# DEPRECATED — Cowork is no longer the runtime

Under architecture v1.0 the trading runtime is **GitHub Actions**
(`.github/workflows/trading-cycle.yml`), which calls
`python -m trading_bot cycle`. Kimi K3 is the trading agent; the deterministic
Python RiskGateway enforces risk; Claude Code maintains the repo.

Claude Cowork's only role now is **read-only review**:

- Daily:  `prompts/cowork-daily-review.md`  → `reports/daily/YYYY-MM-DD.md`
- Weekly: `prompts/cowork-weekly-review.md` → `reports/weekly/YYYY-Www.md`

Cowork must not trade, schedule cycles, or change strategy / prompt / risk
parameters / code / state. This file is kept only so old links resolve.
See `docs/cowork-runbook.md`.
