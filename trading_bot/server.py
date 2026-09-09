"""POC HTTP bridge. Bind loopback; remote use requires an authenticated HTTPS proxy."""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .core import Store,RiskGateway,encode
from .market import fetch

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass  # Never log authentication headers or model input.
    def reply(self,code,obj):
        data=encode(obj).encode();self.send_response(code)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)
    def authorized(self):
        actual=self.headers.get('Authorization','')
        if not hmac.compare_digest(actual,'Bearer '+self.server.token):
            self.reply(401,{'error':'unauthorized'});return False
        return True
    def do_GET(self):
        if not self.authorized():return
        if self.path=='/health':self.reply(200,{'mode':'paper','service':'gateway','version':1})
        elif self.path=='/state':self.reply(200,self.server.store.read())
        else:self.reply(404,{'error':'not_found'})
    def do_POST(self):
        if not self.authorized():return
        if self.path!='/proposals':self.reply(404,{'error':'not_found'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=16384:raise ValueError('payload size')
            proposal=json.loads(self.rfile.read(length))
            # Detect a retry before network I/O; gateway verifies the proposal hash.
            previous=next((r for r in self.server.store.records() if r['run_id']==proposal.get('id')),None)
            market=previous['market'] if previous else fetch()
            out=RiskGateway(self.server.store).run(proposal,market)
            self.reply(200,out)
        except (ValueError,KeyError,TypeError,AttributeError):self.reply(409,{'error':'invalid_or_conflicting_proposal'})
        except Exception:self.reply(503,{'error':'gateway_unavailable_no_fill'})

def main():
    token=os.environ.get('TRADING_GATEWAY_TOKEN','')
    if len(token)<32:raise RuntimeError('TRADING_GATEWAY_TOKEN must have at least 32 characters')
    store=Store(os.environ.get('TRADING_DB','state/paper.sqlite3'));store.read()
    server=ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('TRADING_PORT','8765'))),Handler)
    server.token=token;server.store=store
    print('paper gateway listening on loopback',flush=True);server.serve_forever()
if __name__=='__main__':main()
