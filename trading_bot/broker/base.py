"""Broker contract. Data reads plus a narrow execution surface.

Callers pass symbol + side + base-asset quantity that the deterministic risk
engine has already sized and approved. A broker never sizes orders, never
overrides risk limits, and never holds deployment credentials beyond the
exchange API key it needs.
"""
from abc import ABC, abstractmethod


class BrokerError(RuntimeError):
    """Any broker failure: disabled execution, missing credentials, transport
    error, exchange rejection. Never partially applied without a raised error."""


class Order(dict):
    """Result of place_order / close_position: broker_order_id, symbol, side,
    qty, avg_price, fee, status ('filled' | 'rejected' | 'pending'), raw."""


class Broker(ABC):
    name = 'unset'
    can_execute = False  # True only for a broker wired to a real order endpoint

    @abstractmethod
    def get_balance(self) -> dict:
        """Quote-currency (USDT) balance: {'currency': 'USDT', 'available': float, 'total': float}."""

    @abstractmethod
    def get_positions(self) -> dict:
        """Open spot positions keyed by symbol: {symbol: {'qty': float, 'avg_price': float}}."""

    @abstractmethod
    def get_ticker(self, symbol: str) -> dict:
        """{'symbol', 'price', 'ts_ms', 'source'} for one symbol."""

    @abstractmethod
    def get_candles(self, symbol: str, bar: str = '1H', limit: int = 100) -> list:
        """Oldest-first list of [ts_ms, open, high, low, close, volume] floats."""

    @abstractmethod
    def place_order(self, symbol: str, side: str, qty: float, client_id: str) -> Order:
        """Spot market order for an already-sized, already-approved quantity.
        `client_id` is a deterministic idempotency key (experiment + slot + symbol)."""

    @abstractmethod
    def cancel_order(self, symbol: str, broker_order_id: str) -> dict:
        ...

    @abstractmethod
    def close_position(self, symbol: str, client_id: str) -> Order:
        """Flatten the whole spot position in `symbol` at market."""
