"""Conservative ownership of an approved Enter's focused GET-form navigation.
No actions are dispatched here. Unsupported forms return no observer.
"""
import asyncio,json,urllib.request,urllib.parse,time,subprocess
import websockets

def window():
 def x(*a):return subprocess.run(['xdotool',*a],capture_output=True,text=True,timeout=2).stdout.strip()
 w=x('getactivewindow');return (w,int(x('getwindowpid',w)))
def canonical(url):
 u=urllib.parse.urlsplit(url);return (u.scheme,u.netloc,u.path,tuple(sorted(urllib.parse.parse_qsl(u.query,keep_blank_values=True))))
JS="""(()=>{const e=document.activeElement,f=e&&e.form;if(!document.hasFocus()||document.visibilityState!=='visible'||!f||f.method.toLowerCase()!=='get'||f.target&&f.target!=='_self')return null;const u=new URL(f.action,location.href);u.search=new URLSearchParams(new FormData(f)).toString();return {expected:u.href,url:location.href}})()"""
class Navigation:
 def __init__(self,ws,target,owner):self.ws=ws;self.target=target;self.owner=owner;self.seq=0;self.events=[];self.pending={};self.hidden=False;self.blurred=False;self.allow_find_blur=False;self.retired=False;self.script=None;self.task=asyncio.create_task(self.recv())
 async def recv(self):
  try:
   async for raw in self.ws:
    e=json.loads(raw)
    if 'id' in e:
     f=self.pending.pop(e['id'],None)
     if f and not f.done():f.set_result(e)
    else:
     if e.get('method')=='Runtime.bindingCalled' and e.get('params',{}).get('name')=='__ttNavigationState':
      value=e['params'].get('payload')
      if value=='hidden':self.hidden=True
      if value=='blur' and not self.allow_find_blur:self.blurred=True
     self.events.append(e)
  except Exception as e:
   for f in self.pending.values():
    if not f.done():f.set_exception(e)
 async def cmd(self,method,params=None):
  self.seq+=1;f=asyncio.get_running_loop().create_future();self.pending[self.seq]=f
  await self.ws.send(json.dumps({'id':self.seq,'method':method,'params':params or {}}));r=await asyncio.wait_for(f,3)
  if 'error' in r:raise RuntimeError(str(r['error']))
  return r['result']
 async def eval(self,js):return (await self.cmd('Runtime.evaluate',{'expression':js,'returnByValue':True}))['result'].get('value')
 def retire(self):
  self.retired=True
 async def close(self):
  self.retired=True
  try:
   if self.script:await self.cmd('Page.removeScriptToEvaluateOnNewDocument',{'identifier':self.script})
   await self.eval("if(window.__ttNavWatch){removeEventListener('blur',__ttNavWatch.b);removeEventListener('visibilitychange',__ttNavWatch.v);delete window.__ttNavWatch}")
   await self.cmd('Runtime.removeBinding',{'name':'__ttNavigationState'})
  except Exception:pass
  await self.ws.close();self.task.cancel()
 async def settle(self,eligible):
  end=time.monotonic()+12;req=None;loader=None;url=None
  while time.monotonic()<end:
   if self.retired or self.hidden or self.blurred or not eligible() or await asyncio.to_thread(window)!=self.owner:raise RuntimeError('navigation owner revoked or active window/PID changed')
   # A different tab becoming active is never an opportunity to reacquire.
   if not await self.eval("document.visibilityState==='visible'&&document.hasFocus()"):raise RuntimeError('owned navigation tab lost focus')
   for ev in self.events:
    if ev.get('method')!='Network.requestWillBeSent':continue
    p=ev['params']
    if p.get('type')!='Document' or p.get('frameId')!=self.frame:continue
    if req is None:
     if canonical(p['request']['url'])!=canonical(self.expected):raise RuntimeError('navigation is not the approved focused GET form')
     req=p['requestId'];loader=p['loaderId'];url=p['request']['url']
    elif p['requestId']!=req or not p.get('redirectResponse'):raise RuntimeError('new unowned document navigation')
    else:url=p['request']['url']
   self.events.clear()
   if req:
    tree=(await self.cmd('Page.getFrameTree'))['frameTree']['frame']
    ready=await self.eval("document.readyState==='complete'&&document.visibilityState==='visible'&&document.hasFocus()")
    if ready and tree.get('loaderId')==loader and tree.get('url')==url:
     self.proof={'target':self.target,'frame':self.frame,'loader':loader,'url':url,'window':self.owner};return self.proof
   await asyncio.sleep(.1)
  raise RuntimeError('approved navigation did not settle within bound')
 async def check(self, browser_ui=False):
  try:return await self._check(browser_ui)
  except Exception:return False
 async def preflight(self):
  if self.retired or self.hidden or self.blurred or await asyncio.to_thread(window)!=self.owner:return False
  current=await self.eval(JS)
  return bool(current and canonical(current['expected'])==canonical(self.expected) and current['url']==self.original_url)
 async def _check(self, browser_ui=False):
  if any(e.get("method")=="Network.requestWillBeSent" and e.get("params",{}).get("type")=="Document" and e["params"].get("frameId")==self.frame for e in self.events):return False
  if self.retired or self.hidden or self.blurred or await asyncio.to_thread(window)!=self.owner:return False
  tree=(await self.cmd('Page.getFrameTree'))['frameTree']['frame'];p=self.proof
  return (tree.get('id')==p['frame'] and tree.get('loaderId')==p['loader'] and tree.get('url')==p['url'] and
          await self.eval("document.visibilityState==='visible'" if browser_ui else "document.visibilityState==='visible'&&document.hasFocus()"))
async def prepare():
 """Unique focused CDP target in the active native browser process, or none."""
 owner=await asyncio.to_thread(window);matches=[]
 for port in range(9222,9231):
  try:
   def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:%d/%s'%(port,path),timeout=.4))
   v=await asyncio.to_thread(get,'json/version')
   async with websockets.connect(v['webSocketDebuggerUrl'],open_timeout=1) as b:
    await b.send(json.dumps({'id':1,'method':'SystemInfo.getProcessInfo'}));proc=json.loads(await asyncio.wait_for(b.recv(),2))['result']['processInfo']
   if owner[1] not in [p['id'] for p in proc if p['type']=='browser']:continue
   targets=await asyncio.to_thread(get,'json')
   for t in targets:
    if t.get('type')!='page':continue
    ws=await websockets.connect(t['webSocketDebuggerUrl'],open_timeout=1);n=Navigation(ws,t['id'],owner)
    try:
     form=await n.eval(JS)
     if not form:await n.close();continue
     await n.cmd('Network.enable');await n.cmd('Page.enable');await n.cmd('Runtime.enable')
     await n.cmd('Runtime.addBinding',{'name':'__ttNavigationState'})
     watch="window.__ttNavWatch={b:()=>__ttNavigationState('blur'),v:()=>{if(document.visibilityState==='hidden')__ttNavigationState('hidden')}};addEventListener('blur',__ttNavWatch.b);addEventListener('visibilitychange',__ttNavWatch.v);"
     n.script=(await n.cmd('Page.addScriptToEvaluateOnNewDocument',{'source':watch}))['identifier'];await n.eval(watch)
     frame=(await n.cmd('Page.getFrameTree'))['frameTree']['frame'];n.frame=frame['id'];n.expected=form['expected'];n.original_url=form['url'];matches.append(n)
    except Exception:await n.close()
  except Exception:continue
 if len(matches)==1 and await asyncio.to_thread(window)==owner:return matches[0]
 for n in matches:await n.close()
 return None
