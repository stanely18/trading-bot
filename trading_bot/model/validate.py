"""Stdlib validation for schemas/agent-output.schema.json.

No third-party dependency (mirrors the hand-rolled checks in trading_bot/core.py).
Raises ValueError with a short reason on the first violation.
"""
import math

from ..core import SYMBOLS

REGIMES = ('risk_on', 'risk_off', 'neutral', 'high_volatility', 'unclear')
VIEWS = ('add_risk', 'reduce_risk', 'neutral', 'rotate')
ACTIONS = ('BUY', 'SELL', 'HOLD', 'CLOSE')
_CAND_KEYS = {'symbol', 'action', 'confidence', 'target_allocation',
              'thesis', 'invalidation', 'risk_notes'}


def _text(x, name):
    if not isinstance(x, str) or not 1 <= len(x) <= 2000:
        raise ValueError(name)


def _unit(x, name):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError(name)
    if not 0.0 <= x <= 1.0:
        raise ValueError(name)
    return float(x)


def validate_agent_output(obj):
    """Validate and normalise. Returns the object unchanged on success."""
    if not isinstance(obj, dict) or set(obj) != {'market_regime', 'portfolio_view', 'candidates'}:
        raise ValueError('agent output fields mismatch')
    if obj['market_regime'] not in REGIMES:
        raise ValueError('market_regime')
    if obj['portfolio_view'] not in VIEWS:
        raise ValueError('portfolio_view')
    cands = obj['candidates']
    if not isinstance(cands, list) or len(cands) > len(SYMBOLS):
        raise ValueError('candidates')
    seen = set()
    for c in cands:
        if not isinstance(c, dict) or set(c) != _CAND_KEYS:
            raise ValueError('candidate fields mismatch')
        if c['symbol'] not in SYMBOLS:
            raise ValueError('candidate symbol')
        if c['symbol'] in seen:
            raise ValueError('duplicate candidate symbol')
        seen.add(c['symbol'])
        if c['action'] not in ACTIONS:
            raise ValueError('candidate action')
        _unit(c['confidence'], 'confidence')
        _unit(c['target_allocation'], 'target_allocation')
        _text(c['thesis'], 'thesis')
        _text(c['invalidation'], 'invalidation')
        if not isinstance(c['risk_notes'], list):
            raise ValueError('risk_notes')
        for note in c['risk_notes']:
            _text(note, 'risk_note')
    return obj
