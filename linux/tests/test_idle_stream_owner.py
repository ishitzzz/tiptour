"""Actual idle-stream loop/policy, explicit capture/client/session doubles."""
import asyncio,ast
from pathlib import Path
from tiptour_linux.screenshot_policy import ScreenshotPolicy
root=ast.parse((Path(__file__).parents[1]/'tiptour_linux/app.py').read_text());fn=next(n for n in ast.walk(root) if isinstance(n,ast.AsyncFunctionDef) and n.name=='stream_frames')
async def case(mode):
 class Client:
  def __init__(self):self.calls=0
  async def send_screenshot(self,j):self.calls+=1
 c=Client();replacement=Client();on=[True];tainted=[mode=='retired'];gen=[1];caps=[];logs=[]
 ns={'asyncio':asyncio,'stream_on':on,'screenshot_policy':ScreenshotPolicy(mode!='off'),'stream_state':{'suppressed':False,'hash':None,'sent':0,'skipped':{'suppressed':0,'plan_active':0,'same_scene':0}},'tainted':tainted,'shell_busy':lambda:False,'_plan_active':lambda:False,'plan_tok':{'n':1},'client':c,'gen':gen,'_dhash':lambda j:123,'log':lambda *x:logs.append(x),'a':object(),'stream_changed':asyncio.Event(),'os':__import__('os')}
 def capture(**kw):
  caps.append(1)
  if mode=='retire_capture':tainted[0]=True
  if mode=='replace_capture':ns['client']=replacement;gen[0]+=1
  if mode=='off_capture':ns['screenshot_policy'].set_enabled(False)
  return None,b'jpeg',None
 ns['capture_clean']=capture
 class Cycle:
  async def wait(self):on[0]=False
  def clear(self):pass
 ns['stream_changed']=Cycle()
 # A stale-capture continue intentionally starts another cycle; make it stop there.
 original=capture
 def once(**kw):
  r=original(**kw)
  if mode.endswith('capture'):on[0]=False
  return r
 ns['capture_clean']=once
 exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'actual-stream','exec'),ns)
 await ns['stream_frames']()
 if mode=='live':assert caps and c.calls==1 and ns['stream_state']['sent']==1
 else:assert c.calls==replacement.calls==0,(mode,logs,c.calls)
 if mode in ('off','retired'):assert not caps
 return caps,c.calls
async def main():
 for mode in ('live','retired','off','retire_capture','replace_capture','off_capture'):await case(mode)
 # Revocation after send() queues dispatch must still run the same owner gate.
 class C:
  calls=0
  async def send_screenshot(self,j):self.calls+=1
 p=ScreenshotPolicy(True);c=C();live=[True]
 t=asyncio.create_task(p.send(c,b'x',p.ticket(),valid=lambda:live[0]));asyncio.get_running_loop().call_soon(lambda:live.__setitem__(0,False));assert not await t and c.calls==0
 print('PASS actual idle loop live send; retired/off no capture; retirement/replacement/off during capture and owner revocation before dispatch refuse, no reconnection')
asyncio.run(main())
