# Cowork cloud 驗證步驟

## 第一階段：不交易的關機與持久化探針

1. 在 Cowork 選 cloud session，將此專案 ZIP／檔案保存到 Claude 帳號的雲端檔案，避免指定外接硬碟的本機資料夾。
2. 確認該 session 是否能執行 Python、對 OKX 發 HTTPS、以及哪個路徑宣稱可跨 session 保存。若無持久路徑，記錄失敗，不要假設 `/tmp` 或上傳檔案自動持久化。
3. 首次僅用 `python3 scripts/cloud_probe.py --state-dir <候選雲端持久路徑> --run-id probe-001 --session-id <平台session引用> --init`。保存 JSON 到 Claude 帳號的可回讀成果位置。
4. 在新的獨立 cloud session，使用同一 state-dir，新的 run-id／session-id，**不加 --init**。確認 sequence=2、previous_nonce/hash 指向第一筆。若缺 DB，讓它失敗，不重建。
5. 使用 prompts/cowork-probe.md 建立每小時的 Cowork 排程。只用雲端檔案／connectors。記錄預定時間與平台 task ID；完成至少一次線上基線。
6. 使用者在預定執行之前實際關機並記錄 UTC 時間，從手機／網頁檢查至少兩次執行。重新開機後核對平台時間戳、探針時間、session ID、nonce chain。此 POC 不會擅自關機。
7. 重複相同 run-id 應回傳原紀錄，不增加 sequence。斷網／缺檔錯誤也需保留平台輸出。

## 第二階段：可信任 gateway 與 portfolio

若 Cowork 沒有可用持久磁碟，使用 docs/deployment.md 的獨立遠端 gateway；不把多個 sandbox 的 DB 視為同一帳本。模型權限也應縮減到此服務 API。

1. 在可信任 host 的持久磁碟建立測試帳本，啟動受 HTTPS／驗證保護的 gateway。
2. Cowork GET /state，保存 revision。以當下 created_ms、固定 slot ID 提交 HOLD；回讀 revision+1 及 last_run_hash。
3. 下一個獨立 scheduled session 再讀同一 state；重試上一筆完全相同 proposal，確認原 result 不變；再提交新 slot。
4. 完成 Mac 關機測試。只用 HOLD 即可證明 orchestration，不需要交易所憑證或購買模型 API 額度。
5. 以 Demo API 憑證在可信任環境跑 `python3 -m trading_bot probe-demo`。目前只讀餘額並輸出狀態／筆數，不列敏感帳戶數據；未提供憑證時 blocked 是預期。

## 第三階段：遠端模型

先由 cloud session 盤點可用工具名稱、provider/model。使用固定無交易問題測回傳 request ID、模型名稱與延遲，保存結果；再在 Mac 關機期間重測。不要把本機 Codex CLI 登入資訊複製到 Cowork。Codex App Server 需其執行 host 持續在線；Claude Code plugin 並不是 Cowork 支援證據。

若無遠端模型，可由 Cowork 自身輸出 schema proposal，先跑單一模型；其他代理 disabled，明確記錄未驗證。若需付費 API 或新增服務，先確定供應商／預算；不自動切換付費路由。

四項結果另填 evidence/cloud-validation.json（人工新增，附平台引用、UTC 關機區間、實際結果與限制），成功才用新的正式帳本初始化 30 日實驗。驗證後關閉測試排程，避免重複執行。
