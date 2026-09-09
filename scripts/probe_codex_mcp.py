"""Legacy stdio handshake only: no model invocation and no settings mutation."""
import json,selectors,subprocess,time
p=subprocess.Popen(['codex','mcp-server'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
def send(x):p.stdin.write(json.dumps(x)+'\n');p.stdin.flush()
def receive(id):
    end=time.monotonic()+15
    while time.monotonic()<end:
        with selectors.DefaultSelector() as s:
            s.register(p.stdout,selectors.EVENT_READ)
            if not s.select(max(0,end-time.monotonic())):break
        line=p.stdout.readline()
        if not line:break
        obj=json.loads(line)
        if obj.get('id')==id:
            if 'error' in obj:raise RuntimeError('MCP protocol error')
            return obj['result']
    raise TimeoutError('MCP handshake timed out')
try:
    send({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'paper-poc-probe','version':'0.1'}}})
    info=receive(1)
    send({'jsonrpc':'2.0','method':'notifications/initialized'})
    send({'jsonrpc':'2.0','id':2,'method':'tools/list'})
    available=receive(2)
    print(json.dumps({'status':'passed','scope':'local_stdio_handshake_only','deprecated':True,
                      'server':info.get('serverInfo'),'tools':[x['name'] for x in available['tools']],
                      'model_inference_tested':False,'cowork_cloud_reachability_tested':False},indent=2))
finally:
    p.terminate()
    try:p.wait(timeout=3)
    except subprocess.TimeoutExpired:p.kill();p.wait()
