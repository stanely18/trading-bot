import argparse
import json
import sys
import uuid
from .core import Store,RiskGateway,now_ms,encode
from .market import fetch,demo_balance_probe

def main():
    p=argparse.ArgumentParser(description='Paper-only gateway; never sends exchange orders')
    p.add_argument('--db',default='state/paper.sqlite3')
    p.add_argument('command',choices=['init','state','market','run','export','halt','probe-demo'])
    p.add_argument('--proposal',help='strict JSON proposal; omitted means HOLD')
    p.add_argument('--run-id',help='stable scheduled slot id; do not generate a new id on retry')
    a=p.parse_args();store=Store(a.db)
    if a.command=='init':out=store.init()
    elif a.command=='state':out=store.read()
    elif a.command=='market':out=fetch()
    elif a.command=='export':out={'portfolio':store.read(),'runs':store.records()}
    elif a.command=='halt':out=store.halt()
    elif a.command=='probe-demo':out=demo_balance_probe()
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
    return 0
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print(json.dumps({'status':'failed','error':type(e).__name__,'detail':str(e)},ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
