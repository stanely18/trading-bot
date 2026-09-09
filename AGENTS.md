# 專案規則

- 先讀 README、docs/architecture.md、docs/risk-policy.md、docs/validation.md。
- 僅 paper trading；目前沒有交易所下單介面。不得新增 live mode、真金鑰或繞過 RiskGateway。
- LLM 僅輸出 proposal；不得改風控常數、資料庫、時鐘、行情或 broker。
- 實驗設定 config/experiment.json 是描述性清單；實際風控以 trading_bot/core.py 的固定 POLICY 為準，不能從 prompt 覆寫。
- 修改 POLICY 會使舊帳本拒絕執行；遷移須另行設計，禁止自動重置舊帳本。
- 雲端排程／關機運行／跨 session 持久化須有實測紀錄才能宣稱通過。
- 不可修改鄰近 academic-translation，也不複製其認證。
- 變更交易／狀態程式後執行 python3 -m unittest discover -s tests -v。
