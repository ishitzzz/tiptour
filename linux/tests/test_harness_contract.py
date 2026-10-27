import json,urllib.request,urllib.error,threading
from tiptour_linux.harness import ReadOnlyHarness
calls=[]
h=ReadOnlyHarness(lambda method:calls.append(method) or {'ok':True,'method':method},port=0);h.start()
def req(path,method='GET',headers=None):
 r=urllib.request.Request('http://127.0.0.1:%d%s'%(h.port,path),method=method,headers=headers or {})
 try:
  with urllib.request.urlopen(r) as f:return f.status,json.load(f)
 except urllib.error.HTTPError as e:return e.code,json.load(e)
try:
 cap=req('/v1/capabilities');contract=req('/v1/agent-contract');alias=req('/v1/agent_contract')
 assert cap[0]==contract[0]==alias[0]==200 and contract[1]==alias[1]
 assert contract[1]['baseURL']=='http://127.0.0.1:%d'%h.port
 assert cap[1]['readOnly'] and not cap[1]['single_action'] and not cap[1]['local_tasks']
 assert not any(x in cap[1]['tools'] for x in ['tiptour.act','tiptour.submit_workflow_plan','tiptour.tasks']) and calls==[]
 denied=[]
 for path in ['/v1/capabilities','/v1/agent-contract','/v1/agent_contract']:
  for hdr in [{'Host':'evil.invalid'},{'Origin':'http://localhost'},{'Sec-Fetch-Site':'cross-site'},{'Sec-Fetch-Site':'same-site'}]:
   code,p=req(path,headers=hdr);assert code==403,(path,hdr,code);denied.append([path,hdr,code])
 for method in ['POST','PUT','PATCH','DELETE','OPTIONS']:
  assert req('/v1/capabilities',method)[0]==405
 assert req('/v1/act')[0]==404 and req('/v1/workflow-plan','POST')[0]==405
 assert calls==[]
 assert req('/v1/observe')[1]['method']=='observe' and calls==['observe']
 print('read-only HTTP metadata, aliases, ephemeral base URL, denied host/origin/site, refused mutations, and zero metadata runtime calls: pass')
finally:h.stop()
