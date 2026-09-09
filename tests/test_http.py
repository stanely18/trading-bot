import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from trading_bot.server import Handler
from trading_bot.core import Store,SYMBOLS,now_ms

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.token='a'*32;self.server.store=Store(Path(self.tmp.name)/'test.db');self.server.store.init()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def req(self,path,body=None,auth=True):
        headers={'Authorization':'Bearer '+self.server.token} if auth else {}
        req=Request('http://127.0.0.1:'+str(self.server.server_port)+path,
                    data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urlopen(req,timeout=3) as r:return json.load(r)
    def test_auth_and_no_mutation_endpoint(self):
        with self.assertRaises(HTTPError) as err:self.req('/state',auth=False)
        self.assertEqual(err.exception.code,401)
        with self.assertRaises(HTTPError) as err:self.req('/reset',{})
        self.assertEqual(err.exception.code,404)
        self.assertEqual(self.req('/state')['revision'],0)
    def test_gateway_and_retry(self):
        t=now_ms();p=dict(id='http',created_ms=t,expected_revision=0,agent='test',action='BUY',symbol='BTC-USDT',notional=100,reason='fixture')
        m={s:dict(symbol=s,price=100,ts_ms=t,source='fixture') for s in SYMBOLS}
        with patch('trading_bot.server.fetch',return_value=m) as f:
            a=self.req('/proposals',p);b=self.req('/proposals',p)
            self.assertEqual(a,b);self.assertEqual(f.call_count,1)
        self.assertEqual(self.req('/state')['revision'],1)
    def test_network_failure_keeps_state(self):
        p=dict(id='fail',created_ms=now_ms(),expected_revision=0,agent='test',action='BUY',symbol='BTC-USDT',notional=100,reason='fixture')
        with patch('trading_bot.server.fetch',side_effect=RuntimeError('network')):
            with self.assertRaises(HTTPError) as err:self.req('/proposals',p)
            self.assertEqual(err.exception.code,503)
        self.assertEqual(self.req('/state')['revision'],0)
