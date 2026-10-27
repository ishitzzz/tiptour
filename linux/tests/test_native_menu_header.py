"""Actual native-walk source with explicit AT-SPI node/coordinate doubles."""
import ast,types
from pathlib import Path
root=ast.parse((Path(__file__).parents[1]/'tiptour_linux/atspi_resolver.py').read_text());fn=next(n for n in root.body if isinstance(n,ast.FunctionDef) and n.name=='walk')
class States:
 def __init__(self,enabled=True):self.enabled=enabled
 def contains(self,s):return self.enabled if s=='enabled' else True
class Node:
 def __init__(self,role,label='',parent=None,enabled=True):self.role=role;self.label=label;self.parent=parent;self.enabled=enabled;self.children=[];self.path='/'+label
 def get_child_count(self):return len(self.children)
 def get_child_at_index(self,i):return self.children[i]
 def get_state_set(self):return States(self.enabled)
 def get_role_name(self):return self.role
 def get_parent(self):return self.parent
 def get_name(self):return self.label
 def get_process_id(self):return 123
 def get_application(self):return types.SimpleNamespace(get_name=lambda:'fixture')
bar=Node('menu bar');head=Node('menu','Edit',bar);popup=Node('menu','Popup',Node('frame'));disabled=Node('menu','Disabled',bar,False);button=Node('push button','Edit',Node('frame'));orphan=Node('menu','Unknown');rootnode=Node('application');rootnode.children=[head,popup,disabled,button,orphan]
ns={'Atspi':types.SimpleNamespace(StateType=types.SimpleNamespace(SHOWING='showing',VISIBLE='visible',ENABLED='enabled')),'CLICKABLE':{'push button'},'_screen_rect':lambda n,*x:{'rect':[10,20,40,25]},'CoordinateError':RuntimeError}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'actual-walk','exec'),ns)
r=ns['walk'](rootnode);assert [(x['label'],x['role']) for x in r]==[('Edit','menu'),('Edit','push button')],r
assert r[0]['native_identity']=={'pid':123,'path':'/Edit'} and r[0]['coordinate_mapping']['rect']==[10,20,40,25]
print('PASS actual native walk: enabled direct menu-bar header retained with native identity/mapping; popup/disabled/orphan menu excluded; existing button unchanged')
