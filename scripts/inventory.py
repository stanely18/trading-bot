"""Read metadata only. Never emits secret values or full configuration."""
import json,platform,shutil,subprocess
out={'platform':platform.platform(),'cli':{}}
for cmd in ['python3','node','uv','claude','codex','agy','gemini','docker']:
    out['cli'][cmd]={'path':shutil.which(cmd)}
    if cmd in ['python3','claude','codex'] and shutil.which(cmd):
        r=subprocess.run([cmd,'--version'],capture_output=True,text=True,timeout=15)
        out['cli'][cmd]['version']=r.stdout.strip()
print(json.dumps(out,indent=2))
