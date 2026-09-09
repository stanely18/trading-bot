import json
import tempfile
import unittest
from pathlib import Path

from trading_bot.core import Store, SYMBOLS
from trading_bot.cycle import run_cycle
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
        for rel in ('state/portfolio.json', 'state/risk_state.json', 'state/agent_state.json',
                    'state/experiment.json', 'logs/decisions/slot-1.json',
                    'logs/workflow/slot-1.json', 'trades/trades.csv'):
            self.assertTrue((self.root / rel).exists(), rel)
        dec = json.loads((self.root / 'logs/decisions/slot-1.json').read_text())
        self.assertEqual(dec['proposal']['action'], 'BUY')
        self.assertEqual(dec['proposal']['notional'], 1000.0)          # 10% order cap, not 40%
        self.assertEqual(dec['adapter']['chosen']['raw_notional'], 4000.0)
        self.assertEqual(dec['agent']['request_id'], 'req-slot-1')
        exp = json.loads((self.root / 'state/experiment.json').read_text())
        self.assertEqual(exp['experiment_version'], 'v1.0')
        self.assertIn('benchmarks', exp)
        self.assertEqual(len(exp['changelog']), 1)
        rows = (self.root / 'trades/trades.csv').read_text().strip().splitlines()
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
        self.assertFalse((self.root / 'trades/trades.csv').exists())

    def test_no_model_holds(self):
        out = self.run_it(None)
        self.assertEqual(out['status'], 'held')

    def test_missing_state_raises(self):
        with self.assertRaises(RuntimeError):
            run_cycle(str(self.root / 'nope.sqlite3'), 'x', model_client=None, root=str(self.root),
                      now_ms_fn=lambda: T, market_fn=mk_market, candles_fn=mk_candles)


if __name__ == '__main__':
    unittest.main()
