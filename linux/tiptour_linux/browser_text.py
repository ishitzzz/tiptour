"""Restricted Chrome plain input/textarea adapter when AT-SPI exposes Text but no EditableText.
No contenteditable, frames, passwords, saved highlights or implicit field focusing.
CDP object is bound to the current native field by PID/window, label, text, selection and rect.
DOM setters/input events differ from native keyboard/undo semantics; no parity claim.
"""
import asyncio,json,urllib.request,subprocess
import websockets
from . import cdp_resolver as cdp

READ = r'''function(){const e=this,r=e.getBoundingClientRect();return {tag:e.tagName,type:e.type,name:e.getAttribute('aria-label')||(e.labels&&[...e.labels].map(x=>x.innerText).join(' '))||e.placeholder||'',value:e.value,start:e.selectionStart,end:e.selectionEnd,readonly:e.readOnly,disabled:e.disabled,connected:e.isConnected,focused:document.activeElement===e,visible:document.visibilityState==='visible'&&document.hasFocus(),frame:window===top,rect:[screenX+Math.max(0,(outerWidth-innerWidth)/2)+r.x,screenY+outerHeight-innerHeight+r.y,r.width,r.height],dpr:devicePixelRatio,clientrect:[r.x,r.y,r.width,r.height],viewport:[innerWidth,innerHeight]}}'''
WRITE = r'''function(expected,text,operation){
const e=this,r=e.getBoundingClientRect(), hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2), name=e.getAttribute('aria-label')||(e.labels&&[...e.labels].map(x=>x.innerText).join(' '))||e.placeholder||'', rect=[screenX+Math.max(0,(outerWidth-innerWidth)/2)+r.x,screenY+outerHeight-innerHeight+r.y,r.width,r.height];
if(!hit||!(hit===e||e.contains(hit))||name!==expected.name||!e.isConnected||document.activeElement!==e||!document.hasFocus()||document.visibilityState!=='visible'||window!==top||e.readOnly||e.disabled||devicePixelRatio!==1||e.value!==expected.value||e.selectionStart!==expected.start||e.selectionEnd!==expected.end||rect.some((v,i)=>Math.abs(v-expected.rect[i])>2)||e.tagName!==expected.tag||e.type!==expected.type) return {ok:false,error:'bound DOM field/state changed before write'};
const value=operation==='setValue'?text:e.value.slice(0,e.selectionStart)+text+e.value.slice(e.selectionEnd),caret=operation==='setValue'?text.length:e.selectionStart+text.length;
const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
Object.getOwnPropertyDescriptor(proto,'value').set.call(e,value);e.setSelectionRange(caret,caret);
e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:operation==='setValue'?'insertReplacementText':'insertText',data:text}));
const ok=e.isConnected&&document.activeElement===e&&e.value===value&&e.selectionStart===caret&&e.selectionEnd===caret;return {ok,possibly_applied:!ok,retry_safe:false,error:ok?null:'write dispatched but handler changed field/state; outcome uncertain, do not retry automatically',text_verified:e.value===value,caret_verified:e.selectionStart===caret&&e.selectionEnd===caret,chars:text.length,delivery:'identity-bound CDP plain input setter + input event',status:'performed '+operation};}'''

def _xo(*args):
 r=subprocess.run(['xdotool',*args],capture_output=True,text=True,timeout=2)
 if r.returncode: raise RuntimeError('X11 identity unavailable')
 return r.stdout.strip()

async def _write(step,app,native,recheck,check_cancel,dispatch):
 if step.get('_native_range'): return {'ok':False,'error':'saved browser highlight not supported; nothing written'}
 window=_xo('getactivewindow');pid=int(_xo('getwindowpid',window));title=_xo('getwindowname',window)
 if pid!=native['identity']['pid']: raise RuntimeError('native/X11 browser PID differs')
 candidates=[]
 for port in cdp.PORTS:
  try:
   version=json.load(urllib.request.urlopen('http://127.0.0.1:%d/json/version'%port,timeout=.4))
   async with websockets.connect(version['webSocketDebuggerUrl'],open_timeout=2) as w:
    await w.send(json.dumps({'id':1,'method':'SystemInfo.getProcessInfo'}));info=json.loads(await asyncio.wait_for(w.recv(),3))
    if not any(p['type']=='browser' and p['id']==pid for p in info['result']['processInfo']):continue
   for t in json.load(urllib.request.urlopen('http://127.0.0.1:%d/json'%port,timeout=.4)):
    if t.get('type')=='page' and t.get('title') and title.startswith(t['title']):candidates.append(t)
  except Exception:continue
 if len(candidates)!=1:raise RuntimeError('need exactly one PID/window-bound browser page')
 async with websockets.connect(candidates[0]['webSocketDebuggerUrl'],open_timeout=2,max_size=None) as w:
  seq=0
  async def call(method,params):
   nonlocal seq
   seq+=1;await w.send(json.dumps({'id':seq,'method':method,'params':params}))
   while True:
    result=json.loads(await asyncio.wait_for(w.recv(),4))
    if result.get('id')==seq:
     if 'error' in result:raise RuntimeError('CDP command failed')
     return result['result']
  obj=await call('Runtime.evaluate',{'expression':'document.activeElement','returnByValue':False});oid=obj['result'].get('objectId')
  if not oid:raise RuntimeError('no remote active DOM object')
  read=await call('Runtime.callFunctionOn',{'objectId':oid,'functionDeclaration':READ,'returnByValue':True});s=read['result'].get('value') or {}
  if not (s.get('connected') and s.get('focused') and s.get('visible') and s.get('frame') and s.get('dpr')==1):raise RuntimeError('DOM field not visible/focused/top-frame')
  if s.get('tag') not in ('INPUT','TEXTAREA') or s.get('type') not in ('text','search','url','tel','email','textarea'):raise RuntimeError('unsupported or secret browser input type')
  if s.get('readonly') or s.get('disabled'):raise RuntimeError('browser input not writable')
  if not native.get('editable_state') or native.get('native_editable_iface') or native.get('password'):raise RuntimeError('not the supported native fallback case')
  if not native.get('name') or native['name'].strip()!=s.get('name','').strip():raise RuntimeError('native/DOM accessible label differs')
  if native.get('text')!=s.get('value') or len(s.get('value',''))>=20000:raise RuntimeError('native/DOM text differs or incomplete')
  nr=native.get('element_rect')
  doc = native.get('document_rect')
  if not doc or any(abs(a-b)>2 for a,b in zip(doc[2:],s['viewport'])):raise RuntimeError('native viewport dimensions differ %r vs %r' % (doc,s['viewport']))
  mapped = [doc[0]+s['clientrect'][0],doc[1]+s['clientrect'][1],*s['clientrect'][2:]]
  if not nr or any(abs(a-b)>2 for a,b in zip(nr,mapped)):raise RuntimeError('native/DOM field bounds differ %r vs %r' % (nr,s['rect']))
  # AT-SPI offsets count codepoints; DOM selection offsets count UTF-16 code units.
  def utf16offset(n):return len(s['value'][:n].encode('utf-16-le'))//2
  sel=native.get('selection') or [native.get('caret'),native.get('caret')]
  if None in sel or [utf16offset(n) for n in sel]!=[s.get('start'),s.get('end')]:raise RuntimeError('native/DOM selection differs')
  fresh=recheck()
  if any(fresh.get(k)!=native.get(k) for k in ('identity','text','selection','caret','element_rect','editable_state','document_rect')):raise RuntimeError('native field changed during DOM binding')
  if _xo('getactivewindow')!=window or int(_xo('getwindowpid',window))!=pid:raise RuntimeError('X11 identity changed before browser write')
  check_cancel('browser object write')
  dispatch['possible']=True  # Set before transport send: an exception may mean the remote write landed.
  result=await call('Runtime.callFunctionOn',{'objectId':oid,'functionDeclaration':WRITE,'arguments':[{'value':s},{'value':str(step.get('value') if step.get('value') is not None else step.get('label',''))},{'value':step['type']}],'returnByValue':True})
  if result.get('exceptionDetails'):return {'ok':False,'possibly_applied':True,'retry_safe':False,'error':'browser write exception; may have applied, do not retry automatically'}
  return result['result'].get('value') or {'ok':False,'possibly_applied':True,'retry_safe':False,'error':'browser write result unavailable; may have applied, do not retry automatically'}

def write(step,app,native,recheck,check_cancel):
 dispatch={'possible':False}
 try:return asyncio.run(_write(step,app,native,recheck,check_cancel,dispatch))
 except Exception as e:
  possible=dispatch['possible']
  return {'ok':False,'possibly_applied':possible,'retry_safe':False,'error':str(e)+('; browser write may have applied, do not retry automatically' if possible else '; nothing dispatched by browser adapter')}
