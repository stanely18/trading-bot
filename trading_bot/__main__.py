import argparse
import json
import os
import sys
import uuid
from .core import Store,RiskGateway,now_ms,encode
from .market import fetch,demo_balance_probe

def _model_client(name):
    name=(name or os.environ.get('TRADING_MODEL') or 'none').lower()
    if name in ('none','off','hold'): return None
    if name in ('nvidia','kimi','kimi-k3'):
        from .model.nvidia import NvidiaKimiClient
        return NvidiaKimiClient()
    raise SystemExit('unknown --model: '+name)

def main():
    p=argparse.ArgumentParser(description='Paper-only gateway; never sends exchange orders')
    p.add_argument('--db',default='state/paper.sqlite3')
    p.add_argument('command',choices=['init','state','market','run','cycle','risk-check','export','halt','probe-demo'])
    p.add_argument('--proposal',help='strict JSON proposal; omitted means HOLD')
    p.add_argument('--run-id',help='stable scheduled slot id; do not generate a new id on retry')
    p.add_argument('--root',default='.',help='repo root for cycle state/logs/trades projections')
    p.add_argument('--model',help='cycle trading agent: none (default) or nvidia')
    a=p.parse_args();store=Store(a.db)
    if a.command=='init':out=store.init()
    elif a.command=='state':out=store.read()
    elif a.command=='market':out=fetch()
    elif a.command=='export':out={'portfolio':store.read(),'runs':store.records()}
    elif a.command=='halt':out=store.halt()
    elif a.command=='probe-demo':out=demo_balance_probe()
    elif a.command=='cycle':
        from .cycle import run_cycle
        if not a.run_id: raise SystemExit('cycle requires --run-id (stable slot id, reused on retry)')
        out=run_cycle(a.db,a.run_id,model_client=_model_client(a.model),root=a.root)
    elif a.command=='risk-check':
        from .cycle import run_risk_check
        if not a.run_id: raise SystemExit('risk-check requires --run-id (use a risk-* prefix, distinct from trading slots)')
        out=run_risk_check(a.db,a.run_id,root=a.root)
    else:
        if a.proposal:
            with open(a.proposal) as f: proposal=json.load(f)
        else:
            rid=a.run_id or str(uuid.uuid4())
            # Resume the exact earlier HOLD input for retries after process restarts.
            previous=next((r for r in store.records() if r['run_id']==rid),None)
            proposal=previous['proposal'] if previous else dict(id=rid,created_ms=now_ms(),expected_revision=store.read()['revision'],
                agent='baseline-hold',action='HOLD',symbol='BTC-USDT',notional=0,reason='infrastructure probe')
        # A committed retry needs no fresh market network request.
        previous=next((r for r in store.records() if r['run_id']==proposal['id']),None)
        market=previous['market'] if previous else fetch()
        out=RiskGateway(store).run(proposal,market)
    print(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False))
    if isinstance(out,dict) and out.get('status')=='blocked':return 2
    # Cycle committed a safe HOLD + full logs, but surface a requested-model
    # failure so the CI job goes red and the missing/broken key gets noticed.
    if isinstance(out,dict) and out.get('model_status')=='model_error':return 3
    return 0
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print(json.dumps({'status':'failed','error':type(e).__name__,'detail':str(e)},ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
