"""Exercise actual nested readiness code with adversarial read outcomes, no OS/model."""
import ast,asyncio,pathlib,types
from tiptour_linux.app_transition import context_matches,same_window
root=ast.parse(pathlib.Path('tiptour_linux/app.py').read_text());f=next(n for n in ast.walk(root) if isinstance(n,ast.AsyncFunctionDef) and n.name=='_transition_ready')
base={'app':'Mousepad','pid':22,'x11_client_id':7,'window_path':'native/7','window_name':'Untitled','mapping':{'rect':[1,2,3,4]}}
async def case(seq,pids,change=None,timeout=.2):
 calls=[];token={'n':1};prop={'state':'approved'};clock=[0.]
 def active(_timeout):
  calls.append(1)
  if change:change(token,prop)
  item=seq.pop(0) if seq else None
  if isinstance(item,Exception):raise item
  return item
 async def sleep(sec):clock[0]+=sec
 ns={'__name__':'tiptour_linux.app','__package__':'tiptour_linux','plan_tok':token,'prop':prop,
     'atspi_resolver':types.SimpleNamespace(active_context=active),'time':types.SimpleNamespace(monotonic=lambda:clock[0]),
     'asyncio':types.SimpleNamespace(to_thread=asyncio.to_thread,sleep=sleep)}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[f],type_ignores=[])),'actual-readiness','exec'),ns)
 return await ns['_transition_ready']('Mousepad',1,pids,timeout),calls
async def run():
 old=dict(base,pid=11,x11_client_id=5);other=dict(base,app='Other')
 r,c=await case([old,base],[22]);assert r==base and len(c)==2
 r,c=await case([other,old],[22]);assert r is None
 for p in [None,[],[0],[-1],['22'],[True]]:
  r,c=await case([base],p);assert r is None and not c
 for change in [lambda t,p:t.update(n=2),lambda t,p:p.update(state='stopped')]:
  r,c=await case([base],[22],change);assert r is None and len(c)==1
 r,c=await case([RuntimeError('unverifiable'),base],[22]);assert r==base
 # Next-step immutable destination remains exact, not a same-name relaxation.
 assert not same_window(base,dict(base,x11_client_id=8))
 assert not same_window(base,dict(base,pid=11))
 assert not context_matches(base,'Mousepad',('8','Untitled'))
asyncio.run(run());print('PASS actual readiness: launched PID required, old same-app/other app/unverifiable/timeout/revocation refused; immutable exact window checks retained')
# Actual modal body: exact process only, all its windows still block on dialogs.
f=next(n for n in ast.walk(ast.parse(pathlib.Path('tiptour_linux/atspi_resolver.py').read_text())) if isinstance(n,ast.FunctionDef) and n.name=='_modal_title')
class State:
 def contains(self,k):return k in ('show','visible','modal')
class Window:
 def __init__(self,dialog=False):self.dialog=dialog
 def get_state_set(self):
  return types.SimpleNamespace(contains=lambda k:k in ('show','visible') or self.dialog and k=='modal')
 def get_name(self):return 'Dialog' if self.dialog else 'Doc'
 def get_role_name(self):return 'dialog' if self.dialog else 'frame'
class App:
 def __init__(self,pid,dialog=False):self.pid=pid;self.windows=[Window(),Window(dialog)]
 def get_name(self):return 'Mousepad'
 def get_process_id(self):return self.pid
 def get_child_count(self):return len(self.windows)
 def get_child_at_index(self,i):return self.windows[i]
apps=[App(11,True),App(22)]
desk=types.SimpleNamespace(get_child_count=lambda:len(apps),get_child_at_index=lambda i:apps[i])
ns={'Atspi':types.SimpleNamespace(get_desktop=lambda _:desk,StateType=types.SimpleNamespace(SHOWING='show',VISIBLE='visible',MODAL='modal')),'_is_self':lambda _:False,'MODAL_ROLES':{'dialog','alert','file chooser'}}
exec(compile(ast.fix_missing_locations(ast.Module(body=[f],type_ignores=[])),'actual-modal','exec'),ns)
modal=ns['_modal_title'];assert modal('Mousepad',22) is None;assert modal('Mousepad',11)=='Dialog'
for p in [None,0,-1,True,999]:
 try:modal('Mousepad',p);raise AssertionError(p)
 except TimeoutError:pass
apps[1].windows[1]=Window(True);assert modal('Mousepad',22)=='Dialog'
try:modal('Other',22);raise AssertionError('wrong app')
except TimeoutError:pass
print('PASS actual modal: exact PID, all dialogs inspected; missing/wrong app/PID/ambiguous unavailable')
