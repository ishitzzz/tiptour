"""Private menu proof logic with explicit native-source doubles, not native UI."""
import copy
from tiptour_linux.menu_guidance import capture,valid_record,revalidate
from tiptour_linux.request_limits import forbidden_plan
text='Show me where the Edit menu is so I can open it. Do not edit, save, or close the document.'
args={'app':'mousepad','goal':'Open Edit menu','steps':[{'type':'click','label':'Edit','hint':'Open Edit menu'}]}
ctx={'app':'mousepad','pid':123,'window_path':'w','x11_client_id':7}
target={'label':'Edit','role':'menu','menu_header':True,'app':'mousepad','rect':[39,31,41,25],'coordinate_mapping':{'pid':123,'window_path':'w'},'native_identity':{'pid':123,'path':'edit'}}
class Native:
 def __init__(self):self.ctx=copy.deepcopy(ctx);self.targets=[copy.deepcopy(target)]
 def modal_title(self,*a,**kw):return ('ok',None)
 def active_context(self):return copy.deepcopy(self.ctx)
 def resolve(self,*a):return copy.deepcopy(self.targets)
n=Native();assert forbidden_plan(text,args);p=capture(text,args,n);assert p and valid_record(p,text,args) and revalidate(p,n);assert not forbidden_plan(text,args,menu_proof=p)
for key,val in [('role','push button'),('menu_header',False),('rect',[40,31,41,25]),('native_identity',{'pid':123,'path':'new'})]:
 n.targets=[dict(target,**{key:val})];assert not revalidate(p,n)
for ts in ([],[target,target],[dict(target,rect=[0,0,0,10])],[dict(target,native_identity={'pid':999,'path':'edit'})]):
 n.targets=ts;assert not capture(text,args,n)
n.targets=[copy.deepcopy(target)];n.ctx=dict(ctx,pid=999);assert not revalidate(p,n)
n.ctx=copy.deepcopy(ctx)
for modal in [('unavailable',None),('ok','Blocking')]:
 n.modal_title=lambda *a,**kw:modal
 assert not capture(text,args,n) and not revalidate(p,n)
n.modal_title=lambda *a,**kw:('ok',None)
for s in ({'type':'type','label':'Edit','value':'x'},{'type':'click','label':'Edit document'},{'type':'click','label':'Edit','hint':'Paste text'},{'type':'click','label':'Edit','targetContext':'focusedElement'}):
 a=dict(args,steps=[s]);assert not capture(text,a,n) and forbidden_plan(text,a,menu_proof=p)
assert not capture('Do not click the Edit menu',args,n)
assert forbidden_plan(text,dict(args,steps=args['steps']+[{'type':'type','label':'Text','value':'x'}]),menu_proof=p)
print('PASS private native-menu proof required; label/request alone refuse; role/parent/path/PID/rect/ambiguity changes and destructive plans refuse')
# The app must re-check operation ownership after final awaited native proof,
# before arming; legacy fallback Retry may never use a cached menu proof.
from pathlib import Path
source=(Path(__file__).parents[1]/'tiptour_linux/app.py').read_text()
final=source.index('                if _menu_bound and (a.act or not await read(_menu_revalidate')
arm=source.index('                _cd_status = _arm_block',final)
assert "plan_tok['n'] != _gen0 or not _approved_step(args,idx,step)" in source[final:arm]
control=source[source.index('    def _control('):source.index('    async def run():')]
assert "if cur.get('menu_proof'):" in control and control.index("if cur.get('menu_proof'):") < control.index('def _retry_tail')
print('PASS app final-await owner check precedes arm; legacy bound-menu Retry refuses cached rearm (source contract, not runtime)')
# Execute the actual queued-retirement closure AST with controlled owner/hit state.
import ast,threading
source=(Path(__file__).parents[1]/'tiptour_linux/app.py').read_text()
node=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='_retire_menu')
class Clicks:
 def __init__(self):self.disarmed=0
 def disarm(self):self.disarmed+=1
class GL:
 @staticmethod
 def idle_add(fn):pass
class Overlay:
 @staticmethod
 def retire():pass
for live,hit,expected in [(True,False,1),(True,True,0),(False,False,0)]:
 clicked=threading.Event()
 if hit:clicked.set()
 clicks=Clicks();tok={'n':4};events=[];ov={'hidden':False}
 env={'glock':threading.RLock(),'_live':lambda:live,'_menu_clicked':clicked,'ov':ov,'clicks':clicks,'plan_tok':tok,'GLib':GL,'overlay':Overlay,'click_events':events}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'retire-contract','exec'),env)
 env['_retire_menu']()
 assert clicks.disarmed==expected and tok['n']==4+expected and len(events)==expected
print('PASS actual queued retire closure refuses target-hit or stale owner; revokes unclicked live proof')
