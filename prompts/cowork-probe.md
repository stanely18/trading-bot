請在 Claude Cowork cloud 建立基礎設施驗證工作，僅使用雲端檔案與雲端可達工具，每小時一次。先確認此 session 是 cloud，並記錄平台 task/session ID 與 UTC 時間。

使用專案的 scripts/cloud_probe.py；state-dir 必須是已完成首次初始化的候選雲端持久路徑。每個 UTC slot 使用固定 run-id，重試沿用原 ID。不得加 --init、重建遺失資料、改程式或改真實結果。保存 JSON 原始輸出和平台執行引用；失敗亦保存。只有人工第一次 bootstrap 才可初始化。

不進行交易、不取得真金鑰、不操作本機 app、不依賴 /Volumes/Stanley、不開啟新付費模型。列出可用遠端模型工具，無法驗證即標未驗證；不以主機名稱證明電腦已關機。

平常只保存成果；有執行失敗、持久化中斷或首次完成關鍵驗收才通知。測試完成後停用此測試排程。
