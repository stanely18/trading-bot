# 固定風控

實作來源：`trading_bot/core.py` 的 POLICY。設定檔只是實驗描述，不控制放寬風險。

| 規則 | 數值／行為 |
|---|---|
| 模式 | 僅 paper；沒有 live 或 Demo 下單路由 |
| 起始本金／期限 | 10,000 USDT／30 日 |
| 交易範圍 | BTC、ETH、SOL-USDT 現貨、多頭 |
| 每筆名目額 | ≤ 當前 NAV 10% |
| 單幣部位 | ≤ 當前 NAV 20%；現版禁止任何加碼 |
| 同時持倉 | 最多 3 |
| 新單頻率 | UTC 每日最多 24 次成交後禁止新買入；風險退出不受此限制 |
| 計畫損失 | 每筆止損距離 + 來回費用滑價 ≤ NAV 0.5% |
| 停損 | 成交價下方 2%，下次 run 依當時價執行 |
| 當日虧損 | 相對前 UTC 日最後觀測 NAV 跌 2%，退出並拒絕新買入 |
| 最大回撤 | 相對已觀測 peak NAV 跌 10%，永久 halt 並退出 |
| kill switch | `python3 -m trading_bot halt`；阻止買入，下次 run 退出 |
| 成本假設 | 每邊 10 bps 手續費 + 5 bps 滑價；非 OKX 真實費率 |
| 資料有效期 | 行情 ≤ 60 秒，可容忍前移 5 秒；proposal ≤ 60 秒且不得未來時間 |
| 衝突 | revision 不符、相同 ID 不同 input、缺 state、policy hash 不符皆拒絕 |
| 出場 | 停機、虧損超限或期滿仍允許退出；資料錯誤時不以虛構價格平倉 |

每筆 fill、market 與 state 更新在同一 SQLite transaction 完成。已提交相同 proposal 的 retry 可返回原結果；它不代表重新做風控或新成交。無效格式／行情／revision 不寫交易帳本，CLI 非零退出，HTTP 回傳錯誤；部署者須保留排程失敗日誌。

金額目前使用 Python float，適合基礎設施 paper POC；並未驗證 OKX tick size、lot size、min size、部分成交或撮合。正式 Demo 下單前需改 Decimal、商品規格檢查、持久 outbox、clOrdId、防未知訂單重送與交易所對帳。

**停損不是保證損失上限。** 本版每次 run 才檢查，跳空、排程缺漏與斷網會超過 0.5% 計畫風險、2% 日虧損及 10% 回撤閾值；程式會在下一次可用行情時處理，不保證提前攔截。

LLM 只能使用受限 API；不得讓遠端 LLM 登入可修改 gateway 或帳本的主機。HOLD 請求也會執行既有部位的必要風控退出。
