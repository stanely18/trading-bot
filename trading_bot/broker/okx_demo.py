"""OKX demo-trading broker (x-simulated-trading: 1 only).

Public market data works with no credentials. Account reads need demo API
credentials (OKX_API_KEY / OKX_SECRET_KEY / OKX_PASSPHRASE, or the OKX_DEMO_*
names). Order endpoints are built but double-gated: they raise unless the broker
is constructed with allow_orders=True AND DEMO_ORDER_EXECUTION_ENABLED=1 in the
environment. There is no live-trading path here by construction.
"""
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from .base import Broker, BrokerError, Order
from ..market import get as _http_get, fetch_candles, BASE
from urllib.request import Request, build_opener, HTTPRedirectHandler

_BASE_ASSET = lambda s: s.split('-')[0]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        raise ValueError('redirect refused')


def _creds():
    def pick(*names):
        for n in names:
            v = os.environ.get(n)
            if v:
                return v
        return None
    key = pick('OKX_API_KEY', 'OKX_DEMO_API_KEY')
    secret = pick('OKX_SECRET_KEY', 'OKX_DEMO_SECRET_KEY')
    phrase = pick('OKX_PASSPHRASE', 'OKX_DEMO_PASSPHRASE')
    return key, secret, phrase


class OKXDemoBroker(Broker):
    name = 'okx_demo'

    def __init__(self, allow_orders=False):
        self._allow_orders = bool(allow_orders) and os.environ.get('DEMO_ORDER_EXECUTION_ENABLED') == '1'
        self.can_execute = self._allow_orders

    # ---- public data (no credentials) ----
    def get_ticker(self, symbol: str) -> dict:
        rows = _http_get('/api/v5/market/ticker?instId=' + symbol)
        if len(rows) != 1 or rows[0]['instId'] != symbol:
            raise BrokerError('unexpected ticker')
        q = rows[0]
        return dict(symbol=symbol, price=float(q['last']), ts_ms=int(q['ts']), source='okx_public')

    def get_candles(self, symbol: str, bar: str = '1H', limit: int = 100) -> list:
        return fetch_candles(symbol, bar=bar, limit=limit)

    # ---- signed account reads ----
    def _signed(self, method: str, path: str, body: str = ''):
        key, secret, phrase = _creds()
        if not (key and secret and phrase):
            raise BrokerError('missing OKX demo credentials')
        stamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        mac = hmac.new(secret.encode(), (stamp + method + path + body).encode(), hashlib.sha256)
        sign = base64.b64encode(mac.digest()).decode()
        headers = {'OK-ACCESS-KEY': key, 'OK-ACCESS-SIGN': sign, 'OK-ACCESS-PASSPHRASE': phrase,
                   'OK-ACCESS-TIMESTAMP': stamp, 'x-simulated-trading': '1',
                   'Content-Type': 'application/json', 'User-Agent': 'trading-bot-poc/0.1'}
        req = Request(BASE + path, data=body.encode() if body else None, method=method, headers=headers)
        with build_opener(_NoRedirect).open(req, timeout=20) as r:
            raw = r.read(2_000_001)
        if len(raw) > 2_000_000:
            raise BrokerError('oversized response')
        data = json.loads(raw)
        if data.get('code') not in ('0', 0):
            raise BrokerError('OKX code ' + str(data.get('code')) + ' ' + str(data.get('msg')))
        return data['data']

    def get_balance(self) -> dict:
        rows = self._signed('GET', '/api/v5/account/balance')
        details = (rows[0].get('details') if rows else []) or []
        usdt = next((d for d in details if d.get('ccy') == 'USDT'), None)
        avail = float(usdt['availBal']) if usdt and usdt.get('availBal') else 0.0
        total = float(usdt['cashBal']) if usdt and usdt.get('cashBal') else avail
        return {'currency': 'USDT', 'available': avail, 'total': total}

    def get_positions(self) -> dict:
        rows = self._signed('GET', '/api/v5/account/balance')
        details = (rows[0].get('details') if rows else []) or []
        wanted = {_BASE_ASSET(s): s for s in ('BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT', 'XRP-USDT')}
        out = {}
        for d in details:
            ccy = d.get('ccy')
            if ccy in wanted and float(d.get('cashBal') or 0) > 0:
                out[wanted[ccy]] = {'qty': float(d['cashBal']), 'avg_price': 0.0}
        return out

    # ---- order surface (double-gated, demo only) ----
    def _guard(self):
        if not self._allow_orders:
            raise BrokerError('demo order execution disabled '
                              '(need allow_orders=True and DEMO_ORDER_EXECUTION_ENABLED=1)')

    def place_order(self, symbol, side, qty, client_id) -> Order:
        self._guard()
        body = json.dumps({'instId': symbol, 'tdMode': 'cash', 'side': side.lower(),
                           'ordType': 'market', 'sz': repr(float(qty)), 'clOrdId': client_id})
        rows = self._signed('POST', '/api/v5/trade/order', body)
        r = rows[0] if rows else {}
        return Order(broker_order_id=str(r.get('ordId', '')), symbol=symbol, side=side.upper(),
                     qty=float(qty), avg_price=0.0, fee=0.0,
                     status='pending' if r.get('sCode') in ('0', 0) else 'rejected', raw=r)

    def cancel_order(self, symbol, broker_order_id) -> dict:
        self._guard()
        body = json.dumps({'instId': symbol, 'ordId': broker_order_id})
        return {'result': self._signed('POST', '/api/v5/trade/cancel-order', body)}

    def close_position(self, symbol, client_id) -> Order:
        self._guard()
        held = self.get_positions().get(symbol)
        if not held:
            return Order(broker_order_id='', symbol=symbol, side='SELL', qty=0.0,
                         avg_price=0.0, fee=0.0, status='rejected', raw={'reason': 'no_position'})
        return self.place_order(symbol, 'SELL', held['qty'], client_id)
