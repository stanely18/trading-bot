# trading-bot：30 日 AI crypto paper-trading 實驗

**Kimi trades. Python controls risk. GitHub Actions runs the system. Claude Code
maintains it. Cowork reviews it.**

不使用真實資金。第一階段：OKX Demo / paper、GitHub Actions 作 unattended runtime、
NVIDIA API 上的 Kimi K3 作 trading agent、Python deterministic risk engine 作不可被
LLM 覆寫的風控層。MacBook 不需要 24/7 開機。

架構全貌見 `docs/architecture.md`；風控數值見 `docs/risk-policy.md`；實驗完整性規則見
`CHANGELOG.md`。

## 元件

| 元件 | 角色 |
|---|---|
| `.github/workflows/trading-cycle.yml` | 主 runtime，每 4h UTC + 手動 dispatch，一次一個 cycle（Kimi 決策），結束 commit state/logs/trades |
| `.github/workflows/risk-monitor.yml` | 每小時 deterministic 安全網：無模型，抓行情 → RiskGateway HOLD（執行停損／回撤／日虧損退出）→ commit。`risk-` run_id 前綴，`logs/risk/`。停損延遲 ≤1h |
| `trading_bot/model/`（`NvidiaKimiClient`）| Kimi K3 → `schemas/agent-output.schema.json`（market_regime / portfolio_view / ranked candidates）。可替換介面，換 NVIDIA 其他模型不動交易邏輯。缺 `NVIDIA_API_KEY` 明確 fail |
| `trading_bot/core.py`（`RiskGateway` / `POLICY`）| 唯一動餘額的程式。固定風控、版本檢查、idempotency、atomic SQLite、hash chain。**未變動** |
| `trading_bot/cycle.py` | 13 步 cycle；把 candidates 轉內部 proposal，**notional 由 Python 算**（RESIZE 點），每次 resize/reject 落 `logs/decisions/` |
| `trading_bot/broker/` | `Broker` 介面：`PaperBroker`（第一階段唯讀 + RiskGateway 成交）、`OKXDemoBroker`（public 行情可用，下單雙重關閉） |
| `trading_bot/indicators.py` / `benchmarks.py` | deterministic 指標與 LLM-free benchmark（BTC buy&hold / equal-weight / momentum） |
| Claude Code | 開發、debug、改 prompt／策略／風控參數、分析 log。不是 runtime |
| Claude Cowork | 唯讀 daily／weekly reviewer，產 `reports/`。不下單、不改策略 |

## 本機 dry-run

需 Python 3.11+，核心僅標準函式庫，不需安裝套件。

```sh
python3 -m unittest discover -s tests -v          # 53 tests
python3 -m trading_bot market                     # 真實 OKX 5-symbol 行情

# 一次性 bootstrap 正式帳本（30 日計時從此起算），之後 commit
python3 -m trading_bot --db state/experiment.sqlite3 init

# 跑一個 cycle：--model none = 只做 HOLD 的基礎設施檢查
python3 -m trading_bot --db state/experiment.sqlite3 --root . --model none \
  cycle --run-id experiment-$(date -u +%Y-%m-%dT%H)Z

# 接 Kimi（需先 export NVIDIA_API_KEY）
export NVIDIA_API_KEY=...   # 不要寫進檔案或 commit
python3 -m trading_bot --db state/experiment.sqlite3 --root . --model nvidia \
  cycle --run-id experiment-$(date -u +%Y-%m-%dT%H)Z

python3 -m trading_bot --db state/experiment.sqlite3 export
```

相同 `--run-id` 重跑是 idempotent：重放已存的 proposal 與 market，不再呼叫 Kimi、不重複成交。
`init` 只能一次，既有檔案拒絕覆寫，帳本不存在即停止（不自動重置）。測試帳本請用別的路徑。

## 上線前尚缺（GitHub Actions）

1. `python3 -m trading_bot --db state/experiment.sqlite3 init` 並把 `state/experiment.sqlite3` commit。
2. 設 GitHub Secret `NVIDIA_API_KEY`；repo variable `TRADING_MODEL`（先 `none`，穩定後改 `nvidia`）。
3. 先讓 workflow 跑 1–2 天 `none` 模式，確認每 4h 排程、commit 迴圈、無遞迴觸發。
4.（可選）branch protection，避免非 workflow 的 commit 改動 `trading_bot/core.py` / POLICY。
5. OKX Demo 憑證僅在要做 Demo 帳戶讀取 / 未來真下單時才需要；第一階段非必要。

## 歷史

舊架構（Cowork cloud 作 orchestrator）因跨 session 狀態寫入每次需人工即時核准、無法
無人值守而retired，詳見 `evidence/cloud-validation.json`、`docs/validation.md`。
GitHub Actions 取代該路徑。

## GitHub 交接

私人 repo 保存程式、文件、空白設定範本，以及 30 日實驗的 `state/experiment.sqlite3`
帳本與 `state/*.json`、`logs/`、`trades/`、`reports/` 記錄。`evidence/`、
`docs/environment.md`、`.env` 不進版本控制。雲端憑證一律走 GitHub Secrets，勿寫入
程式、prompt 或 commit。
