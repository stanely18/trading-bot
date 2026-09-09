"""Read-only broker view over the paper portfolio.

Phase 1: the cycle uses this for balance/position/market reads, and RiskGateway
performs the simulated fills inside its atomic transaction. Execution methods
raise on purpose so nothing can route a "real" order in paper mode.
"""
from .base import Broker, BrokerError, Order
from ..market import fetch, fetch_candles


class PaperBroker(Broker):
    name = 'paper'
    can_execute = False

    def __init__(self, portfolio: dict, market_snapshot: dict | None = None):
        self._pf = portfolio
        self._market = market_snapshot

    def _quotes(self):
        if self._market is None:
            self._market = fetch()
        return self._market

    def get_balance(self) -> dict:
        return {'currency': 'USDT', 'available': float(self._pf['cash']), 'total': float(self._pf['cash'])}

    def get_positions(self) -> dict:
        return {s: {'qty': float(p['qty']), 'avg_price': float(p['entry_price'])}
                for s, p in self._pf.get('positions', {}).items()}

    def get_ticker(self, symbol: str) -> dict:
        return self._quotes()[symbol]

    def get_candles(self, symbol: str, bar: str = '1H', limit: int = 100) -> list:
        return fetch_candles(symbol, bar=bar, limit=limit)

    def place_order(self, symbol, side, qty, client_id) -> Order:
        raise BrokerError('paper mode: fills are executed by RiskGateway, not the broker')

    def cancel_order(self, symbol, broker_order_id) -> dict:
        raise BrokerError('paper mode: no exchange orders exist to cancel')

    def close_position(self, symbol, client_id) -> Order:
        raise BrokerError('paper mode: exits are executed by RiskGateway, not the broker')
