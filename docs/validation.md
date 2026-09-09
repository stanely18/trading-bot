# 驗收矩陣

| 問題 | 本次狀態（2026-09-09 更新） | 真正通過條件 |
|---|---|---|
| Cowork 雲端排程在 Mac 關機後執行 | **已建立排程、已完成一次線上基線**（trig_01ES7AoJUZCYinuaCNoBxFmy，每小時 :18 分，create_trigger 回應明確標示 `local_device_not_required — this task will run in the cloud only`，即排程本身不綁定使用者裝置）。**尚未實測「Mac 實際關機」區間**——需使用者實際關機並回報 UTC 時間，見 evidence/cloud-validation.json | 至少兩次獨立雲端 scheduled session；平台 UTC 執行時間位於使用者記錄的實際關機區間 |
| OKX public／Demo 與 market state | **本次於真正的 Cowork cloud container（Linux, root, session_016sQPBv5UTncv1JuXcMZV3e）內以 `python3 -m trading_bot market` 成功抓到即時 OKX ticker**，並以 scripts/cloud_probe.py 在同容器內驗證 nonce/hash chain 邏輯正確（見 evidence/cloud-container-smoke.json）。**跨獨立 cloud session 讀回**已透過 Artifact 工具的 db capability（真正跨 session、跨 container 的平台原生持久化）建立 baseline 並觸發一次獨立 fired session 讀回，結果見 evidence/cloud-validation.json。Demo 仍缺憑證 | 雲端抓到新鮮 ticker 並跨次讀回；Demo 唯讀探針成功另列 |
| Codex／替代遠端模型工具 | 本機舊 MCP handshake 成功；**雲端已查核**：此 Cowork cloud session 的 ToolSearch 找不到任何 codex/openai 工具；SearchMcpRegistry 搜尋 codex/openai/gpt/chatgpt 找不到對應 model-inference connector；ListConnectors 顯示此帳號目前已連接的 connector 只有 Adobe、Canva、Gmail、Notion，均非模型推論工具；唯一可見的 gemini-cli 是透過 remote-devices 代理使用者 Mac 上的本機 stdio MCP，Mac 離線時不可用，不算雲端原生能力。**結論：目前沒有可由 Cowork cloud 直接呼叫、不依賴 Mac、且不需新增付費 API 的遠端模型工具** | Cowork cloud session 呼叫遠端工具取得指定模型結果，記錄 provider/model/request ID；本機離線時仍成功 |
| portfolio／persistent state 跨 runs | 本機交易、重啟與並行測試通過；**雲端 container 本地測試通過但明確標示「非跨 session 證據」**（因為同一 session 的容器不會被下一個獨立 session 存取，這點已由官方文件 sources.md 引用的 Cowork recurring tasks 說明證實）。**跨獨立 session 的持久化改用 Artifact 工具 db capability 實測**，見 evidence/cloud-validation.json 的 probe chain 結果 | 不同 session 讀回前次 nonce/revision/hash；重試不重複成交；state 缺失不重設本金 |

## 額外發現：風控權限邊界（本次新增，非原始四項之一但屬使用者要求的第 5 項）

在本 cloud session（session_016sQPBv5UTncv1JuXcMZV3e）內直接測試發現：此 session 對 `trading_bot/core.py`（RiskGateway 實作與 POLICY 常數）與任何 SQLite 帳本檔案擁有完整讀寫權限，且以 root 身分執行（`uid=0`），連 `core.py` 的 444 唯讀權限位元都無法阻擋寫入。也就是說，**任何被指派為 orchestrator 的 Cowork cloud session，技術上都能繞過 RiskGateway 直接竄改風控常數或帳本**，目前唯一的保護是「LLM 沒有被指示這麼做」，不是強制的系統邊界。這證實 docs/architecture.md 原先的判斷是正確的，也是本次未部署獨立遠端 gateway 前，30 日正式實驗必須明確揭露給使用者的限制。詳細部署缺口清單見 docs/deployment.md 底部新增章節。

`evidence/` 的 local 檔只證明本機測試。即使主機名稱顯示 Linux，也不能單獨證明使用者電腦已關機；需平台紀錄和關機／開機時間交叉核對。

測試套件涵蓋正常買賣、成本、並行重複請求、版本衝突、NaN／Infinity／多餘欄位、行情過期、停損、halt、日虧損／回撤、30 日期滿、交易回滾、policy tamper 與 hash chain。測試採 fixture，不將其標示為即時市場。

未部署雲端，未設置任何 Codex 或 Cowork 排程，未呼叫付費模型，未送出任何交易所訂單。正式 30 日帳本尚未建立；本次煙霧測試帳本用獨立臨時路徑。

## 本次實測結果

19 項測試全部通過（含 HTTP 認證、重試與斷網保護）。`evidence/local-smoke.json` 記錄兩次真實 OKX 公開行情 run、跨程序重啟、相同 ID 不重複寫入，以及探針 nonce chain。本次 Demo 探針回傳 missing_demo_credentials；Codex MCP 本機握手通過。
