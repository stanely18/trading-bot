import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode
from .core import SYMBOLS, now_ms, market_valid

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ValueError('redirect refused')

# Read-only routes. There is deliberately no exchange order API adapter.
BASE='https://www.okx.com'
def get(path,headers=None):
    req=Request(BASE+path,headers={'User-Agent':'trading-bot-poc/0.1',**(headers or {})},method='GET')
    with build_opener(NoRedirect).open(req,timeout=20) as r:
        raw=r.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('oversized response')
    data=json.loads(raw)
    if data.get('code')!='0': raise ValueError('OKX error code '+str(data.get('code')))
    return data['data']

def fetch():
    result={}
    for sym in SYMBOLS:
        rows=get('/api/v5/market/ticker?'+urlencode({'instId':sym}))
        if len(rows)!=1 or rows[0]['instId']!=sym:raise ValueError('unexpected ticker')
        q=rows[0];result[sym]=dict(symbol=sym,price=float(q['last']),ts_ms=int(q['ts']),source='okx_public')
    market_valid(result,now_ms())
    return result

def demo_balance_probe():
    names=('OKX_DEMO_API_KEY','OKX_DEMO_SECRET_KEY','OKX_DEMO_PASSPHRASE')
    if not all(os.environ.get(k) for k in names): return {'status':'blocked','reason':'missing_demo_credentials'}
    key,secret,phrase=(os.environ[k] for k in names)
    stamp=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
    path='/api/v5/account/balance'
    sign=base64.b64encode(hmac.new(secret.encode(),(stamp+'GET'+path).encode(),hashlib.sha256).digest()).decode()
    rows=get(path,{'OK-ACCESS-KEY':key,'OK-ACCESS-SIGN':sign,'OK-ACCESS-PASSPHRASE':phrase,
                   'OK-ACCESS-TIMESTAMP':stamp,'x-simulated-trading':'1'})
    return {'status':'passed','operation':'demo_balance_read_only','account_rows':len(rows)}
