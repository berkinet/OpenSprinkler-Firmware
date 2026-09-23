import json
from functools import partial
from http.server import ThreadingHTTPServer
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from tools.serve_test_ui import Assets


class Sim:
    def snapshot(self): return {'running':True}
    def configure(self, body): return {'accepted':body['version']}
    def control(self, action): return {'action':action}


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        class Handler(Assets):
            simulation=Sim()
            controller_origin='http://test-controller'
            def log_message(self,*args): pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=self.temp.name))
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True); self.worker.start()
        self.addCleanup(self.cleanup)
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def cleanup(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join()
    def request(self,path,method='GET',origin=None,body=None,content='application/json'):
        headers={'Content-Type':content}
        if origin: headers['Origin']=origin
        data=json.dumps(body).encode() if body is not None else None
        return urlopen(Request(self.base+path,method=method,data=data,headers=headers))
    def test_status_readable_and_expected_origin_can_apply_and_control(self):
        with self.request('/simulation/status') as response: self.assertTrue(json.load(response)['running'])
        with self.request('/simulation/config','POST','http://test-controller',{'version':4}) as response:
            self.assertEqual(json.load(response),{'accepted':4})
        with self.request('/simulation/control','POST','http://test-controller',{'action':'pause'}) as response:
            self.assertEqual(json.load(response),{'action':'pause'})
    def test_cross_origin_missing_origin_and_form_posts_rejected(self):
        for origin in (None,'http://unrelated-site'):
            with self.assertRaises(HTTPError) as caught: self.request('/simulation/config','POST',origin,{'version':4})
            self.assertEqual(caught.exception.code,403)
        with self.assertRaises(HTTPError) as caught:
            self.request('/simulation/config','POST','http://test-controller',{'version':4},'text/plain')
        self.assertEqual(caught.exception.code,400)
    def test_preflight_only_for_expected_origin(self):
        with self.request('/simulation/config','OPTIONS','http://test-controller') as response:
            self.assertEqual(response.status,204)
        with self.assertRaises(HTTPError) as caught: self.request('/simulation/config','OPTIONS','http://unrelated-site')
        self.assertEqual(caught.exception.code,403)
