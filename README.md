# trading-bot：30 日 paper trading POC

目標：以 Claude Cowork cloud 作主 orchestrator，驗證遠端排程、OKX 資料、模型工具與跨次狀態。此版本已可在本機執行；**尚未部署雲端、尚未開始 30 日排程**。

## 已實作

- OKX BTC／ETH／SOL-USDT 公開行情；Demo 帳戶唯讀探針。
- 固定 Python 風控 + paper 成交，含費用／滑價／停損；完全沒有真實或 Demo 交易所下單程式。
- SQLite 原子交易保存 portfolio、market、proposal、fills、版本與 hash chain；重複 run ID 不重複成交，帳本不存在即停止。
- 本機 CLI、供遠端封裝的 HTTP gateway、Cowork 雲端持久化探針、模型擴充 Protocol 與 JSON Schema。
- 預設策略 HOLD。這是基礎建設驗證，沒有已證實的交易策略或獲利主張。

## 快速執行

需 Python 3.11+，核心僅使用標準函式庫，不需安裝套件。

```sh
cd '/Volumes/Stanley/專案/trading-bot'
python3 -m unittest discover -s tests -v
python3 -m trading_bot market
python3 -m trading_bot --db state/smoke.sqlite3 init
python3 -m trading_bot --db state/smoke.sqlite3 run --run-id smoke-001
python3 -m trading_bot --db state/smoke.sqlite3 run --run-id smoke-001
python3 -m trading_bot --db state/smoke.sqlite3 export
```

第二次相同 ID 會回傳原結果。`init` 只執行一次，既有檔案會拒絕覆寫。測試帳本與正式 30 日帳本請用不同路徑；正式計時從該帳本 init 起算。任何持倉的停損與期限退出只在下一次成功取得行情的 run 發生。

模型輸出符合 `schemas/proposal.schema.json` 後，可用 `run --proposal proposal.json` 提交；價格永遠由程式自行抓取。先 `state` 取得 expected_revision，created_ms 使用當下 UTC 毫秒；proposal 有效期 60 秒。HTTP 模式另見部署文件。

## 專案導覽

| 位置 | 用途 |
|---|---|
| docs/architecture.md | 提案、信任邊界與 30 日階段 |
| docs/risk-policy.md | 風控數值與限制 |
| docs/validation.md | 四項驗收與目前證據 |
| docs/cowork-runbook.md | 雲端排程、關機及持久化測試步驟 |
| docs/deployment.md | 遠端 gateway／模型接入 |
| docs/environment.md | CLI／MCP 盤點 |
| docs/sources.md | 官方來源與查核日期 |
| prompts/ | Cowork 可用提示詞 |
| config/ | 描述性設定及環境變數範本 |
| schemas/ | 狀態與代理資料契約 |
| trading_bot/ | 行情、風控、帳本、CLI、HTTP 與擴充介面 |
| scripts/ | 環境、雲端及 MCP 探針 |
| tests/ | 核心與 HTTP 風控測試 |
| evidence/ | 本次本機實測；非雲端驗收 |

## 目前阻礙

此工作環境只有本機 CLI／MCP，未接通使用者 Cowork cloud session、遠端持久化主機或 Demo 憑證。下一步依 docs/cowork-runbook.md 做兩次不同雲端 session 的無交易探針，並在使用者實際關機時驗證排程。不要把 `/Volumes/Stanley/…` 當成雲端 state 路徑。

## GitHub 交接

私人儲存庫僅保存程式、文件與空白設定範本。`evidence/`、`docs/environment.md`、`.env`、state 與資料庫只留在本機，未隨 Git 上傳；文件中的證據路徑不表示遠端儲存庫含有該檔案。雲端執行憑證請透過執行環境的 secret manager 設定，勿寫入程式、prompt 或 commit。
