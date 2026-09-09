# logs

Per-run records written by trading_bot/cycle.py (UTC).

- `decisions/<run_id>.json` — full 4-hour Kimi cycle: market, Kimi raw output, adapter
  sizing (resize/reject), risk result, executed actions, portfolio before/after, pnl.
- `risk/<run_id>.json` — hourly deterministic risk check (run_id prefix `risk-`): market,
  risk result, any stop/drawdown/daily-loss exits, positions after, pnl. No model, no
  indicators, no benchmark rebalance.
- `workflow/<run_id>.json` — per-run health: step statuses, durations, errors.
- `errors/<run_id>.json` — written only when a step degraded or errored.
