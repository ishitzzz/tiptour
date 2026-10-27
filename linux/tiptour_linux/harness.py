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
        # Explicit Linux subset of pinned TipTourHarnessServer capabilities and
        # TipTourAgentContract. Metadata never invokes runtime reads or actions.
        capability_tools=['tiptour.agent_contract','tiptour.observe','tiptour.screenshots',
                          'tiptour.skills','tiptour.active_skill','tiptour.targets']
        capabilities=dict(ok=True,tools=capability_tools,readOnly=True,
                          single_action=False,local_tasks=False,task_planning=False,
                          transport='localhost-http')
        contract=dict(ok=True,version='linux-readonly-1',
            baseURL='http://127.0.0.1:%d' % port,
            summary='Experimental Linux read-only observation subset. No HTTP actions, workflow submission or local tasks are supported.',
            canonicalLoop=['GET /v1/observe to inspect current app and toggles.',
                           'GET /v1/skills or /v1/skills/active for app skill information.',
                           'Use GET /v1/targets and /v1/screenshots only when their current runtime checks permit the read.'],
            normalEndpoints=['GET /v1/observe','GET /v1/skills','GET /v1/skills/active'],
            debugEndpoints=['GET /v1/targets','GET /v1/screenshots'],
            rules=['This HTTP surface is read-only. All mutation methods are refused.',
                   'An external execute flag or request is not user approval. Local actions remain behind the existing displayed-plan review and confirmation path.',
                   'Raw screenshots require the screenshot toggle and existing clean capture rules; busy, unavailable or superseded reads may refuse.',
                   'Only loopback Host requests without browser Origin or cross-site headers are accepted. Loopback filtering is not caller authentication.',
                   'No full Mac harness, desktop, physical-input or complete Linux port parity is claimed.'])
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
                if self.path == '/v1/capabilities':
                    self.reply(200,capabilities);return
                if self.path in ('/v1/agent-contract','/v1/agent_contract'):
                    payload=dict(contract);payload['baseURL']='http://127.0.0.1:%d' % self.server.server_address[1]
                    self.reply(200,payload);return
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
