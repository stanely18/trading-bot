# 專案規則

- 先讀 README、docs/architecture.md、docs/risk-policy.md、CHANGELOG.md、docs/validation.md。
- 核心原則：Kimi trades. Python controls risk. GitHub Actions runs the system.
  Claude Code maintains it. Cowork reviews it.
- 僅 paper trading。`OKXDemoBroker` 的下單路徑雙重關閉（env `DEMO_ORDER_EXECUTION_ENABLED=1`
  且 `allow_orders=True`）。不得新增 live mode、真金鑰路徑或繞過 RiskGateway。
- LLM（Kimi）僅輸出 `schemas/agent-output.schema.json` 的 ranked candidates；
  不得改風控常數、資料庫、時鐘、行情或 broker。所有 notional 由 `trading_bot/cycle.py`
  的 Python 計算，不採用 Kimi 的數字。
- `trading_bot/core.py` 的 `RiskGateway` 與 `POLICY` 是受保護區：非 bug-fix 不動；
  修改 POLICY 會使既有 `state/experiment.sqlite3` 帳本因 policy_hash 不符而拒絕執行，
  遷移須另行設計，禁止自動重置。
- config/experiment.json 是描述性清單；實際風控以 `POLICY` 為準，不能從 prompt 覆寫。
- 實驗完整性：30 日期間固定 Kimi system prompt（prompts/kimi-system.md）、POLICY、
  universe、cadence。技術 bug 修可做但必記 `CHANGELOG.md` 的 infra 條目；動到策略條件
  必須 bump `experiment_version`（v1.0 → …）並記入 `state/experiment.json.changelog`。
- Cowork 是唯讀 reviewer：不下單、不排程 cycle、不改策略／prompt／風控參數／程式／
  `state/` `trades/` `logs/`。只寫 `reports/`。
- runtime 是 GitHub Actions，不是本機 Claude Code / Desktop / Mac。
- 雲端排程／無人值守運行須有實測紀錄才能宣稱通過。
- 不可修改鄰近 academic-translation，也不複製其認證。
- 變更交易／狀態／cycle／model／broker 程式後執行 `python3 -m unittest discover -s tests -v`
  （需 Python 3.11+；本機 base python 可能是 3.10，改用 python3.11/3.14）。
