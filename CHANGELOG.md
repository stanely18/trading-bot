# Experiment changelog

Any change that affects strategy conditions must be recorded here **and** in
`state/experiment.json` (`changelog[]`), with the experiment version bumped.
Technical bug fixes that do not change strategy conditions are listed under a
dated "infra" entry and do not bump the version. During a live 30-day run the
fixed conditions are: Kimi system prompt, enforced POLICY, universe, cadence.

## v1.0 — baseline (not yet started)

Architecture realignment. No live run has begun; the 30-day clock starts when
`state/experiment.sqlite3` is initialised and committed.

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

## infra — YYYY-MM-DD

_(bug-fix entries go here; no version bump)_
