"""Exchange abstraction.

Phase 1 uses PaperBroker for data reads while RiskGateway performs simulated
fills; no exchange order path is active. Phase 2 can swap in OKXDemoBroker
(OKX demo / x-simulated-trading only) without changing cycle or risk code.
Live trading is out of scope and intentionally not implemented.
"""
from .base import Broker, BrokerError, Order
from .paper import PaperBroker
from .okx_demo import OKXDemoBroker

__all__ = ['Broker', 'BrokerError', 'Order', 'PaperBroker', 'OKXDemoBroker']
