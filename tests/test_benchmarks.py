import unittest

from trading_bot import benchmarks as b

PRICES0 = {'BTC-USDT': 100.0, 'ETH-USDT': 10.0, 'SOL-USDT': 1.0, 'BNB-USDT': 5.0, 'XRP-USDT': 0.5}


class BenchmarkTests(unittest.TestCase):
    def test_init_equities_equal_initial_cash(self):
        st = b.init_state(PRICES0, 10000.0)
        for v in st['equity'].values():
            self.assertAlmostEqual(v, 10000.0, places=6)

    def test_btc_buy_hold_tracks_btc(self):
        st = b.init_state(PRICES0, 10000.0)
        st = b.update(st, {**PRICES0, 'BTC-USDT': 200.0}, None)
        self.assertAlmostEqual(st['equity']['btc_buy_hold'], 20000.0, places=4)

    def test_equal_weight_half_move(self):
        st = b.init_state(PRICES0, 10000.0)
        doubled = {k: v * 2 for k, v in PRICES0.items()}
        st = b.update(st, doubled, None)
        self.assertAlmostEqual(st['equity']['equal_weight'], 20000.0, places=4)

    def test_momentum_goes_to_cash_when_all_negative(self):
        st = b.init_state(PRICES0, 10000.0)
        st = b.update(st, PRICES0, {k: -1.0 for k in PRICES0})
        self.assertAlmostEqual(st['mom_cash'], 10000.0, places=6)
        self.assertAlmostEqual(st['equity']['momentum_baseline'], 10000.0, places=6)

    def test_momentum_concentrates_in_winners(self):
        st = b.init_state(PRICES0, 10000.0)
        mom = {'BTC-USDT': 5.0, 'ETH-USDT': 3.0, 'SOL-USDT': -1.0, 'BNB-USDT': -1.0, 'XRP-USDT': -1.0}
        st = b.update(st, PRICES0, mom)
        self.assertEqual(st['mom_cash'], 0.0)
        self.assertGreater(st['mom_units']['BTC-USDT'], 0)
        self.assertEqual(st['mom_units']['SOL-USDT'], 0)


if __name__ == '__main__':
    unittest.main()
