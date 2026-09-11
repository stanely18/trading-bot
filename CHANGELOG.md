# Experiment changelog

Any change that affects strategy conditions must be recorded here **and** in
`state/experiment.json` (`changelog[]`), with the experiment version bumped.
Technical bug fixes that do not change strategy conditions are listed under a
dated "infra" entry and do not bump the version. During a live 30-day run the
fixed conditions are: Kimi system prompt, enforced POLICY, universe, cadence.

## v1.1 — live start 2026-09-11T02:33:47Z (ends 2026-10-11T02:33:47Z)

**Strategy-condition change, so the version bumps.** Two things changed:

- **Runtime moved from GitHub Actions to an AWS EC2 t3.micro cron VM.** GitHub
  Actions' `schedule:` trigger proved unreliable in practice (one night: 3 of 9
  hourly risk-monitor ticks fired, and a whole 4h trading-cycle tick was
  dropped). `scripts/run_on_vm.sh` + `crontab.example` run the identical
  `cycle` / `risk-check` code on a plain Ubuntu `cron`; see
  `docs/vm-runtime-setup.md`. GitHub Actions workflows are kept, `disabled`,
  as a manual fallback (`gh workflow run ...`). No change to trading logic.
- **`POLICY['initial_cash']`: 10,000 → 10 USDT**, at Stanley's request, so the
  paper P&L is denominated in numbers he can read at a glance. This is still
  100% paper trading — no real capital was ever at risk at either scale, so
  this changes the bookkeeping unit, not the risk taken. Position sizing scales
  proportionally (same 10%/20%/0.5% caps), so order sizes are now cents rather
  than hundreds of dollars.
- **Bug fix while touching `core.py`**: `Store.init()` hardcoded
  `peak_equity`/`day_equity`/`last_equity` to `10000.0` instead of reading
  `POLICY['initial_cash']`. Invisible while `initial_cash` was actually 10000;
  would have silently broken drawdown/daily-loss math at any other value.

The v1.0 ledger (2026-09-10T22:21Z → 2026-09-11T02:33Z, ~4h, one live Kimi
BUY on BNB-USDT) is discarded; records live only in git history. `policy_hash`
changed with `initial_cash`, so the old ledger would have been rejected by
`RiskGateway` regardless.

## v1.0 — live start 2026-09-10T22:21:08Z (ends 2026-10-10T22:21:08Z)

Kimi K3 enabled (`TRADING_MODEL=nvidia`, `NVIDIA_API_KEY` repo secret). The
2026-09-09T20:50Z → 2026-09-10T22:21Z ledger was a HOLD-only infrastructure
shakeout (GitHub `schedule:` reliability, projections, commit loop); it is
discarded and its records live only in git history.
`state/experiment.sqlite3` was re-`init`ed so the 30-day clock counts from the
first Kimi-driven cycle (`experiment-2026-09-10T22Z`, request
`chatcmpl-a190904b`). Nothing about the strategy conditions changed, so this is
still v1.0, not a new version.

Bring-up fix: NIM rejected the initial call — `top_p` is immutable for Kimi K3
and must be `0.95`; the client now sends `top_p=0.95`, `temperature=1.0` (the
model's documented single-step profile) and surfaces the HTTP status + body on
any future model failure.

Architecture realignment (unchanged from the shakeout):

- Runtime moved to **GitHub Actions** (`.github/workflows/trading-cycle.yml`),
  one cycle every 4h UTC + manual dispatch. Cowork is no longer the runtime.
- **Kimi K3** via NVIDIA NIM added as the trading agent behind a replaceable
  `trading_bot/model/` interface. Agent returns ranked candidates only
  (`schemas/agent-output.schema.json`); it never sizes orders or executes.
- Deterministic **RiskGateway / POLICY unchanged**. New `trading_bot/cycle.py`
  adapter computes every notional in Python from `target_allocation`, clamped to
  the order / position / planned-loss caps — this is the RESIZE path. Every
  resize / rejection is written to `logs/decisions/`.
- Universe expanded 3 → 5: added **BNB-USDT, XRP-USDT** (`core.SYMBOLS`, schemas).
- State: git-tracked `state/*.json`, `logs/`, `trades/trades.csv` projections
  alongside the committed `state/experiment.sqlite3` ledger.
- Benchmarks added (`trading_bot/benchmarks.py`, LLM-free): BTC buy&hold,
  equal-weight, deterministic momentum baseline.
- Deterministic indicators added (`trading_bot/indicators.py`): SMA/RSI/momentum/
  volatility/trend, computed before each model call.
- Broker abstraction added (`trading_bot/broker/`): `PaperBroker` (phase 1 reads;
  RiskGateway still does the fills) and `OKXDemoBroker` (public data works;
  order endpoints double-gated and off).
- Cowork repurposed to **read-only daily/weekly reviewer**; it does not trade,
  and does not modify strategy, prompt, risk parameters or code.

## infra — 2026-09-09

- Added `risk-monitor` workflow: an hourly deterministic safety pass
  (`trading_bot.cycle.run_risk_check`, CLI `risk-check`) that runs a HOLD
  proposal through RiskGateway between the 4-hour Kimi cycles, so stop-loss /
  drawdown / daily-loss exits execute within <= 1h instead of <= 4h. No model,
  no indicators, no benchmark rebalance; `risk-` run_id prefix; light
  `logs/risk/<run_id>.json`. The **trading decision cadence stays 4h** — the
  fixed experiment condition is unchanged, so this is infra, not a version bump.

## infra — template

_(bug-fix entries go here; no version bump)_
