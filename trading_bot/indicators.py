"""Deterministic technical indicators computed from OKX candles.

Pure functions, standard library only. Output is context for the trading agent
and for the momentum benchmark; it never makes or gates a trading decision.
"""
import math


def sma(values, n):
    if n <= 0 or len(values) < n:
        return None
    return sum(values[-n:]) / n


def ema(values, n):
    if n <= 0 or len(values) < n:
        return None
    k = 2 / (n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(-n, 0):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_gain, avg_loss = gains / n, losses / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1 + rs)


def momentum(closes, n):
    """Percent change over the last n bars."""
    if len(closes) < n + 1 or closes[-n - 1] == 0:
        return None
    return (closes[-1] / closes[-n - 1] - 1.0) * 100.0


def realized_vol(closes, n=20):
    """Sample stdev of log returns over the last n bars, in percent."""
    if len(closes) < n + 1:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(-n, 0) if closes[i - 1] > 0]
    if len(rets) < 2:
        return None
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * 100.0


def summarize(candles):
    """One symbol's indicator snapshot from oldest-first candle rows."""
    closes = [c[4] for c in candles]
    last = closes[-1] if closes else None
    s20, s50 = sma(closes, 20), sma(closes, 50)
    trend = 'flat'
    if s20 is not None and s50 is not None:
        if last > s20 > s50:
            trend = 'up'
        elif last < s20 < s50:
            trend = 'down'
    return {
        'last': last,
        'sma_20': s20,
        'sma_50': s50,
        'rsi_14': rsi(closes, 14),
        'mom_10': momentum(closes, 10),
        'mom_30': momentum(closes, 30),
        'vol_20': realized_vol(closes, 20),
        'trend': trend,
    }


def regime_hint(per_symbol):
    """Rough breadth label from per-symbol trends. Advisory context only."""
    trends = [v.get('trend') for v in per_symbol.values()]
    ups = trends.count('up')
    downs = trends.count('down')
    total = len(trends) or 1
    if ups / total >= 0.6:
        return 'risk_on'
    if downs / total >= 0.6:
        return 'risk_off'
    vols = [v.get('vol_20') for v in per_symbol.values() if v.get('vol_20') is not None]
    if vols and sum(vols) / len(vols) >= 5.0:
        return 'high_volatility'
    return 'neutral'
