import unittest

from trading_bot import indicators as ind


def candles(closes):
    return [[i * 3600000, c, c, c, c, 1.0] for i, c in enumerate(closes)]


class IndicatorTests(unittest.TestCase):
    def test_sma_and_none_when_short(self):
        self.assertEqual(ind.sma([1, 2, 3, 4], 2), 3.5)
        self.assertIsNone(ind.sma([1, 2], 5))

    def test_rsi_all_gains_is_100(self):
        self.assertEqual(ind.rsi(list(range(1, 40)), 14), 100.0)

    def test_rsi_midrange(self):
        closes = [10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10]
        r = ind.rsi(closes, 14)
        self.assertTrue(0 < r < 100)

    def test_momentum_pct(self):
        self.assertAlmostEqual(ind.momentum([100, 110], 1), 10.0)
        self.assertIsNone(ind.momentum([100], 5))

    def test_summarize_trend_up(self):
        s = ind.summarize(candles([i for i in range(1, 80)]))
        self.assertEqual(s['trend'], 'up')
        self.assertEqual(s['last'], 79)

    def test_regime_hint(self):
        up = {'A': {'trend': 'up', 'vol_20': 1}, 'B': {'trend': 'up', 'vol_20': 1},
              'C': {'trend': 'flat', 'vol_20': 1}}
        self.assertEqual(ind.regime_hint(up), 'risk_on')
        down = {'A': {'trend': 'down'}, 'B': {'trend': 'down'}, 'C': {'trend': 'down'}}
        self.assertEqual(ind.regime_hint(down), 'risk_off')


if __name__ == '__main__':
    unittest.main()
