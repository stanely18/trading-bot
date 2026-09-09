import copy
import hashlib
import json
import math
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = ('BTC-USDT', 'ETH-USDT', 'SOL-USDT')
POLICY = dict(version=1, mode='paper', initial_cash=10000.0, days=30,
              max_order_fraction=.10, max_position_fraction=.20, max_positions=3,
              daily_loss=.02, max_drawdown=.10, max_age_ms=60000,
              fee_bps=10, slippage_bps=5, stop_fraction=.02,
              max_planned_loss_fraction=.005, max_daily_orders=24)

def now_ms(): return int(time.time()*1000)
def encode(x): return json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False)
def digest(x): return hashlib.sha256(encode(x).encode()).hexdigest()
def day(ms): return datetime.fromtimestamp(ms/1000, timezone.utc).strftime('%Y-%m-%d')
def number(x, positive=False):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError('finite numeric value required')
    if positive and x <= 0: raise ValueError('positive value required')
    return x

def proposal_valid(p):
    keys={'id','created_ms','expected_revision','agent','action','symbol','notional','reason'}
    if not isinstance(p,dict) or set(p)!=keys: raise ValueError('proposal fields mismatch')
    for k in ('id','agent','reason'):
        if not isinstance(p[k],str) or not 1 <= len(p[k]) <= 2000: raise ValueError(k)
    for k in ('created_ms','expected_revision'):
        if type(p[k]) is not int or p[k]<0: raise ValueError(k)
    if p['action'] not in ('HOLD','BUY','SELL') or p['symbol'] not in SYMBOLS: raise ValueError('action/symbol')
    number(p['notional'])
    if p['action']=='HOLD' and p['notional']!=0: raise ValueError('HOLD notional')
    if p['action']!='HOLD' and p['notional']<=0: raise ValueError('notional')

def market_valid(m, t):
    if set(m)!=set(SYMBOLS): raise ValueError('incomplete market')
    for sym,q in m.items():
        if q['symbol']!=sym: raise ValueError('symbol mismatch')
        number(q['price'],True)
        if type(q['ts_ms']) is not int or not -5000<=t-q['ts_ms']<=POLICY['max_age_ms']:
            raise ValueError('stale/future market')

def equity(s,m): return s['cash']+sum(p['qty']*m[k]['price'] for k,p in s['positions'].items())

class Store:
    def __init__(self,path): self.path=Path(path)
    @contextmanager
    def transaction(self):
        if not self.path.exists(): raise RuntimeError('state missing: explicit init required; never auto-reset')
        c=sqlite3.connect(self.path,timeout=10, isolation_level=None)
        try:
            c.execute('PRAGMA synchronous=FULL')
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback(); raise
        finally: c.close()
    def init(self,t=None):
        t=now_ms() if t is None else t
        self.path.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation prevents an accidental portfolio reset.
        with self.path.open('xb'): pass
        c=sqlite3.connect(self.path)
        try:
            c.executescript('CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);'
                'CREATE TABLE runs (id TEXT PRIMARY KEY, input_hash TEXT NOT NULL, body TEXT NOT NULL);')
            s=dict(schema_version=1, revision=0, mode='paper', policy_hash=digest(POLICY),
                   started_ms=t, ends_ms=t+POLICY['days']*86400000, cash=POLICY['initial_cash'],
                   positions={}, peak_equity=10000.0, day=day(t), day_equity=10000.0,
                   last_equity=10000.0, daily_orders=0, halted=False, market={}, last_run_hash=None)
            c.execute('INSERT INTO state VALUES (1,?)',(encode(s),));c.commit()
        finally:c.close()
        return s
    def read(self):
        with self.transaction() as c: return json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
    def records(self):
        with self.transaction() as c: return [json.loads(x[0]) for x in c.execute('SELECT body FROM runs ORDER BY rowid')]
    def halt(self):
        with self.transaction() as c:
            s=json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
            s['halted']=True;s['revision']+=1
            c.execute('UPDATE state SET body=? WHERE id=1',(encode(s),))
        return s

class RiskGateway:
    """Only this class changes trading balances. Fixed policy, no model override fields."""
    def __init__(self,store): self.store=store
    def run(self,p,market,t=None):
        proposal_valid(p)
        t=now_ms() if t is None else t
        with self.store.transaction() as c:
            old=c.execute('SELECT input_hash,body FROM runs WHERE id=?',(p['id'],)).fetchone()
            if old:
                if old[0]!=digest(p): raise ValueError('idempotency conflict')
                return json.loads(old[1])
            s=json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
            if s['policy_hash']!=digest(POLICY) or s['mode']!='paper': raise ValueError('policy/mode changed')
            if p['expected_revision']!=s['revision']: raise ValueError('revision conflict; re-read state')
            if not 0<=t-p['created_ms']<=POLICY['max_age_ms']: raise ValueError('expired/future proposal')
            market_valid(market,t)
            if t < s['started_ms']: raise ValueError('clock before experiment')
            s['market']=copy.deepcopy(market)
            nav=equity(s,market)
            if s['day']!=day(t):
                # First observed mark of new UTC day; overnight gap belongs to new day.
                s['day']=day(t);s['day_equity']=s['last_equity'];s['daily_orders']=0
            s['peak_equity']=max(s['peak_equity'],nav)
            daily_breach=nav<=s['day_equity']*(1-POLICY['daily_loss'])
            if nav<=s['peak_equity']*(1-POLICY['max_drawdown']): s['halted']=True
            fills=[]
            expired=t>=s['ends_ms']
            # Stops and exits remain allowed during kill/daily-loss/end-of-experiment.
            for sym in list(s['positions']):
                pos=s['positions'][sym]
                if s['halted'] or daily_breach or expired or market[sym]['price']<=pos['stop_price']:
                    self._sell(s,sym,pos['qty'],market,fills,'risk_exit')
            nav=equity(s,market)
            action=p['action'];sym=p['symbol'];n=p['notional'];reason='hold';status='held'
            if action=='BUY':
                pos=s['positions'].get(sym);price=market[sym]['price']*(1+POLICY['slippage_bps']/10000)
                cost=n*(1+POLICY['fee_bps']/10000)
                planned_loss=n*(POLICY['stop_fraction']+2*(POLICY['fee_bps']+POLICY['slippage_bps'])/10000)
                checks=[(s['halted'],'halted'),(daily_breach,'daily_loss'),(expired,'experiment_ended'),
                        (s['daily_orders']>=POLICY['max_daily_orders'],'daily_order_cap'),
                        (n>nav*POLICY['max_order_fraction'],'order_cap'),
                        (n+(pos['qty']*market[sym]['price'] if pos else 0)>nav*POLICY['max_position_fraction'],'position_cap'),
                        (not pos and len(s['positions'])>=POLICY['max_positions'],'positions_cap'),
                        (cost>s['cash'],'insufficient_cash'),
                        (pos is not None,'pyramiding_disabled'),
                        (planned_loss>nav*POLICY['max_planned_loss_fraction'],'planned_loss_cap')]
                reason=next((r for failed,r in checks if failed),'approved')
                if reason=='approved':
                    qty=n/price;s['cash']-=cost
                    s['positions'][sym]=dict(qty=qty,entry_price=price,stop_price=price*(1-POLICY['stop_fraction']))
                    fills.append(dict(symbol=sym,side='BUY',qty=qty,price=price,fee=n*POLICY['fee_bps']/10000,reason='proposal'))
                    s['daily_orders']+=1;status='filled'
                else: status='rejected'
            elif action=='SELL':
                pos=s['positions'].get(sym)
                if not pos: status='rejected';reason='no_position'
                elif n>pos['qty']*market[sym]['price']+1e-8:status='rejected';reason='oversell'
                else:
                    self._sell(s,sym,min(pos['qty'],n/market[sym]['price']),market,fills,'proposal')
                    status='filled';reason='approved'
            s['last_equity']=equity(s,market);s['peak_equity']=max(s['peak_equity'],s['last_equity'])
            if s['last_equity']<=s['peak_equity']*(1-POLICY['max_drawdown']):s['halted']=True
            prev=s['last_run_hash'];s['revision']+=1
            result=dict(schema_version=1,run_id=p['id'],recorded_ms=t,revision=s['revision'],mode='paper',
                        proposal=p,market=market,status=status,reason=reason,fills=fills,
                        equity=s['last_equity'],previous_hash=prev)
            result['hash']=digest(result);s['last_run_hash']=result['hash']
            c.execute('UPDATE state SET body=? WHERE id=1',(encode(s),))
            c.execute('INSERT INTO runs VALUES (?,?,?)',(p['id'],digest(p),encode(result)))
            return result
    def _sell(self,s,sym,qty,market,fills,reason):
        price=market[sym]['price']*(1-POLICY['slippage_bps']/10000);gross=qty*price
        fee=gross*POLICY['fee_bps']/10000;s['cash']+=gross-fee
        s['positions'][sym]['qty']-=qty
        if s['positions'][sym]['qty']<1e-12:del s['positions'][sym]
        s['daily_orders']+=1
        fills.append(dict(symbol=sym,side='SELL',qty=qty,price=price,fee=fee,reason=reason))
