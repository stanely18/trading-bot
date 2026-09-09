import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from trading_bot.core import *

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'state.sqlite3';self.s=Store(self.db);self.t=1788998400000;self.s.init(self.t)
        self.g=RiskGateway(self.s);self.m={k:dict(symbol=k,price=100.0,ts_ms=self.t,source='fixture') for k in SYMBOLS}
    def p(self,id='one',action='BUY',n=100):
        return dict(id=id,created_ms=self.t,expected_revision=self.s.read()['revision'],agent='fixture',action=action,symbol='BTC-USDT',notional=n,reason='test')
    def runp(self,p=None):return self.g.run(p or self.p(),self.m,self.t)
    def test_buy_restart_sell_fees(self):
        r=self.runp();self.assertEqual(r['status'],'filled');self.assertLess(r['equity'],10000)
        self.g=RiskGateway(Store(self.db));q=self.s.read()['positions']['BTC-USDT']['qty']
        self.runp(self.p('sell','SELL',q*100));self.assertFalse(self.s.read()['positions'])
        self.assertLess(self.s.read()['cash'],10000)
    def test_retry_and_conflict(self):
        p=self.p();r=self.runp(p);self.assertEqual(r,self.g.run(p,{},self.t+999999))
        p['notional']=90
        with self.assertRaises(ValueError):self.runp(p)
        self.assertEqual(len(self.s.records()),1)
    def test_concurrent_duplicate(self):
        p=self.p()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:RiskGateway(Store(self.db)).run(p,self.m,self.t),range(4)))
        self.assertTrue(all(r==results[0] for r in results));self.assertEqual(self.s.read()['revision'],1)
    def test_revision_conflict(self):
        p=self.p();self.runp();p['id']='other'
        with self.assertRaises(ValueError):self.runp(p)
    def test_bad_numeric_and_override(self):
        for val in [float('nan'),float('inf'),True,-1,0,'100']:
            p=self.p();p['notional']=val
            with self.assertRaises(ValueError):self.runp(p)
        p=self.p();p['override']=True
        with self.assertRaises(ValueError):self.runp(p)
        self.assertEqual(self.s.read()['revision'],0)
    def test_stale_missing_future_market(self):
        for m in [{}, {**self.m,'BTC-USDT':dict(symbol='BTC-USDT',price=100,ts_ms=self.t-60001)},
                  {**self.m,'BTC-USDT':dict(symbol='BTC-USDT',price=100,ts_ms=self.t+6000)}]:
            with self.assertRaises(ValueError):self.g.run(self.p(),m,self.t)
        self.assertEqual(len(self.s.records()),0)
    def test_expired_proposal(self):
        p=self.p();p['created_ms']-=60001
        with self.assertRaises(ValueError):self.runp(p)
    def test_size_and_no_pyramiding(self):
        self.assertEqual(self.runp(self.p(n=2000))['reason'],'order_cap')
        self.runp(self.p('small'));self.assertEqual(self.runp(self.p('add'))['reason'],'pyramiding_disabled')
    def test_oversell(self):self.assertEqual(self.runp(self.p(action='SELL'))['reason'],'no_position')
    def test_halt_exits_and_blocks(self):
        self.runp();self.s.halt();r=self.runp(self.p('halted'))
        self.assertEqual(r['reason'],'halted');self.assertEqual(r['fills'][0]['side'],'SELL')
        self.assertFalse(self.s.read()['positions'])
    def test_stop(self):
        self.runp();self.m['BTC-USDT']['price']=90
        r=self.runp(self.p('stop','HOLD',0));self.assertEqual(r['fills'][0]['reason'],'risk_exit')
    def test_daily_loss_and_drawdown(self):
        # Simulate a preexisting mark-to-market breach without bypassing execution.
        with self.s.transaction() as c:
            s=json.loads(c.execute('SELECT body FROM state').fetchone()[0]);s['cash']=9700
            c.execute('UPDATE state SET body=?',(encode(s),))
        self.assertEqual(self.runp()['reason'],'daily_loss')
        with self.s.transaction() as c:
            s=json.loads(c.execute('SELECT body FROM state').fetchone()[0]);s['cash']=8900
            c.execute('UPDATE state SET body=?',(encode(s),))
        self.assertEqual(self.runp(self.p('dd'))['reason'],'halted')
    def test_end_of_experiment(self):
        self.runp();self.t+=30*86400000
        for q in self.m.values():q['ts_ms']=self.t
        r=self.runp(self.p('end'));self.assertEqual(r['reason'],'experiment_ended')
        self.assertFalse(self.s.read()['positions'])
    def test_rollback_and_missing_state(self):
        with self.assertRaises(RuntimeError):
            with self.s.transaction() as c:
                c.execute('DELETE FROM state');raise RuntimeError('crash')
        self.assertEqual(self.s.read()['revision'],0)
        with self.assertRaises(FileExistsError):self.s.init()
        with self.assertRaises(RuntimeError):Store(self.db.parent/'missing').read()
    def test_hash_chain(self):
        a=self.runp();b=self.runp(self.p('two','HOLD',0))
        self.assertEqual(b['previous_hash'],a['hash'])
        expected=b.pop('hash');self.assertEqual(digest(b),expected)
    def test_policy_tamper(self):
        with self.s.transaction() as c:
            s=json.loads(c.execute('SELECT body FROM state').fetchone()[0]);s['mode']='live'
            c.execute('UPDATE state SET body=?',(encode(s),))
        with self.assertRaises(ValueError):self.runp()

if __name__=='__main__':unittest.main()
