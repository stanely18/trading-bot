"""Run within Cowork cloud. Saves evidence; never labels caller assertions as verified."""
import argparse
import hashlib
import json
import os
import platform
import secrets
import shutil
import sqlite3
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trading_bot.market import fetch

p=argparse.ArgumentParser()
p.add_argument('--state-dir',required=True)
p.add_argument('--run-id',required=True,help='Unique scheduled slot id, reused on retries')
p.add_argument('--session-id',required=True,help='Copy actual Cowork session reference')
p.add_argument('--init',action='store_true',help='First run only; never repeat after missing state')
a=p.parse_args();root=Path(a.state_dir);db=root/'cloud-probe.sqlite3'
if a.init:
    root.mkdir(parents=True,exist_ok=True)
    with db.open('xb'):pass
    c=sqlite3.connect(db)
    c.execute('CREATE TABLE probes (id TEXT PRIMARY KEY, body TEXT NOT NULL)');c.commit();c.close()
if not db.exists():sys.exit('BLOCKED: persistent state missing; do not auto-init')
c=sqlite3.connect(db,timeout=10)
c.execute('BEGIN IMMEDIATE')
try:
    old=c.execute('SELECT body FROM probes WHERE id=?',(a.run_id,)).fetchone()
    if old:out=json.loads(old[0])
    else:
        previous=c.execute('SELECT body FROM probes ORDER BY rowid DESC LIMIT 1').fetchone()
        previous=json.loads(previous[0]) if previous else None
        try:market={'status':'passed','quotes':fetch()}
        except Exception as e:market={'status':'failed','error_type':type(e).__name__}
        out={'run_id':a.run_id,'session_id_claimed':a.session_id,'recorded_ms':int(time.time()*1000),
             'hostname':platform.node(),'platform':platform.platform(),'nonce':secrets.token_hex(16),
             'previous_nonce':previous['nonce'] if previous else None,
             'previous_hash':previous['hash'] if previous else None,
             'sequence':previous['sequence']+1 if previous else 1,
             'market':market,'cli_paths':{k:shutil.which(k) for k in ['python3','codex','claude','agy','gemini']},
             'cloud_execution_verified':False,'laptop_off_verified':False}
        out['hash']=hashlib.sha256(json.dumps(out,sort_keys=True).encode()).hexdigest()
        c.execute('INSERT INTO probes VALUES (?,?)',(a.run_id,json.dumps(out)))
    c.commit()
except BaseException:c.rollback();raise
finally:c.close()
print(json.dumps(out,ensure_ascii=False,indent=2))
