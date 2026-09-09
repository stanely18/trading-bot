# Claude Cowork — read-only reviewer runbook

Under architecture v1.0 Cowork does **not** run cycles and does **not** trade.
The runtime is GitHub Actions (`docs/architecture.md`). Cowork reads the
experiment records the workflow commits and produces review reports. Nothing
else it does is authorised: no strategy edits, no prompt edits, no risk-parameter
edits, no code edits, no writes under `state/` `trades/` `logs/`, no order
placement, no scheduling of trading cycles.

## Daily review (recommended: once per day, a few hours after 00:00 UTC)

1. Pull the repo (or read it through the GitHub connector).
2. Follow `prompts/cowork-daily-review.md`.
3. Write exactly one file: `reports/daily/YYYY-MM-DD.md` for the day under review.
4. Commit only that file (message e.g. `daily review YYYY-MM-DD`). Do not touch
   anything else in the working tree.
5. Notify Stanley only on: `halted=true`, drawdown within ~2% of the 10% cap,
   a run of failed/missing cycles, repeated model errors, or a suspected
   experiment-integrity breach.

## Weekly review (recommended: once per week)

Same rules; follow `prompts/cowork-weekly-review.md`; write
`reports/weekly/YYYY-Www.md`. Include the experiment-integrity check (fixed Kimi
prompt, POLICY hash, universe, cadence; list `state/experiment.json` changelog
entries).

## What the reviewer reads

| File | Use |
|---|---|
| `state/portfolio.json` | positions, cash, revision |
| `state/risk_state.json` | halted, drawdown %, daily-loss %, peak equity |
| `state/agent_state.json` | last regime / view, model provider+model+request id, consecutive holds |
| `state/experiment.json` | version, `benchmarks`, `benchmark_vs_strategy`, `changelog` |
| `logs/decisions/<run_id>.json` | full per-cycle record: market, Kimi raw output, adapter sizing (resize/reject), risk result, executed actions, portfolio before/after, `pnl` |
| `logs/workflow/<run_id>.json` | per-run health: step statuses, durations, errors |
| `trades/trades.csv` | appended fills (run_id, utc, symbol, side, qty, price, fee, reason) |

`run_id` is `experiment-YYYY-MM-DDTHHZ`; gaps in the hourly-slot sequence at the
4h cadence indicate missed cycles.

## Historical note

The earlier plan (Cowork as cloud orchestrator writing proposals to a trusted
gateway) is retired because Cowork's cross-session state writes required
per-write manual approval and could not run unattended — see
`evidence/cloud-validation.json`. GitHub Actions replaces that path.
