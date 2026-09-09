# 驗收矩陣

**2026-09-09T18:05Z 重大更正**：使用者實測回報，排程觸發的獨立 session 每次執行到 Artifact db 的 write_db 那一步，都會跳出對話內工具使用核准視窗，且只有「這次允許」、沒有永久選項，必須使用者當下在場手動點擊才會繼續。這代表先前記錄的兩次「排程成功」，其實是使用者剛好在場點了核准才完成，不是排程機制真正無人值守；也讓原本第一次卡在 PENDING 超過一小時的那次有了更合理的解釋——很可能是卡在等待同一個核准，只是當時沒人看著對話去點。以下矩陣已依此更正。

| 問題 | 本次狀態（2026-09-09 更新） | 真正通過條件 |
|---|---|---|
| Cowork 雲端排程在 Mac 關機後執行 | **部分通過，有重大保留**：排程觸發（cron 建立新 session）本身不依賴使用者 Mac、`derived_state.folders_state=FOLDERS_STATE_NONE`，這部分已確認。但完整流程（含跨 session 狀態寫入）目前需要使用者即時在場核准才能跑完，**不算真正無人值守**。「Mac 實際關機」的實地測試意義不大，除非先解決核准問題，否則關機後排程大概率會卡住，如同最早那次一樣 | 至少兩次獨立雲端 scheduled session，**且全程沒有人為即時介入**；平台 UTC 執行時間位於使用者記錄的實際關機區間 |
| OKX public／Demo 與 market state | 即時行情雲端抓取＝**已通過**（見 evidence/cloud-container-smoke.json）。跨獨立 cloud session 讀回的**功能與鏈完整性＝已驗證**（sequence 1→2→3，每筆 hash 都經本對話獨立重算比對相符，非單憑該 session 自述），但**無人值守的寫入＝未通過**：每次 write_db 都需要使用者即時手動核准。Demo 仍缺憑證 | 雲端抓到新鮮 ticker 並跨次讀回，**且寫入不需要即時人工核准**；Demo 唯讀探針成功另列 |
| Codex／替代遠端模型工具 | 本機舊 MCP handshake 成功；雲端原生 connector 盤點（ToolSearch／SearchMcpRegistry／ListConnectors）找不到 Codex/OpenAI 選項，結論維持不變。**2026-09-09T18:20Z 更新**：使用者同意新增付費 API 後，改測 NVIDIA NIM 上的 `moonshotai/kimi-k3`——本對話直接呼叫成功（HTTP 200，request_id `chatcmpl-42d62540-5fe2-42db-9a03-6e262fa0f4b9`），回傳的 HOLD proposal 通過 `schemas/proposal.schema.json` 驗證。**這只是模型 API 本身的直接呼叫測試，不是接進 CLI／RiskGateway 的完整送審流程**。API key 僅存在於本次測試的環境變數，未寫入任何檔案或 trigger。**尚未解決**：要把這個模型接進『每小時排程、無人值守』的正式流程，key 要如何安全地喂進每一次全新的排程 session——目前沒有暴露可用的密鑰保管機制，只能寫進 trigger 明碼 prompt（等同外洩），這跟 item_1/2/4 的 Artifact 核准問題是同一類根本缺口 | Cowork cloud session 呼叫遠端工具取得指定模型結果，記錄 provider/model/request ID（**已達成**）；本機離線時仍成功、且能在無人值守排程中安全使用金鑰（**尚未達成**） |
| portfolio／persistent state 跨 runs | 本機交易、重啟與並行測試通過；雲端 container 本地測試通過但明確標示「非跨 session 證據」。跨獨立 session 的持久化「機制」（Artifact db capability）技術上可行且鏈完整，但**同樣卡在每次寫入需要即時人工核准**，不能視為可無人值守運作的持久化管道。**這證明的是機制可行，不是 trading_bot 自身 SQLite 帳本可以無人值守地跨 session 存活**——後者仍需 docs/deployment.md 缺口清單所列的獨立、常駐、不經消費者核准 UI 的持久磁碟服務 | 不同 session 讀回前次 nonce/revision/hash，**且寫入不需要即時人工核准**；重試不重複成交；state 缺失不重設本金 |

## 額外發現：風控權限邊界（本次新增，非原始四項之一但屬使用者要求的第 5 項）

在本 cloud session（session_016sQPBv5UTncv1JuXcMZV3e）內直接測試發現：此 session 對 `trading_bot/core.py`（RiskGateway 實作與 POLICY 常數）與任何 SQLite 帳本檔案擁有完整讀寫權限，且以 root 身分執行（`uid=0`），連 `core.py` 的 444 唯讀權限位元都無法阻擋寫入。也就是說，**任何被指派為 orchestrator 的 Cowork cloud session，技術上都能繞過 RiskGateway 直接竄改風控常數或帳本**，目前唯一的保護是「LLM 沒有被指示這麼做」，不是強制的系統邊界。這證實 docs/architecture.md 原先的判斷是正確的，也是本次未部署獨立遠端 gateway 前，30 日正式實驗必須明確揭露給使用者的限制。詳細部署缺口清單見 docs/deployment.md 底部新增章節。

`evidence/` 的 local 檔只證明本機測試。即使主機名稱顯示 Linux，也不能單獨證明使用者電腦已關機；需平台紀錄和關機／開機時間交叉核對。

測試套件涵蓋正常買賣、成本、並行重複請求、版本衝突、NaN／Infinity／多餘欄位、行情過期、停損、halt、日虧損／回撤、30 日期滿、交易回滾、policy tamper 與 hash chain。測試採 fixture，不將其標示為即時市場。

未部署雲端，未設置任何 Codex 或 Cowork 排程，未呼叫付費模型，未送出任何交易所訂單。正式 30 日帳本尚未建立；本次煙霧測試帳本用獨立臨時路徑。

## 本次實測結果

19 項測試全部通過（含 HTTP 認證、重試與斷網保護）。`evidence/local-smoke.json` 記錄兩次真實 OKX 公開行情 run、跨程序重啟、相同 ID 不重複寫入，以及探針 nonce chain。本次 Demo 探針回傳 missing_demo_credentials；Codex MCP 本機握手通過。
