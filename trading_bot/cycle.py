"""One market/trading cycle for the GitHub Actions runner.

Stateless process, git-backed state. Steps:
  1  load portfolio state          8  size + select in Python (RESIZE point)
  2  load risk state               9  submit to RiskGateway (paper fill)
  3  fetch market                 10  read portfolio after
  4  deterministic indicators     11  write state/*.json projections
  5  build model context          12  write logs/decisions + trades.csv
  6  call trading agent (Kimi)    13  write logs/workflow health record
  7  validate agent JSON

The deterministic RiskGateway (trading_bot/core.py) remains the only code that
moves balances. The model only ranks candidates; Python computes every notional.
A re-run of the same run_id is idempotent: the stored proposal and market are
replayed and the model is not called again (experiment integrity + no double
fill).
"""
import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from .core import POLICY, RiskGateway, SYMBOLS, Store, equity, now_ms
from .market import fetch, fetch_candles
from . import benchmarks, indicators
from .model import ModelError
from .model.validate import validate_agent_output

EXPERIMENT_VERSION = 'v1.1'
_PROMPT_PATH = Path(__file__).resolve().parent.parent / 'prompts' / 'kimi-system.md'


def _utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace('+00:00', 'Z')


def _atomic_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n')
    tmp.replace(path)


def _floor2(x):
    return math.floor(x * 100) / 100


def build_context(portfolio, market, ind, nav):
    caps = {k: POLICY[k] for k in ('max_order_fraction', 'max_position_fraction', 'max_positions',
                                   'daily_loss', 'max_drawdown', 'stop_fraction',
                                   'max_planned_loss_fraction', 'max_daily_orders',
                                   'fee_bps', 'slippage_bps')}
    return {
        'experiment_version': EXPERIMENT_VERSION,
        'mode': 'paper',
        'universe': list(SYMBOLS),
        'policy_caps': caps,
        'nav_usdt': round(nav, 2),
        'cash_usdt': round(portfolio['cash'], 2),
        'positions': {s: {'qty': p['qty'], 'entry_price': p['entry_price'],
                          'stop_price': p['stop_price'],
                          'value_usdt': round(p['qty'] * market[s]['price'], 2)}
                      for s, p in portfolio['positions'].items()},
        'halted': portfolio['halted'],
        'daily_orders_used': portfolio['daily_orders'],
        'market': {s: {'price': market[s]['price'], 'ts_ms': market[s]['ts_ms']} for s in SYMBOLS},
        'indicators': ind,
        'regime_hint': indicators.regime_hint(ind),
    }


def size_and_select(agent_output, portfolio, market, run_id, created_ms, revision):
    """Pick at most one actionable candidate and size it in Python.

    Returns (proposal, meta). `meta.decision` is one of: hold, sized, resized,
    skipped_*. The model's target_allocation is advisory; the returned notional
    is clamped to order / position / planned-loss caps."""
    nav = equity(portfolio, market)
    base = dict(id=run_id, created_ms=created_ms, expected_revision=revision,
                agent='kimi-k3', symbol='BTC-USDT')
    hold = {**base, 'action': 'HOLD', 'notional': 0, 'reason': 'no actionable candidate'}
    meta = {'nav': nav, 'decision': 'hold', 'considered': [], 'chosen': None}

    if not agent_output:
        return hold, meta

    plr = POLICY['stop_fraction'] + 2 * (POLICY['fee_bps'] + POLICY['slippage_bps']) / 10000
    cands = sorted(agent_output['candidates'],
                   key=lambda c: (-c['confidence'], c['symbol']))
    for c in cands:
        sym, act = c['symbol'], c['action']
        rec = {'symbol': sym, 'action': act, 'confidence': c['confidence'],
               'target_allocation': c['target_allocation']}
        held = portfolio['positions'].get(sym)
        if act in ('HOLD',):
            rec['result'] = 'noop'
            meta['considered'].append(rec)
            continue
        if act == 'BUY':
            if held:
                rec['result'] = 'skipped_pyramiding'
                meta['considered'].append(rec)
                continue
            raw = c['target_allocation'] * nav
            capped = min(raw,
                         POLICY['max_order_fraction'] * nav,
                         POLICY['max_position_fraction'] * nav,
                         nav * POLICY['max_planned_loss_fraction'] / plr)
            n = _floor2(capped)
            if n <= 0:
                rec['result'] = 'skipped_zero_size'
                meta['considered'].append(rec)
                continue
            reason = (c.get('thesis') or 'model buy')[:2000]
            proposal = {**base, 'symbol': sym, 'action': 'BUY', 'notional': n, 'reason': reason}
            meta['decision'] = 'resized' if n < raw - 1e-9 else 'sized'
            rec['result'] = meta['decision']
            rec['raw_notional'] = round(raw, 2)
            rec['sized_notional'] = n
            meta['considered'].append(rec)
            meta['chosen'] = rec
            return proposal, meta
        if act in ('SELL', 'CLOSE'):
            if not held:
                rec['result'] = 'skipped_no_position'
                meta['considered'].append(rec)
                continue
            cur_val = held['qty'] * market[sym]['price']
            if act == 'CLOSE':
                n = _floor2(cur_val)
            else:
                target_val = c['target_allocation'] * nav
                n = _floor2(max(0.0, cur_val - target_val))
                if n <= 0:
                    rec['result'] = 'skipped_zero_size'
                    meta['considered'].append(rec)
                    continue
            n = min(n, _floor2(cur_val))
            if n <= 0:
                rec['result'] = 'skipped_zero_size'
                meta['considered'].append(rec)
                continue
            reason = (c.get('thesis') or 'model exit')[:2000]
            proposal = {**base, 'symbol': sym, 'action': 'SELL', 'notional': n, 'reason': reason}
            meta['decision'] = 'sized'
            rec['result'] = 'sized'
            rec['sized_notional'] = n
            meta['considered'].append(rec)
            meta['chosen'] = rec
            return proposal, meta
    return hold, meta


def _pnl(portfolio, market):
    nav = equity(portfolio, market)
    unrealized = sum(p['qty'] * (market[s]['price'] - p['entry_price'])
                     for s, p in portfolio['positions'].items())
    total = nav - POLICY['initial_cash']
    return {'nav': round(nav, 4), 'total_pnl': round(total, 4),
            'unrealized_pnl': round(unrealized, 4), 'realized_pnl': round(total - unrealized, 4)}


def _risk_state(portfolio, market):
    nav = equity(portfolio, market)
    return {
        'revision': portfolio['revision'],
        'halted': portfolio['halted'],
        'daily_orders': portfolio['daily_orders'],
        'peak_equity': portfolio['peak_equity'],
        'last_equity': portfolio['last_equity'],
        'day_equity': portfolio['day_equity'],
        'nav': round(nav, 4),
        'drawdown_pct': round((1 - nav / portfolio['peak_equity']) * 100, 4) if portfolio['peak_equity'] else 0.0,
        'daily_loss_pct': round((1 - nav / portfolio['day_equity']) * 100, 4) if portfolio['day_equity'] else 0.0,
        'policy_hash': portfolio['policy_hash'],
    }


def _append_trades(csv_path: Path, run_id, recorded_ms, fills):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    with csv_path.open('a', newline='') as f:
        w = csv.writer(f)
        if new:
            w.writerow(['run_id', 'recorded_utc', 'symbol', 'side', 'qty', 'price', 'fee', 'reason'])
        for fl in fills:
            w.writerow([run_id, _utc(recorded_ms), fl['symbol'], fl['side'],
                        repr(fl['qty']), repr(fl['price']), repr(fl['fee']), fl['reason']])


def run_cycle(db, run_id, *, model_client=None, root='.', deadline_ms=40000,
              now_ms_fn=now_ms, market_fn=fetch, candles_fn=fetch_candles,
              candle_bar='1H', candle_limit=120):
    root = Path(root)
    started = time.monotonic()
    health = {'run_id': run_id, 'experiment_version': EXPERIMENT_VERSION,
              'started_utc': _utc(now_ms_fn()), 'steps': {}, 'errors': []}
    store = Store(db)
    portfolio_before = store.read()  # step 1 (raises if state missing: never auto-init)
    health['steps']['load_state'] = 'ok'

    replay = next((r for r in store.records() if r['run_id'] == run_id), None)

    t = now_ms_fn()
    if replay:
        market = replay['market']
        proposal = replay['proposal']
        adapter_meta = {'decision': 'replay', 'note': 'idempotent re-run; model not called'}
        agent_record = {'status': 'skipped_replay'}
        ind = {}
        health['steps']['market'] = health['steps']['indicators'] = 'replay'
        health['steps']['model'] = 'replay'
    else:
        try:
            market = market_fn()  # step 3
            health['steps']['market'] = 'ok'
        except Exception as e:
            health['steps']['market'] = 'failed'
            health['errors'].append(f'market:{type(e).__name__}:{e}')
            _atomic_json(root / 'logs' / 'workflow' / f'{run_id}.json',
                         {**health, 'result': 'aborted_no_market',
                          'duration_ms': int((time.monotonic() - started) * 1000)})
            raise

        ind = {}
        for s in SYMBOLS:  # step 4
            try:
                ind[s] = indicators.summarize(candles_fn(s, bar=candle_bar, limit=candle_limit))
            except Exception as e:
                ind[s] = {'error': type(e).__name__}
                health['errors'].append(f'candles:{s}:{type(e).__name__}')
        health['steps']['indicators'] = 'ok' if any('error' not in v for v in ind.values()) else 'degraded'

        nav_before = equity(portfolio_before, market)
        context = build_context(portfolio_before, market, ind, nav_before)  # step 5

        agent_output = None
        agent_record = {'status': 'hold_default'}
        if model_client is not None:  # step 6
            req = {'request_id': run_id, 'snapshot_hash': f'{portfolio_before["revision"]}:{t}',
                   'system_prompt': _PROMPT_PATH.read_text(), 'context': context,
                   'deadline_ms': deadline_ms}
            try:
                resp = model_client.evaluate(req)
                validate_agent_output(resp['output'])  # step 7, defensive re-check
                agent_output = resp['output']
                agent_record = {'status': 'ok', 'provider': resp['provider'], 'model': resp['model'],
                                'request_id': resp['request_id'], 'latency_ms': resp['latency_ms'],
                                'usage': resp['usage'], 'output': agent_output}
                health['steps']['model'] = 'ok'
            except ModelError as e:
                agent_record = {'status': 'model_error', 'error': str(e)}
                health['steps']['model'] = 'error_hold_fallback'
                health['errors'].append(f'model:{e}')
        else:
            health['steps']['model'] = 'disabled_hold'

        proposal, adapter_meta = size_and_select(  # step 8
            agent_output, portfolio_before, market, run_id, t, portfolio_before['revision'])

    try:
        result = RiskGateway(store).run(proposal, market, t)  # step 9
        health['steps']['risk_gateway'] = result['status']
    except Exception as e:
        health['steps']['risk_gateway'] = 'failed'
        health['errors'].append(f'risk_gateway:{type(e).__name__}:{e}')
        _atomic_json(root / 'logs' / 'workflow' / f'{run_id}.json',
                     {**health, 'result': 'risk_gateway_error',
                      'duration_ms': int((time.monotonic() - started) * 1000)})
        raise

    portfolio_after = store.read()  # step 10
    pnl = _pnl(portfolio_after, market)

    # step 11: state projections
    _atomic_json(root / 'state' / 'portfolio.json', portfolio_after)
    _atomic_json(root / 'state' / 'risk_state.json', _risk_state(portfolio_after, market))

    consec = 0
    agent_state_path = root / 'state' / 'agent_state.json'
    if agent_state_path.exists():
        try:
            consec = json.loads(agent_state_path.read_text()).get('consecutive_holds', 0)
        except Exception:
            consec = 0
    consec = consec + 1 if result['status'] == 'held' else 0
    _atomic_json(agent_state_path, {
        'last_run_id': run_id, 'last_recorded_utc': _utc(result['recorded_ms']),
        'last_status': result['status'], 'last_reason': result['reason'],
        'consecutive_holds': consec,
        'agent': agent_record.get('status'),
        'market_regime': (agent_record.get('output') or {}).get('market_regime'),
        'portfolio_view': (agent_record.get('output') or {}).get('portfolio_view'),
        'model_provider': agent_record.get('provider'),
        'model_name': agent_record.get('model'),
        'model_request_id': agent_record.get('request_id'),
    })

    # benchmarks in experiment.json
    exp_path = root / 'state' / 'experiment.json'
    exp = {}
    if exp_path.exists():
        try:
            exp = json.loads(exp_path.read_text())
        except Exception:
            exp = {}
    prices = {s: market[s]['price'] for s in SYMBOLS}
    bench = exp.get('benchmarks')
    if not bench:
        bench = benchmarks.init_state(prices, POLICY['initial_cash'])
    if not replay:
        bench = benchmarks.update(bench, prices,
                                  {s: (ind.get(s, {}) or {}).get('mom_10') for s in SYMBOLS})
    exp.update({
        'experiment_version': EXPERIMENT_VERSION,
        'mode': 'paper', 'cadence': 'every_4h', 'timezone': 'UTC',
        'universe': list(SYMBOLS),
        'initial_cash_usdt': POLICY['initial_cash'],
        'started_ms': portfolio_after['started_ms'], 'ends_ms': portfolio_after['ends_ms'],
        'policy_hash': portfolio_after['policy_hash'],
        'last_run_id': run_id, 'last_recorded_utc': _utc(result['recorded_ms']),
        'benchmarks': bench,
        'benchmark_vs_strategy': {
            'strategy_nav': pnl['nav'],
            'btc_buy_hold': round(bench['equity']['btc_buy_hold'], 4),
            'equal_weight': round(bench['equity']['equal_weight'], 4),
            'momentum_baseline': round(bench['equity']['momentum_baseline'], 4),
        },
    })
    exp.setdefault('changelog', [
        {'version': EXPERIMENT_VERSION, 'utc': _utc(portfolio_after['started_ms']),
         'change': f'baseline: 5-symbol spot universe, every-4h cadence, Kimi K3 agent, '
                   f'fixed POLICY, initial_cash_usdt={POLICY["initial_cash"]}'}])
    _atomic_json(exp_path, exp)

    # step 12: decision log + trades
    decision = {
        'run_id': run_id, 'experiment_version': EXPERIMENT_VERSION,
        'recorded_utc': _utc(result['recorded_ms']), 'recorded_ms': result['recorded_ms'],
        'revision_before': portfolio_before['revision'], 'revision_after': portfolio_after['revision'],
        'market': market,
        'portfolio_before': portfolio_before,
        'indicators': ind,
        'agent': agent_record,
        'adapter': adapter_meta,
        'proposal': proposal,
        'risk_result': {k: result[k] for k in ('status', 'reason', 'fills', 'equity', 'hash', 'previous_hash')},
        'executed': [f for f in result['fills'] if f['reason'] == 'proposal'],
        'risk_exits': [f for f in result['fills'] if f['reason'] == 'risk_exit'],
        'portfolio_after': portfolio_after,
        'pnl': pnl,
        'errors': health['errors'],
    }
    decision_path = root / 'logs' / 'decisions' / f'{run_id}.json'
    if not (replay and decision_path.exists()):
        # First execution of a slot writes the authoritative record; a later
        # idempotent replay must not overwrite it with a sparser one.
        _atomic_json(decision_path, decision)
    if result['fills'] and not replay:
        _append_trades(root / 'trades' / 'trades.csv', run_id, result['recorded_ms'], result['fills'])

    # step 13: workflow health (+ a dedicated error record when anything degraded)
    health.update({'result': 'ok', 'risk_status': result['status'], 'risk_reason': result['reason'],
                   'fills': len(result['fills']), 'pnl': pnl,
                   'finished_utc': _utc(now_ms_fn()),
                   'duration_ms': int((time.monotonic() - started) * 1000)})
    _atomic_json(root / 'logs' / 'workflow' / f'{run_id}.json', health)
    if health['errors']:
        _atomic_json(root / 'logs' / 'errors' / f'{run_id}.json',
                     {'run_id': run_id, 'recorded_utc': _utc(result['recorded_ms']),
                      'errors': health['errors'], 'steps': health['steps']})
    return {'run_id': run_id, 'status': result['status'], 'reason': result['reason'],
            'fills': result['fills'], 'pnl': pnl, 'decision': adapter_meta.get('decision'),
            'revision': portfolio_after['revision'],
            'model_status': agent_record.get('status'),
            'errors': health['errors']}


def run_risk_check(db, run_id, *, root='.', now_ms_fn=now_ms, market_fn=fetch):
    """Hourly deterministic safety pass between the 4-hour Kimi cycles.

    No model, no indicators, no benchmark rebalance. Fetches trusted market and
    runs a HOLD proposal through RiskGateway, which still executes stop-loss /
    drawdown / daily-loss / expiry exits. Writes light projections and a compact
    logs/risk/<run_id>.json. `run_id` MUST use a distinct prefix (e.g. 'risk-')
    so it never occupies a 4-hour trading slot id.
    """
    root = Path(root)
    started = time.monotonic()
    health = {'run_id': run_id, 'kind': 'risk_check',
              'started_utc': _utc(now_ms_fn()), 'steps': {}, 'errors': []}
    store = Store(db)
    portfolio_before = store.read()  # never auto-init
    health['steps']['load_state'] = 'ok'
    replay = next((r for r in store.records() if r['run_id'] == run_id), None)
    t = now_ms_fn()

    if replay:
        market, proposal = replay['market'], replay['proposal']
        health['steps']['market'] = 'replay'
    else:
        try:
            market = market_fn()
            health['steps']['market'] = 'ok'
        except Exception as e:
            health['steps']['market'] = 'failed'
            health['errors'].append(f'market:{type(e).__name__}:{e}')
            _atomic_json(root / 'logs' / 'workflow' / f'{run_id}.json',
                         {**health, 'result': 'aborted_no_market',
                          'duration_ms': int((time.monotonic() - started) * 1000)})
            raise
        proposal = dict(id=run_id, created_ms=t, expected_revision=portfolio_before['revision'],
                        agent='risk-monitor', action='HOLD', symbol='BTC-USDT', notional=0,
                        reason='hourly deterministic risk check')

    try:
        result = RiskGateway(store).run(proposal, market, t)
        health['steps']['risk_gateway'] = result['status']
    except Exception as e:
        health['steps']['risk_gateway'] = 'failed'
        health['errors'].append(f'risk_gateway:{type(e).__name__}:{e}')
        _atomic_json(root / 'logs' / 'workflow' / f'{run_id}.json',
                     {**health, 'result': 'risk_gateway_error',
                      'duration_ms': int((time.monotonic() - started) * 1000)})
        raise

    portfolio_after = store.read()
    pnl = _pnl(portfolio_after, market)
    exits = [f for f in result['fills'] if f['reason'] != 'proposal']

    _atomic_json(root / 'state' / 'portfolio.json', portfolio_after)
    _atomic_json(root / 'state' / 'risk_state.json', _risk_state(portfolio_after, market))

    record = {
        'run_id': run_id, 'kind': 'risk_check',
        'recorded_utc': _utc(result['recorded_ms']), 'recorded_ms': result['recorded_ms'],
        'revision_before': portfolio_before['revision'], 'revision_after': portfolio_after['revision'],
        'market': {s: {'price': market[s]['price'], 'ts_ms': market[s]['ts_ms']} for s in SYMBOLS},
        'risk_status': result['status'], 'risk_reason': result['reason'],
        'risk_exits': exits, 'halted': portfolio_after['halted'],
        'positions_after': list(portfolio_after['positions']),
        'pnl': pnl, 'hash': result['hash'], 'previous_hash': result['previous_hash'],
        'errors': health['errors'],
    }
    risk_path = root / 'logs' / 'risk' / f'{run_id}.json'
    if not (replay and risk_path.exists()):
        _atomic_json(risk_path, record)
    if exits and not replay:
        _append_trades(root / 'trades' / 'trades.csv', run_id, result['recorded_ms'], result['fills'])

    health.update({'result': 'ok', 'risk_status': result['status'], 'risk_reason': result['reason'],
                   'risk_exits': len(exits), 'pnl': pnl, 'finished_utc': _utc(now_ms_fn()),
                   'duration_ms': int((time.monotonic() - started) * 1000)})
    _atomic_json(root / 'logs' / 'workflow' / f'{run_id}.json', health)
    if health['errors']:
        _atomic_json(root / 'logs' / 'errors' / f'{run_id}.json',
                     {'run_id': run_id, 'recorded_utc': _utc(result['recorded_ms']),
                      'errors': health['errors'], 'steps': health['steps']})
    return {'run_id': run_id, 'kind': 'risk_check', 'status': result['status'],
            'reason': result['reason'], 'risk_exits': exits, 'pnl': pnl,
            'revision': portfolio_after['revision'], 'halted': portfolio_after['halted'],
            'errors': health['errors']}
