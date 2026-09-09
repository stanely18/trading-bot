# logs

Per-cycle records written by trading_bot/cycle.py (UTC).

- `decisions/<run_id>.json` — market, Kimi raw output, adapter sizing (resize/reject),
  risk result, executed actions, portfolio before/after, pnl. Authoritative per-cycle record.
- `workflow/<run_id>.json` — run health: step statuses, durations, errors.
- `errors/<run_id>.json` — written only when a step degraded or errored.
