# 官方來源（查核日期：2026-09-09）

1. [Cowork recurring tasks](https://support.claude.com/en/articles/13854387-schedule-recurring-tasks-in-claude-cowork)：排程在遠端執行，不需桌面 app 開啟；依賴本機檔案／app 的任務有本機限制。每次是獨立 session，因此不能假設 Python sandbox 磁碟跨次保存。
2. [Codex MCP server](https://learn.chatgpt.com/docs/mcp-server)：舊 `codex mcp-server` 已棄用，官方建議 App Server 或 Claude Code 的 Codex plugin。這不等於 Cowork cloud 支援該 plugin。
3. [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)：本機客戶端與遠端工具配置須區分。
4. [OKX API guide](https://www.okx.com/docs-v5)：public ticker 路徑 `/api/v5/market/ticker`；Demo 需專用 API key 與 `x-simulated-trading: 1`。公開 ticker 成功不代表 Demo 帳戶或模擬下單成功。

文件支持產品能力，不能代替使用者帳號的雲端部署實測。本次依有效公開行情實測使用 https://www.okx.com；若帳戶因地區使用不同 API 網域，需另行核對官方文件，不自動切換網域或轉送憑證。
