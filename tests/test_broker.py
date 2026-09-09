import os
import unittest

from trading_bot.broker import PaperBroker, OKXDemoBroker, BrokerError

_CRED_KEYS = ('OKX_API_KEY', 'OKX_DEMO_API_KEY', 'OKX_SECRET_KEY', 'OKX_DEMO_SECRET_KEY',
             'OKX_PASSPHRASE', 'OKX_DEMO_PASSPHRASE')

PF = {
    'cash': 8000.0,
    'positions': {'BTC-USDT': {'qty': 0.05, 'entry_price': 40000.0, 'stop_price': 39200.0}},
}
MARKET = {s: {'symbol': s, 'price': p, 'ts_ms': 1, 'source': 'fixture'}
          for s, p in [('BTC-USDT', 42000.0), ('ETH-USDT', 2500.0), ('SOL-USDT', 100.0),
                       ('BNB-USDT', 600.0), ('XRP-USDT', 0.5)]}


class PaperBrokerTests(unittest.TestCase):
    def setUp(self):
        self.b = PaperBroker(PF, MARKET)

    def test_balance_and_positions(self):
        self.assertEqual(self.b.get_balance(), {'currency': 'USDT', 'available': 8000.0, 'total': 8000.0})
        self.assertEqual(self.b.get_positions()['BTC-USDT']['qty'], 0.05)

    def test_ticker_from_snapshot(self):
        self.assertEqual(self.b.get_ticker('ETH-USDT')['price'], 2500.0)

    def test_execution_methods_raise(self):
        for call in (lambda: self.b.place_order('BTC-USDT', 'BUY', 0.001, 'c1'),
                     lambda: self.b.cancel_order('BTC-USDT', 'x'),
                     lambda: self.b.close_position('BTC-USDT', 'c1')):
            with self.assertRaises(BrokerError):
                call()

    def test_cannot_execute_flag(self):
        self.assertFalse(PaperBroker.can_execute)


class OKXDemoBrokerGateTests(unittest.TestCase):
    def test_orders_disabled_by_default(self):
        b = OKXDemoBroker()
        self.assertFalse(b.can_execute)
        with self.assertRaises(BrokerError):
            b.place_order('BTC-USDT', 'BUY', 0.001, 'c1')
        with self.assertRaises(BrokerError):
            b.close_position('BTC-USDT', 'c1')

    def test_allow_orders_still_needs_env(self):
        # allow_orders=True but env flag not set -> stays disabled
        b = OKXDemoBroker(allow_orders=True)
        self.assertFalse(b.can_execute)

    def test_account_read_without_creds_raises(self):
        if any(os.environ.get(k) for k in _CRED_KEYS):
            self.skipTest('OKX credentials present in environment')
        b = OKXDemoBroker()
        with self.assertRaises(BrokerError):
            b.get_balance()


if __name__ == '__main__':
    unittest.main()
