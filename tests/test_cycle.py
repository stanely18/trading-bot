import json
import tempfile
import unittest
from pathlib import Path

from trading_bot.core import DEFAULT_POLICY, POLICY, Store, SYMBOLS, load_policy
from trading_bot.cycle import EXPERIMENT_VERSION, run_cycle, run_risk_check, size_and_select
from trading_bot.model import ModelResponse

T = 1788998400000
PRICES = [40000.0, 2500.0, 100.0, 600.0, 0.5]


def mk_market(t=T):
    return {s: dict(symbol=s, price=p, ts_ms=t, source='fixture')
            for s, p in zip(SYMBOLS, PRICES)}


def mk_candles(sym, **kw):
    return [[i * 3600000, 100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i, 1.0] for i in range(1, 130)]


class FakeModel:
    provider = 'fake'

    def __init__(self, output):
        self.output = output
        self.calls = 0

    def evaluate(self, req):
        self.calls += 1
        return ModelResponse(request_id='req-' + req['request_id'], provider='fake', model='fake-1',
                             snapshot_hash=req['snapshot_hash'], output=self.output,
                             usage={'total_tokens': 1}, latency_ms=5)


class BrokenModel:
    def evaluate(self, req):
        raise AssertionError('model must not be called on an idempotent replay')


BUY_BIG = {'market_regime': 'risk_on', 'portfolio_view': 'add_risk', 'candidates': [
    {'symbol': 'ETH-USDT', 'action': 'BUY', 'confidence': 0.9, 'target_allocation': 0.40,
     'thesis': 'momentum breakout', 'invalidation': 'below 20d sma', 'risk_notes': ['vol']}]}
ALL_HOLD = {'market_regime': 'neutral', 'portfolio_view': 'neutral', 'candidates': []}


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'state' / 'exp.sqlite3'
        Store(self.db).init(T)

    def run_it(self, model, run_id='slot-1'):
        return run_cycle(str(self.db), run_id, model_client=model, root=str(self.root),
                         now_ms_fn=lambda: T, market_fn=mk_market, candles_fn=mk_candles)

    def test_resize_buy_and_projections(self):
        out = self.run_it(FakeModel(BUY_BIG))
        self.assertEqual(out['status'], 'filled')
        self.assertEqual(out['decision'], 'resized')
        for rel in ('state/baseline/portfolio.json', 'state/baseline/risk_state.json', 'state/baseline/agent_state.json',
                    'state/baseline/experiment.json', 'logs/decisions/slot-1.json',
                    'logs/workflow/slot-1.json', 'trades/baseline.csv'):
            self.assertTrue((self.root / rel).exists(), rel)
        dec = json.loads((self.root / 'logs/decisions/slot-1.json').read_text())
        self.assertEqual(dec['proposal']['action'], 'BUY')
        # 10% order cap binds, not the 40% Kimi asked for
        self.assertAlmostEqual(dec['proposal']['notional'], round(POLICY['initial_cash']*POLICY['max_order_fraction'], 2), places=2)
        self.assertAlmostEqual(dec['adapter']['chosen']['raw_notional'], round(POLICY['initial_cash']*.40, 2), places=2)
        self.assertEqual(dec['agent']['request_id'], 'req-slot-1')
        exp = json.loads((self.root / 'state/baseline/experiment.json').read_text())
        self.assertEqual(exp['experiment_version'], EXPERIMENT_VERSION)
        self.assertIn('benchmarks', exp)
        self.assertEqual(len(exp['changelog']), 1)
        rows = (self.root / 'trades/baseline.csv').read_text().strip().splitlines()
        self.assertEqual(rows[0].split(',')[0], 'run_id')
        self.assertEqual(rows[1].split(',')[3], 'BUY')

    def test_idempotent_replay_does_not_call_model(self):
        first = self.run_it(FakeModel(BUY_BIG))
        again = self.run_it(BrokenModel())
        self.assertEqual(again['revision'], first['revision'])
        self.assertEqual(again['decision'], 'replay')
        self.assertEqual(len(Store(self.db).records()), 1)

    def test_all_hold_writes_no_trades(self):
        out = self.run_it(FakeModel(ALL_HOLD))
        self.assertEqual(out['status'], 'held')
        self.assertEqual(out['decision'], 'hold')
        self.assertFalse((self.root / 'trades/baseline.csv').exists())

    def test_no_model_holds(self):
        out = self.run_it(None)
        self.assertEqual(out['status'], 'held')

    def test_missing_state_raises(self):
        with self.assertRaises(RuntimeError):
            run_cycle(str(self.root / 'nope.sqlite3'), 'x', model_client=None, root=str(self.root),
                      now_ms_fn=lambda: T, market_fn=mk_market, candles_fn=mk_candles)


class RiskCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'state' / 'exp.sqlite3'
        Store(self.db).init(T)

    def test_hold_writes_risk_log_not_decisions(self):
        out = run_risk_check(str(self.db), 'risk-2026-09-09T21Z', root=str(self.root),
                             now_ms_fn=lambda: T, market_fn=mk_market)
        self.assertEqual(out['kind'], 'risk_check')
        self.assertEqual(out['status'], 'held')
        self.assertEqual(out['risk_exits'], [])
        self.assertTrue((self.root / 'logs/risk/risk-2026-09-09T21Z.json').exists())
        self.assertTrue((self.root / 'state/baseline/portfolio.json').exists())
        self.assertFalse((self.root / 'logs/decisions/risk-2026-09-09T21Z.json').exists())
        self.assertFalse((self.root / 'trades/baseline.csv').exists())
        self.assertFalse((self.root / 'state/baseline/agent_state.json').exists())  # untouched by risk check

    def test_executes_stop_loss_between_trading_cycles(self):
        # trading cycle buys ETH, then price falls below the 2% stop; the hourly
        # risk check must flatten it without any model call.
        run_cycle(str(self.db), 'slot-a', model_client=FakeModel(BUY_BIG), root=str(self.root),
                  now_ms_fn=lambda: T, market_fn=mk_market, candles_fn=mk_candles)
        self.assertIn('ETH-USDT', Store(self.db).read()['positions'])
        crash = {s: dict(symbol=s, price=(p * 0.90 if s == 'ETH-USDT' else p), ts_ms=T, source='fixture')
                 for s, p in zip(SYMBOLS, PRICES)}
        out = run_risk_check(str(self.db), 'risk-x', root=str(self.root),
                             now_ms_fn=lambda: T, market_fn=lambda: crash)
        self.assertTrue(out['risk_exits'])
        self.assertEqual(out['risk_exits'][0]['side'], 'SELL')
        self.assertNotIn('ETH-USDT', Store(self.db).read()['positions'])
        rows = (self.root / 'trades/baseline.csv').read_text().strip().splitlines()
        self.assertEqual(rows[-1].split(',')[0], 'risk-x')

    def test_idempotent_replay(self):
        run_risk_check(str(self.db), 'risk-r', root=str(self.root),
                       now_ms_fn=lambda: T, market_fn=mk_market)
        rev = Store(self.db).read()['revision']
        run_risk_check(str(self.db), 'risk-r', root=str(self.root),
                       now_ms_fn=lambda: T, market_fn=mk_market)
        self.assertEqual(Store(self.db).read()['revision'], rev)
        self.assertEqual(len(Store(self.db).records()), 1)


class SizeAndSelectPolicyTests(unittest.TestCase):
    """size_and_select's policy threading and leverage field, in isolation."""
    def setUp(self):
        self.market = mk_market()
        self.portfolio = {'cash': DEFAULT_POLICY['initial_cash'], 'positions': {}}

    def test_omitted_policy_matches_explicit_default_policy(self):
        p_omitted, _ = size_and_select(BUY_BIG, self.portfolio, self.market, 'r1', T, 0)
        p_explicit, _ = size_and_select(BUY_BIG, self.portfolio, self.market, 'r1', T, 0, DEFAULT_POLICY)
        self.assertEqual(p_omitted, p_explicit)

    def test_aggressive_margin_matches_baseline_but_carries_leverage_field(self):
        base_p, _ = size_and_select(BUY_BIG, self.portfolio, self.market, 'r2', T, 0, DEFAULT_POLICY)
        agg_p, _ = size_and_select(BUY_BIG, self.portfolio, self.market, 'r3', T, 0, load_policy('aggressive'))
        self.assertEqual(base_p['notional'], agg_p['notional'])  # margin sizing is leverage-agnostic
        self.assertNotIn('leverage', base_p)
        self.assertEqual(agg_p['leverage'], 5)

    def test_conservative_halves_the_sized_notional(self):
        base_p, _ = size_and_select(BUY_BIG, self.portfolio, self.market, 'r4', T, 0, DEFAULT_POLICY)
        cons_p, _ = size_and_select(BUY_BIG, self.portfolio, self.market, 'r5', T, 0, load_policy('conservative'))
        self.assertAlmostEqual(cons_p['notional'], base_p['notional'] / 2)
        self.assertNotIn('leverage', cons_p)


if __name__ == '__main__':
    unittest.main()
