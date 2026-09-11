# 架構 v1.0

核心原則：**Kimi trades. Python controls risk. GitHub Actions runs the system.
Claude Code maintains it. Cowork reviews it.**

30 日 paper 實驗，初始 **10 USDT** 虛擬資金（v1.1 起；v1.0 shakeout 用 10,000 USDT），
UTC 每 4 小時一次，現貨、多頭，
universe = BTC / ETH / SOL / BNB / XRP-USDT。沒有槓桿、借貸或真錢。

## 元件角色

| 元件 | 角色 | 不做的事 |
|---|---|---|
| **AWS EC2 t3.micro + cron**（`scripts/run_on_vm.sh`）| **主 runtime（2026-09-11 起）**。常開 VM，`crontab` 每 4h 跑完整 cycle、每小時跑 risk-check，fetch → 執行 → commit → push。取代原本 GitHub Actions `schedule:`（實測會延遲/丟 tick）| 不依賴本機 Mac、Claude Code 或 Claude Desktop 在線 |
| **GitHub Actions**（`trading-cycle.yml` / `risk-monitor.yml`）| **已 disable**，只留作手動 fallback（`gh workflow run ...`）。程式邏輯與 VM 完全相同，見 `docs/vm-runtime-setup.md` | 不再是排程來源 |
| **Kimi K3**（NVIDIA NIM，`trading_bot/model/`）| 主 trading agent。讀整理好的 market snapshot + indicators + portfolio，輸出 `schemas/agent-output.schema.json`：market_regime、portfolio_view、ranked candidates（含 confidence / target_allocation / thesis / invalidation / risk_notes）| 不呼叫交易所、不算 USDT 部位大小、不碰 policy／DB／金鑰 |
| **Python RiskGateway**（`trading_bot/core.py`，未變動）| 唯一會動到餘額的程式。固定 POLICY、版本檢查、idempotency、atomic SQLite transaction、hash chain | 沒有可被 prompt 覆寫的欄位 |
| **`trading_bot/cycle.py` adapter** | 把 Kimi 的 candidates 轉成 RiskGateway 內部 proposal；**notional 一律由 Python 以 `min(target_allocation, caps) × NAV` 計算** —— 這是 RESIZE 點；每次 resize／reject 寫入 `logs/decisions/` | 不信任 Kimi 給的數字 |
| **Claude Code** | 開發、review、debug、改 Kimi prompt／策略／風控參數、分析 log、維護 repo | 不是 runtime；架構不要求它常駐 |
| **Claude Cowork** | 唯讀 daily／weekly reviewer，產 `reports/` | 不下單、不改策略／prompt／風控／程式／state、不排程 cycle |

```text
AWS EC2 cron（每 4h UTC；GitHub Actions workflow_dispatch 為手動 fallback）
  1 載入 state/experiment.sqlite3 + state/*.json（git）
  2 讀 risk_state
  3 抓 OKX public market（5 symbols ticker）
  4 抓 candles → 計算 deterministic indicators（SMA/RSI/momentum/vol/trend）
  5 組 Kimi context
  6 呼叫 Kimi K3（NVIDIA_API_KEY 來自 GitHub Secret；缺 key → 明確 fail → 該 cycle HOLD）
  7 驗證 agent JSON（schemas/agent-output.schema.json）
  8 Python 選單一最高信心 candidate + 計算 notional（RESIZE / REJECT）
  9 RiskGateway.run(proposal, market) → paper fill（atomic）
 10 讀 portfolio after
 11 寫 state/portfolio.json、risk_state.json、agent_state.json、experiment.json（含 benchmarks）
 12 寫 logs/decisions/<run_id>.json、append trades/trades.csv
 13 寫 logs/workflow/<run_id>.json（health / errors）
  → git commit "cycle <run_id> [skip ci]" + push（無 push trigger，不會遞迴）
```

## 信任邊界（v1.0 相較舊版的改善）

舊版把 LLM 放進能執行 shell 的 sandbox，因此「LLM 不能改風控」不是可強制的邊界。
v1.0 下 **Kimi 只透過 NVIDIA HTTPS API 回傳文字**，在 GitHub Actions runner 內沒有
shell、沒有檔案系統寫入權、看不到 repo secret 以外的東西；`cycle.py` 與 RiskGateway
才是 runner 內執行的程式，Kimi 無法觸及。這使「模型只能建議、Python 強制風控」在
這個 runtime 下實際成立。

殘留風險（誠實揭露）：

- 有 repo write 權的人（或被入侵的 Actions token）仍可改 `core.py`／POLICY 並 commit。
  緩解：POLICY 變更會使既有 ledger 的 `policy_hash` 不符而拒絕執行；`CHANGELOG.md` +
  `state/experiment.json.changelog` 留痕；branch protection 由 Stanley 決定。
- `state/experiment.sqlite3` 進 git 是單一 committer（workflow）+ `concurrency` 序列化
  的權宜做法。多節點 / 抗竄改儲存 → 未來換 Postgres compare-and-swap，資料契約不變。
- Kimi 仍可能在額度內亂發合法小額 paper 單；`max_daily_orders` 與每筆上限限制影響。

## 30 日順序

1. **啟動前**：`python -m trading_bot --db state/experiment.sqlite3 init` 一次並 commit；
   設 GitHub Secret `NVIDIA_API_KEY`；`TRADING_MODEL` 先留 `none` 跑 1–2 天純基礎設施
   （HOLD、benchmarks、log、commit 迴圈）確認排程穩定。
2. 轉 `TRADING_MODEL=nvidia`（repo variable），實驗版本記為 v1.0，30 日計時從 ledger
   `started_ms` 起算（720 個理論 4h... 實際 slot 依 start/end 對齊，分母用實際數）。
3. 期間固定：Kimi system prompt、POLICY、universe、cadence。技術 bug 修可做，必記
   `CHANGELOG.md`；動到策略條件必須 bump experiment version。
4. 期滿：`ends_ms` 後 RiskGateway 對任何持倉做 paper 平倉（stop / experiment_ended），
   保留完整 ledger 與 `logs/` 再分析。

## 後續擴充點（v1.0 不做）

多 candidate 同 cycle 執行；OKX Demo 真下單（`trading_bot/broker/OKXDemoBroker`，
目前雙重關閉）；多模型比較（各自獨立 ledger、相同 snapshot / policy / 成本）；
Postgres 狀態後端；Sharpe/Sortino 等完整報表（weekly reviewer 已預留）。
`interfaces.py` 與 model request/response schema 保留 request id / provider / model /
snapshot hash / usage / latency 欄位供之後使用。
