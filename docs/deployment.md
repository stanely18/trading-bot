# 遠端部署與介面

> **v1.0 狀態**：主 runtime 已改為 GitHub Actions（`docs/architecture.md`），
> 不再需要對外的 HTTP gateway 或獨立主機來啟動 30 日實驗。本文件描述的
> `trading_bot/server.py` gateway 保留為**次要／選用** transport（例如日後要讓
> 一個獨立服務隔離 RiskGateway、或給非 GitHub 的 orchestrator 用）。下方
> 「獨立遠端 gateway 部署尚缺項目」清單對 v1.0 不是啟動前置條件，但仍是把
> RiskGateway 變成檔案系統上 LLM 完全無法觸及之可信任服務的路線圖。

HTTP gateway 已有最小實作，**不是 MCP server**，也尚未發布到網路。Cowork 能否直接呼叫 HTTP 需在該 cloud session 驗證；若只支援 remote MCP，需另外部署 MCP wrapper，僅映射此處窄 API，不提供 shell 或通用 HTTP proxy。

## 本機服務檢查

```sh
python3 -m trading_bot --db state/gateway.sqlite3 init
# 以部署環境的 secret manager 提供至少 32 字元隨機 TRADING_GATEWAY_TOKEN。
# 不要把 token 放進 prompt、版本控制或 URL。
export TRADING_DB=state/gateway.sqlite3
python3 -m trading_bot.server
```

服務固定只聽 127.0.0.1:8765。部署到**使用者另行指定的雲端 host**，需 HTTPS reverse proxy、secret injection、持久磁碟、非 root 服務帳號、流量／body timeout、服務重啟、監控及備份。Python http.server 只是 POC transport，不直接暴露公網。本版沒有 provision 主機、DNS、TLS、OAuth 或 remote MCP。

| 方法／路徑 | 輸入 | 結果 |
|---|---|---|
| GET /health | Authorization: Bearer token | paper 模式／版本 |
| GET /state | 相同認證 | 唯讀 portfolio 與最近 market |
| POST /proposals | schema proposal JSON | trusted market → RiskGateway → record |

所有路由需認證。沒有重設／修改 state、改 policy、指定行情、指定執行模式或改 DB 路徑的路由。HTTP 409 表示無效／衝突，503 表示執行錯誤；網路中斷而結果不明時，以相同 ID **及完全相同 body** 重試，避免重複成交。

首次 state 的 market 是空物件；先提交 baseline HOLD 取得行情。策略不可拿過期 snapshot 繼續下單，必須重讀 state／重新生成 proposal。

模型帳號只能有 API token；不能有部署帳號、secret manager、掛載 volume 或檔案工具的寫權。當 API token 可由惡意 prompt 使用時，固定風控仍限制 proposal，但模型可能亂發合法小額 paper 單；每日上限限制新增交易。

SQLite 必須位於單一 host 支援鎖定／同步的持久檔案系統；不要使用不支援鎖定的共享磁碟或直接複製運行中 DB。備份使用 SQLite backup API，恢復測試後才啟動排程。多節點需另實作交易式 DB backend。

Codex 遠端模型擴充以 App Server service wrapper 為建議方向（尚未實作）；不得假定本機 stdio MCP 可由雲端存取。維持模型 context-only、禁止 gateway 檔案寫入、不自動新增 API 計費。

## 2026-09-09T18:05Z 新增關鍵發現：Cowork 平台原生跨 session 持久化管道無法無人值守

實測發現：本專案原先選用的跨獨立 cloud session 持久化管道（Claude Artifact 工具的 db capability）讀寫功能與 hash chain 完整性都正確，但**每一次 write_db 寫入，在一個全新的排程觸發 session 中，都會跳出對話內工具使用核准視窗，且只有「這次允許」、沒有「永遠允許/不再問」的選項**，必須使用者當下在場手動點擊才會繼續執行。這不是這個專案程式碼的問題，是 Cowork 平台對這類動作的既有安全設計（消費者導向的逐次核准 UI）。

實務影響：目前沒有已驗證可行、且不需要使用者即時在場核准的跨 session 狀態持久化方式。這代表下面第 1～4 項「獨立主機／持久磁碟」的必要性，不只是「讓風控邊界可強制」的加分項，而是**讓正式 30 日排程能真正無人值守運作的必要條件**——只要還在用 Artifact db 這類消費者核准 UI 做狀態持久化，排程只要在使用者沒看對話時觸發，就有很高機率卡住（很可能就是本次驗證過程中第一次觸發異常卡住超過一小時的真正原因）。獨立部署的資料庫／持久磁碟走的是標準連線（如 HTTP API 帶 token、或直接的資料庫協定），不會經過這種核准 UI，是目前唯一已知能真正無人值守的路徑。

## 獨立遠端 gateway 部署尚缺項目（2026-09-09 盤點；僅列清單，不宣稱已部署）

Cowork cloud 驗證證實：任何能在此 sandbox 執行 shell/Python 的 session（包含目前這個 orchestrator 本身）對 `trading_bot/core.py`、POLICY 常數與任何 SQLite 帳本檔案都有完整讀寫權限（此 session 甚至以 root 執行，連檔案權限位元都無法阻擋），因此「LLM 不能覆寫風控」目前不是可強制的邊界。要讓 RiskGateway 成為真正獨立、LLM 無法觸及檔案系統的可信任服務，需要使用者決定並提供以下項目——本專案目前都沒有，以下純粹是清單，不是已完成的部署：

1. **主機**：一台 LLM orchestrator（Cowork cloud session）不具 shell／檔案系統存取權的獨立主機（VM、容器平台或 PaaS）。需使用者選擇供應商與付費方案；未經同意不自動建立。
2. **網域與 TLS**：對外 DNS 名稱＋憑證（如 Let's Encrypt 或雲端供應商代管憑證），供 HTTPS reverse proxy 使用；`trading_bot/server.py` 目前只支援 loopback，需在其前面加 reverse proxy。
3. **Secret Manager**：存放 `TRADING_GATEWAY_TOKEN`（≥32 字元隨機值）與（若日後需要）OKX Demo API 金鑰，且 LLM 帳號不可有讀取權；建議雲端供應商原生的 secret manager，而非放進版本控制或環境變數檔。
4. **持久磁碟**：SQLite 檔案所在的單一可信任 host 持久磁碟，支援檔案鎖定；需定期用 SQLite backup API 備份，並實際做過還原測試才能啟動排程。
5. **非 root 服務帳號**：`trading_bot.server` 應以最小權限的專用系統帳號執行，而非目前示範用的 root。
6. **流量與逾時控管**：body size limit（現有 16384 bytes 已在程式內）、連線逾時、reverse proxy 層級的 rate limiting。
7. **服務重啟與監控**：process supervisor（如 systemd／supervisor）、健康檢查、失敗告警（對應 `GET /health`）。
8. **模型帳號權限縮減**：LLM／Cowork cloud 只應持有 gateway 的 API token（`/state`、`/proposals`），不可有部署帳號、SSH、secret manager 存取權或掛載磁碟權限——這需要在第 1–3 項的主機上另外設定 IAM／存取控制，屬於部署時的權限設計，不是程式碼變更。
9. **Codex／其他遠端模型的 App Server**：若採用，需要其獨立、持續在線的 host（App Server 需要執行環境常駐），並且是另一個需要使用者決定供應商與預算的項目；本次盤點確認 Cowork cloud session 本身無法直接呼叫 Codex（無 connector、無本機 CLI），本機 stdio MCP 也不能視為雲端可達。

以上任一項目都需要使用者提供主機／預算／供應商決定；在此之前，30 日正式實驗只能維持現有「Cowork cloud sandbox 直接執行 Python」模式，並且必須承認這只是基礎設施驗證，不是「LLM 無法覆寫風控」的可強制保證。
