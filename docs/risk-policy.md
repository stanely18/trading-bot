# 固定風控

實作來源：`trading_bot/core.py` 的 `POLICY`（數值 v1.0 未變動）。設定檔只是實驗描述，
不控制放寬風險。任何 LLM 建議都必須經過 `RiskGateway`；LLM 不得修改、繞過或 override
下列限制。

| 規則 | 數值／行為 |
|---|---|
| 模式 | 僅 paper；沒有 live 或 Demo 下單路由（`OKXDemoBroker` 下單雙重關閉） |
| 起始本金／期限 | **10 USDT**／30 日（v1.1 起；v1.0 是 10,000 USDT） |
| 交易範圍 | BTC、ETH、SOL、BNB、XRP-USDT 現貨、多頭（v1.0 由 3 擴為 5） |
| 每筆名目額 | ≤ 當前 NAV 10% |
| 單幣部位 | ≤ 當前 NAV 20%；禁止任何加碼（pyramiding_disabled） |
| 同時持倉 | 最多 3 |
| 新單頻率 | UTC 每日最多 24 次成交後禁止新買入；風險退出不受此限制 |
| 計畫損失 | 每筆止損距離 + 來回費用滑價 ≤ NAV 0.5% |
| 停損 | 成交價下方 2%，下次 run 依當時價執行 |
| 當日虧損 | 相對前 UTC 日最後觀測 NAV 跌 2%，退出並拒絕新買入 |
| 最大回撤 | 相對已觀測 peak NAV 跌 10%，永久 halt 並退出 |
| kill switch | `python3 -m trading_bot --db state/experiment.sqlite3 halt`；阻止買入，下次 run 退出 |
| 成本假設 | 每邊 10 bps 手續費 + 5 bps 滑價；非 OKX 真實費率 |
| 資料有效期 | 行情 ≤ 60 秒，可容忍前移 5 秒；proposal ≤ 60 秒且不得未來時間 |
| 衝突 | revision 不符、相同 ID 不同 input、缺 state、policy hash 不符皆拒絕 |
| 出場 | 停機、虧損超限或期滿仍允許退出；資料錯誤時不以虛構價格平倉 |

## Position sizing 由 Python 計算，不相信 Kimi 的數字

Kimi 只給 `target_allocation`（NAV 分數，建議值）。`trading_bot/cycle.py` 的
`size_and_select` 每 cycle 最多選一個信心最高的 actionable candidate，並計算：

```
raw      = target_allocation × NAV
notional = floor2( min( raw,
                        max_order_fraction   × NAV,     # 10%
                        max_position_fraction × NAV,    # 20%
                        NAV × max_planned_loss_fraction / planned_loss_rate ) )
```

- `notional < raw` → 記為 **RESIZED**（例：Kimi 說 BUY ETH 40% → Python RESIZED 至 10%）。
- BUY 已持有該幣 → 略過（會是 `pyramiding_disabled`）。
- SELL / CLOSE：`notional` 由現值與目標值計算，向下取整避免 oversell。
- 沒有可執行 candidate、或 sized 後為 0 → HOLD。
- 之後 `RiskGateway.run()` 仍會獨立再檢查一次；上面只是先行夾擠，不取代風控。

每一次 RESIZE / REJECT（含 `adapter.considered[]` 內每個被略過的 candidate 與原因）
都寫進 `logs/decisions/<run_id>.json`。

## 未變動的保留事項

金額用 Python float，適合 paper POC；未驗證 OKX tick / lot / min size / 部分成交。
真 Demo 下單前需改 Decimal、商品規格檢查、持久 outbox、clOrdId、防重送與對帳。

**停損不是保證損失上限。** 每次 run 才檢查；跳空、排程缺漏、斷網會超過 0.5% 計畫風險、
2% 日虧損、10% 回撤閾值，程式只在下一次可用行情時處理。

**兩層 cadence（2026-09-09）**：Kimi 的**交易決策**維持每 4h 一次（固定實驗條件）。
另有 `risk-monitor` workflow **每小時**跑 `risk-check`：不呼叫任何模型，只抓行情 →
RiskGateway 跑一個 HOLD proposal（仍會執行停損／回撤／日虧損／期滿退出）→ commit。
`run_id` 用 `risk-` 前綴，與 4h 交易 slot（`experiment-`）分開；輸出在 `logs/risk/`。
這把停損執行延遲從 ≤4h 降到 ≤1h，但跳空／缺漏／斷網下仍不保證提前攔截。

LLM 只能使用受限介面（NVIDIA API 回傳文字）；在 GitHub Actions runner 內沒有 shell、
檔案寫入權或 secret 讀取權。HOLD 請求也會執行既有部位的必要風控退出。
