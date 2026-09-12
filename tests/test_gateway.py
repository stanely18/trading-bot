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
    def p(self,id='one',action='BUY',n=None):
        n=POLICY['initial_cash']*0.01 if n is None else n  # 1% of nav: well inside every cap regardless of initial_cash
        return dict(id=id,created_ms=self.t,expected_revision=self.s.read()['revision'],agent='fixture',action=action,symbol='BTC-USDT',notional=n,reason='test')
    def runp(self,p=None):return self.g.run(p or self.p(),self.m,self.t)
    def test_buy_restart_sell_fees(self):
        r=self.runp();self.assertEqual(r['status'],'filled');self.assertLess(r['equity'],POLICY['initial_cash'])
        self.g=RiskGateway(Store(self.db));q=self.s.read()['positions']['BTC-USDT']['qty']
        self.runp(self.p('sell','SELL',q*100));self.assertFalse(self.s.read()['positions'])
        self.assertLess(self.s.read()['cash'],POLICY['initial_cash'])
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
        self.assertEqual(self.runp(self.p(n=POLICY['initial_cash']*.5))['reason'],'order_cap')
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
            s=json.loads(c.execute('SELECT body FROM state').fetchone()[0]);s['cash']=POLICY['initial_cash']*.97
            c.execute('UPDATE state SET body=?',(encode(s),))
        self.assertEqual(self.runp()['reason'],'daily_loss')
        with self.s.transaction() as c:
            s=json.loads(c.execute('SELECT body FROM state').fetchone()[0]);s['cash']=POLICY['initial_cash']*.89
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

class PolicyProfileTests(unittest.TestCase):
    """load_policy() itself; no store/gateway involved."""
    def test_baseline_and_missing_profile_are_default(self):
        self.assertEqual(load_policy('baseline'), DEFAULT_POLICY)
        self.assertEqual(load_policy('nonexistent-profile'), DEFAULT_POLICY)
    def test_conservative_halves_risk_caps_no_leverage(self):
        cons=load_policy('conservative')
        for k in ('max_order_fraction','max_position_fraction','daily_loss','max_drawdown','max_planned_loss_fraction'):
            self.assertAlmostEqual(cons[k],DEFAULT_POLICY[k]/2)
        self.assertNotIn('leverage',cons)
    def test_aggressive_adds_leverage_without_loosening_account_caps(self):
        agg=load_policy('aggressive')
        self.assertEqual(agg['leverage'],5)
        self.assertEqual(agg['maintenance_margin_rate'],0.005)
        self.assertEqual(agg['daily_loss'],DEFAULT_POLICY['daily_loss'])
        self.assertEqual(agg['max_drawdown'],DEFAULT_POLICY['max_drawdown'])

class LeverageTests(unittest.TestCase):
    """Aggressive-profile (5x isolated-margin) mechanics and the leverage=1 no-op guarantee."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.t=1788998400000
        self.m={k:dict(symbol=k,price=100.0,ts_ms=self.t,source='fixture') for k in SYMBOLS}
        self.base_db=Path(self.tmp.name)/'base.sqlite3'
        self.base_store=Store(self.base_db);self.base_store.init(self.t)
        self.agg_policy=dict(DEFAULT_POLICY,leverage=5,maintenance_margin_rate=0.005,liquidation_fee_rate=0.0125)
        self.agg_db=Path(self.tmp.name)/'agg.sqlite3'
        self.agg_store=Store(self.agg_db);self.agg_store.init(self.t,policy=self.agg_policy)
    def bp(self,store,id='one',n=None,symbol='BTC-USDT',action='BUY',leverage=None,revision=0):
        p=dict(id=id,created_ms=self.t,expected_revision=revision,agent='fixture',action=action,
               symbol=symbol,notional=n if n is not None else DEFAULT_POLICY['initial_cash']*0.1,reason='test')
        if leverage is not None: p['leverage']=leverage
        return p
    def test_liquidation_price_formula_long_and_short(self):
        self.assertAlmostEqual(liquidation_price(100.0,5,0.005,'long'),100.0*(1-1/5+0.005))
        self.assertAlmostEqual(liquidation_price(100.0,5,0.005,'short'),100.0*(1+1/5-0.005))
    def test_leverage_scales_notional_exposure_same_margin(self):
        # n kept small enough that the leveraged (5x) notional still clears
        # planned_loss_cap -- see test_planned_loss_cap_uses_leveraged_notional
        # below for the case where it doesn't.
        n=DEFAULT_POLICY['initial_cash']*0.03
        g_base=RiskGateway(self.base_store)
        r_base=g_base.run(self.bp(self.base_store,n=n),self.m,self.t)
        self.assertEqual(r_base['status'],'filled')
        base_after=self.base_store.read()
        qty_base=base_after['positions']['BTC-USDT']['qty']
        fee_base=r_base['fills'][0]['fee']
        margin_base=DEFAULT_POLICY['initial_cash']-base_after['cash']-fee_base

        g_agg=RiskGateway(self.agg_store,policy=self.agg_policy)
        r_agg=g_agg.run(self.bp(self.agg_store,id='agg',n=n,leverage=5),self.m,self.t)
        self.assertEqual(r_agg['status'],'filled')
        agg_after=self.agg_store.read()
        qty_agg=agg_after['positions']['BTC-USDT']['qty']
        fee_agg=r_agg['fills'][0]['fee']
        margin_agg=self.agg_policy['initial_cash']-agg_after['cash']-fee_agg

        self.assertAlmostEqual(qty_agg,qty_base*5,places=9)
        self.assertAlmostEqual(margin_base,margin_agg,places=9)
        # Fees are charged on notional (leveraged) size: 5x margin -> 5x fee
        # for an equivalent margin commitment; baseline fee math untouched.
        self.assertAlmostEqual(fee_agg,fee_base*5,places=9)
        self.assertAlmostEqual(fee_base,n*DEFAULT_POLICY['fee_bps']/10000,places=9)
        self.assertIn('liquidation_price',agg_after['positions']['BTC-USDT'])
        self.assertNotIn('liquidation_price',base_after['positions']['BTC-USDT'])

    def test_planned_loss_cap_uses_leveraged_notional_not_margin(self):
        # n=10% of nav is under aggressive's own max_order_fraction (10%) and
        # max_position_fraction (20%) caps -- i.e. margin-only checks would
        # pass it -- but at 5x leverage the real notional-based planned loss
        # (~11.5% of nav) blows through max_planned_loss_fraction (0.5%).
        # Before the fix this was computed from unleveraged margin and wrongly
        # approved; it must now be rejected.
        n=DEFAULT_POLICY['initial_cash']*0.1
        g_agg=RiskGateway(self.agg_store,policy=self.agg_policy)
        r_agg=g_agg.run(self.bp(self.agg_store,n=n,leverage=5),self.m,self.t)
        self.assertEqual(r_agg['status'],'rejected')
        self.assertEqual(r_agg['reason'],'planned_loss_cap')
        self.assertFalse(self.agg_store.read()['positions'])
        # Baseline/conservative (leverage=1): notional==margin, so the same
        # margin fraction that got rejected above is unaffected (still fills)
        # -- confirms this is a no-op for leverage=1.
        g_base=RiskGateway(self.base_store)
        r_base=g_base.run(self.bp(self.base_store,n=n),self.m,self.t)
        self.assertEqual(r_base['status'],'filled')
    def test_leverage_exceeds_policy_guard_rejects(self):
        g_base=RiskGateway(self.base_store)
        p=self.bp(self.base_store,leverage=2)  # base policy caps leverage at 1
        r=g_base.run(p,self.m,self.t)
        self.assertEqual(r['reason'],'leverage_exceeds_policy')
        self.assertFalse(self.base_store.read()['positions'])
    def test_force_liquidation_distinct_from_stop_loss(self):
        g_agg=RiskGateway(self.agg_store,policy=self.agg_policy)
        # n small enough that 5x notional clears planned_loss_cap (see
        # test_planned_loss_cap_uses_leveraged_notional_not_margin).
        r_open=g_agg.run(self.bp(self.agg_store,n=DEFAULT_POLICY['initial_cash']*0.03,leverage=5),self.m,self.t)
        self.assertEqual(r_open['status'],'filled')
        pos=self.agg_store.read()['positions']['BTC-USDT']
        liq=pos['liquidation_price']
        self.assertLess(liq,pos['stop_price'])  # liquidation sits below the 2% stop for 5x/0.5% mmr
        crashed={**self.m,'BTC-USDT':dict(symbol='BTC-USDT',price=liq-0.01,ts_ms=self.t)}
        p_hold=dict(id='crash',created_ms=self.t,expected_revision=self.agg_store.read()['revision'],
                    agent='fixture',action='HOLD',symbol='BTC-USDT',notional=0,reason='test')
        r_crash=g_agg.run(p_hold,crashed,self.t)
        self.assertEqual(r_crash['fills'][0]['reason'],'liquidated')
        self.assertNotIn('BTC-USDT',self.agg_store.read()['positions'])
    def test_liquidation_fee_charged_on_top_of_normal_exit_fee(self):
        g_agg=RiskGateway(self.agg_store,policy=self.agg_policy)
        r_open=g_agg.run(self.bp(self.agg_store,n=DEFAULT_POLICY['initial_cash']*0.03,leverage=5),self.m,self.t)
        self.assertEqual(r_open['status'],'filled')
        state=self.agg_store.read()
        qty=state['positions']['BTC-USDT']['qty']
        entry_price=state['positions']['BTC-USDT']['entry_price']
        crashed_market={**self.m,'BTC-USDT':dict(symbol='BTC-USDT',price=entry_price*0.8,ts_ms=self.t)}
        # Two copies of the identical post-entry state, exited with the same
        # qty/price via _sell but different reasons, isolate the effect of
        # liquidation_fee_rate on realized proceeds (an "otherwise-identical"
        # comparison to a normal stop-loss exit).
        s_liq=copy.deepcopy(state);fills_liq=[]
        g_agg._sell(s_liq,'BTC-USDT',qty,crashed_market,fills_liq,'liquidated')
        s_stop=copy.deepcopy(state);fills_stop=[]
        g_agg._sell(s_stop,'BTC-USDT',qty,crashed_market,fills_stop,'risk_exit')
        self.assertLess(s_liq['cash'],s_stop['cash'])
        exit_price=entry_price*0.8*(1-self.agg_policy['slippage_bps']/10000)
        expected_extra_fee=qty*exit_price*self.agg_policy['liquidation_fee_rate']
        self.assertAlmostEqual(s_stop['cash']-s_liq['cash'],expected_extra_fee,places=6)
        self.assertAlmostEqual(fills_liq[0]['fee']-fills_stop[0]['fee'],expected_extra_fee,places=6)

    def test_liquidation_fee_absent_is_noop_for_baseline(self):
        # baseline/conservative never set liquidation_fee_rate; self.policy.get
        # must default to 0 so a (hypothetical) 'liquidated' reason on a
        # non-leveraged store costs exactly the normal exit fee.
        g_base=RiskGateway(self.base_store)
        r_open=g_base.run(self.bp(self.base_store,n=DEFAULT_POLICY['initial_cash']*0.05),self.m,self.t)
        self.assertEqual(r_open['status'],'filled')
        state=self.base_store.read()
        qty=state['positions']['BTC-USDT']['qty']
        s_liq=copy.deepcopy(state);fills_liq=[]
        g_base._sell(s_liq,'BTC-USDT',qty,self.m,fills_liq,'liquidated')
        s_normal=copy.deepcopy(state);fills_normal=[]
        g_base._sell(s_normal,'BTC-USDT',qty,self.m,fills_normal,'risk_exit')
        self.assertAlmostEqual(s_liq['cash'],s_normal['cash'],places=9)
        self.assertAlmostEqual(fills_liq[0]['fee'],fills_normal[0]['fee'],places=9)

    def test_exit_cash_conservation_winning_trade_no_manufactured_money(self):
        # Regression test: _sell() must return margin+PnL on a normal
        # (non-liquidated) exit, not the full leveraged notional -- crediting
        # qty*exit_price back would manufacture ~leverage x free money on
        # every winning trade.
        g_agg=RiskGateway(self.agg_store,policy=self.agg_policy)
        n=DEFAULT_POLICY['initial_cash']*0.03  # margin, well under all caps at 5x
        r_open=g_agg.run(self.bp(self.agg_store,n=n,leverage=5),self.m,self.t)
        self.assertEqual(r_open['status'],'filled')
        entry_fee=r_open['fills'][0]['fee']
        pos=self.agg_store.read()['positions']['BTC-USDT']
        qty=pos['qty'];entry_price=pos['entry_price']

        # Price up 10%: liquidation/stop are downside-only triggers, so this
        # never auto-exits; close the full position with an explicit SELL.
        raw_exit_price=110.0
        up_market={**self.m,'BTC-USDT':dict(symbol='BTC-USDT',price=raw_exit_price,ts_ms=self.t)}
        p_close=dict(id='close-up',created_ms=self.t,expected_revision=self.agg_store.read()['revision'],
                     agent='fixture',action='SELL',symbol='BTC-USDT',notional=qty*raw_exit_price,reason='test')
        r_close=g_agg.run(p_close,up_market,self.t)
        self.assertEqual(r_close['status'],'filled')
        self.assertEqual(r_close['fills'][0]['reason'],'proposal')
        exit_fee=r_close['fills'][0]['fee']
        exit_exec_price=raw_exit_price*(1-self.agg_policy['slippage_bps']/10000)

        expected_pnl=qty*(exit_exec_price-entry_price)
        self.assertGreater(expected_pnl,0)
        round_trip=self.agg_store.read()['cash']-self.agg_policy['initial_cash']
        self.assertAlmostEqual(round_trip,expected_pnl-entry_fee-exit_fee,places=6)
        # Sanity: the pre-fix bug credited qty*exit_exec_price (full notional)
        # back instead of margin+pnl -- that would be off by ~n*(leverage-1),
        # nowhere close to the correct, much smaller round trip above.
        self.assertNotAlmostEqual(round_trip,qty*exit_exec_price-entry_fee-exit_fee,places=2)

    def test_exit_cash_conservation_losing_trade_leverage_scales_correctly(self):
        # Losing trade (price down, but staying above both stop_price and
        # liquidation_price so the close is a discretionary SELL, not an
        # automatic exit): must still satisfy cash conservation, and the loss
        # must be leverage x the loss an equivalent leverage=1 trade (same
        # margin, same price move) would take -- confirms the fix didn't
        # invert or double-count on the losing side.
        n=DEFAULT_POLICY['initial_cash']*0.03
        raw_exit_price=99.0  # 1% drop: clear of the 2% stop and the ~-19.5% liq price
        down_market={**self.m,'BTC-USDT':dict(symbol='BTC-USDT',price=raw_exit_price,ts_ms=self.t)}

        def round_trip_pnl(store,policy,leverage):
            g=RiskGateway(store,policy=policy)
            kwargs=dict(n=n,leverage=leverage) if leverage>1 else dict(n=n)
            r_open=g.run(self.bp(store,**kwargs),self.m,self.t)
            self.assertEqual(r_open['status'],'filled')
            entry_fee=r_open['fills'][0]['fee']
            pos=store.read()['positions']['BTC-USDT']
            qty=pos['qty'];entry_price=pos['entry_price']
            if leverage>1:
                self.assertGreater(raw_exit_price,pos['stop_price'])
                self.assertGreater(raw_exit_price,pos['liquidation_price'])
            else:
                self.assertGreater(raw_exit_price,pos['stop_price'])
            p_close=dict(id='close-down',created_ms=self.t,expected_revision=store.read()['revision'],
                         agent='fixture',action='SELL',symbol='BTC-USDT',notional=qty*raw_exit_price,reason='test')
            r_close=g.run(p_close,down_market,self.t)
            self.assertEqual(r_close['status'],'filled')
            self.assertEqual(r_close['fills'][0]['reason'],'proposal')
            exit_fee=r_close['fills'][0]['fee']
            exit_exec_price=raw_exit_price*(1-policy['slippage_bps']/10000)
            expected_pnl=qty*(exit_exec_price-entry_price)
            round_trip=store.read()['cash']-policy['initial_cash']
            self.assertAlmostEqual(round_trip,expected_pnl-entry_fee-exit_fee,places=6)
            return expected_pnl

        pnl_agg=round_trip_pnl(self.agg_store,self.agg_policy,5)
        pnl_base=round_trip_pnl(self.base_store,DEFAULT_POLICY,1)
        self.assertLess(pnl_agg,0);self.assertLess(pnl_base,0)
        self.assertAlmostEqual(pnl_agg,5*pnl_base,places=6)

    def test_leverage1_path_is_zero_diff_noop(self):
        # RiskGateway() with an implicit default policy vs an explicit
        # policy=DEFAULT_POLICY must be indistinguishable, and no leveraged
        # fields must appear on the resulting position.
        g_implicit=RiskGateway(self.base_store)
        g_explicit=RiskGateway(Store(self.base_db),policy=DEFAULT_POLICY)
        small_n=DEFAULT_POLICY['initial_cash']*0.01  # well under caps so a prior fill's fee can't tip it over
        r1=g_implicit.run(self.bp(self.base_store,id='a',symbol='BTC-USDT',n=small_n),self.m,self.t)
        r2=g_explicit.run(self.bp(self.base_store,id='b',symbol='ETH-USDT',n=small_n,revision=1),self.m,self.t)
        for key in ('status','reason'):
            self.assertEqual(r1[key],r2[key])
        for pos in self.base_store.read()['positions'].values():
            self.assertNotIn('leverage',pos);self.assertNotIn('liquidation_price',pos)
    def test_conservative_profile_halved_caps_and_no_leverage_fields(self):
        cons=load_policy('conservative')
        cons_db=Path(self.tmp.name)/'cons.sqlite3'
        cons_store=Store(cons_db);cons_store.init(self.t,policy=cons)
        gw=RiskGateway(cons_store,policy=cons)
        n_ok=cons['max_order_fraction']*cons['initial_cash']
        r=gw.run(self.bp(cons_store,n=n_ok),self.m,self.t)
        self.assertEqual(r['status'],'filled')
        self.assertNotIn('leverage',cons_store.read()['positions']['BTC-USDT'])
        self.assertNotIn('liquidation_price',cons_store.read()['positions']['BTC-USDT'])
        r2=gw.run(self.bp(cons_store,id='over',n=n_ok*1.5,symbol='ETH-USDT',revision=cons_store.read()['revision']),self.m,self.t)
        self.assertEqual(r2['reason'],'order_cap')

if __name__=='__main__':unittest.main()
