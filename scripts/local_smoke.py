"""Actual OKX read + separate-process state/retry smoke; writes no exchange orders."""
import json,subprocess,sys,tempfile
from pathlib import Path
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[1]
def cmd(args,allowed=(0,)):
    p=subprocess.run([sys.executable,*args],cwd=root,capture_output=True,text=True,timeout=40)
    if p.returncode not in allowed:raise RuntimeError(p.stderr)
    return json.loads(p.stdout)
with tempfile.TemporaryDirectory(prefix='trading-poc-') as tmp:
    db=str(Path(tmp)/'paper.sqlite3')
    start=cmd(['-m','trading_bot','--db',db,'init'])
    one=cmd(['-m','trading_bot','--db',db,'run','--run-id','local-smoke-1'])
    retry=cmd(['-m','trading_bot','--db',db,'run','--run-id','local-smoke-1'])
    two=cmd(['-m','trading_bot','--db',db,'run','--run-id','local-smoke-2'])
    exported=cmd(['-m','trading_bot','--db',db,'export'])
    assert one==retry and len(exported['runs'])==2 and exported['portfolio']['revision']==2
    assert two['previous_hash']==one['hash'] and not one['fills'] and not two['fills']
    probe=str(Path(tmp)/'probe')
    a=cmd(['scripts/cloud_probe.py','--state-dir',probe,'--run-id','local-1','--session-id','local-process-A','--init'])
    b=cmd(['scripts/cloud_probe.py','--state-dir',probe,'--run-id','local-2','--session-id','local-process-B'])
    assert b['previous_nonce']==a['nonce'] and b['sequence']==2
    output={'scope':'local_only_not_cowork_cloud','checked_at':datetime.now(timezone.utc).isoformat(),
            'status':'passed','restart_and_retry':'passed','probe_chain':'passed',
            'demo':cmd(['-m','trading_bot','probe-demo'],(0,2)),
            'export':exported,'probe_records':[a,b]}
(root/'evidence/local-smoke.json').write_text(json.dumps(output,indent=2))
print(json.dumps({k:v for k,v in output.items() if k not in ['export','probe_records']},indent=2))
