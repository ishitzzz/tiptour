"""Opt-in loopback READ-ONLY subset of pinned TipTourHarnessServer.

No action/task/plan endpoint is registered. Browser cross-origin requests are
refused. Captures honor the existing screenshot toggle and capture exclusion.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json, threading


class ReadOnlyHarness:
    def __init__(self, invoke, port=19474):
        routes={'/v1/observe':'observe','/v1/skills':'skills','/v1/skills/active':'active_skill',
                '/v1/active-skill':'active_skill','/v1/active_skill':'active_skill',
                '/v1/targets':'targets','/v1/grounding-targets':'targets',
                '/v1/screenshots':'screenshots','/v1/screenshot':'screenshots'}
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(2)
                super().setup()
            def log_message(self,*args): pass
            def reply(self,code,data):
                body=json.dumps(data,allow_nan=False).encode()
                self.send_response(code);self.send_header('Content-Type','application/json')
                self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            def do_GET(self):
                host = (self.headers.get('Host') or '').split(':',1)[0].lower()
                if host not in ('127.0.0.1','localhost'):
                    self.reply(403,dict(ok=False,reason='non_loopback_host'));return
                if self.headers.get('Origin') is not None or self.headers.get('Sec-Fetch-Site') in ('cross-site','same-site'):
                    self.reply(403,dict(ok=False,reason='browser_origin_not_allowed'));return
                if self.path in ('/health','/v1/health'):
                    self.reply(200,dict(ok=True,service='tiptour-harness',readOnly=True));return
                if self.path not in routes:
                    self.reply(404,dict(ok=False,reason='not_found'));return
                try: value=invoke(routes[self.path])
                except Exception: self.reply(503,dict(ok=False,reason='runtime_unavailable'));return
                self.reply(200,value)
            def do_POST(self): self.reply(405,dict(ok=False,reason='read_only_harness'))
            do_PUT=do_POST;do_PATCH=do_POST;do_DELETE=do_POST;do_OPTIONS=do_POST
        self.server=HTTPServer(('127.0.0.1',port),Handler)
        self.server.timeout=2
        self.port=self.server.server_address[1]
    def start(self):
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name='readonly-harness');self.thread.start()
    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
