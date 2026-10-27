"""Boundary doubles for live native selection. Runtime GTK/Gemini proof is separate."""
import copy,json,threading
from types import SimpleNamespace
from tiptour_linux import actions as a,atspi_resolver as ar
base={'identity':{'pid':123,'element_path':'field','window_path':'window'},'text':'prefix OLD suffix','selection':[7,10],'caret':10,'element_rect':[5,5,300,30],'document_rect':None,'editable':True,'password':False,'name':'Draft','ok':True}
live={k:copy.deepcopy(base[k]) for k in ('identity','text','selection','caret','element_rect','document_rect')}
step={'type':'type','value':'NEW','_live_selection':live}
a._skill_numeric_text=lambda *x:None
a._focus=lambda *x:'simulated focus'
a._TL.bound=(('11',123),base['identity'])
a._TL.cancel=None
a._TL.expected_window=None
a._TL.expected_focus=None
a._TL.navigation_guard=None
a._TL.click_guard=None
ar.Atspi=SimpleNamespace(StateType=SimpleNamespace(FOCUSED=1,EDITABLE=2))
calls=[]
a._run=lambda *args:(calls.append(args) or json.dumps({'ok':True}))
a._check_bound=lambda *x:copy.deepcopy(base)
assert a._native_text(step,'test')['ok'] and len(calls)==1
assert json.loads(calls[0][-1])['live_selection']==live
for key,value in [('text','drift'),('selection',[0,6]),('caret',0),('identity',{'pid':123,'element_path':'other'}),('element_rect',[1,2,3,4]),('editable',False)]:
 calls.clear();changed=copy.deepcopy(base);changed[key]=value
 for final_only in (False,True):
  n=[0]
  def check(*args):
   n[0]+=1
   return copy.deepcopy(changed if not final_only or n[0]>1 else base)
  a._check_bound=check
  try:a._native_text(step,'test');raise AssertionError('accepted drift '+key)
  except a._XFail:pass
  assert not calls
# The child must compare BOTH snapshots with the app-owned selection, including geometry.
class Text:
 def set_text_contents(self,text):self.text=text;return True
 def set_caret_offset(self,n):self.caret=n;return True
 def get_caret_offset(self):return self.caret
 def get_n_selections(self):return 0
 def get_character_count(self):return len(self.text)
 def get_text(self,*args):return self.text
class Node:
 def __init__(self):self.t=Text();self.t.text=base['text'];self.t.caret=10
 def get_state_set(self):return SimpleNamespace(contains=lambda *args:True)
 def get_role_name(self):return 'text'
 def get_editable_text_iface(self):return self.t
 def get_text_iface(self):return self.t
import subprocess
original_run=subprocess.run
subprocess.run=lambda *args,**kw:SimpleNamespace(returncode=0,stdout='11\n')
ar._modal_title=lambda *args:None
req={'operation':'type','text':'NEW','app':'test','identity':base['identity'],'xwindow':'11','live_selection':live}
try:
 for key,value in [('text','drift'),('selection',[0,6]),('caret',0),('identity',{'pid':123,'element_path':'other'}),('element_rect',[1,2,3,4])]:
  for second in (False,True):
   node=Node();n=[0]
   def record(*args):
    n[0]+=1;f=copy.deepcopy(base)
    if not second or n[0]>1:f[key]=value
    return node,f
   ar._focused_record=record
   r=ar._focused_write(req);assert not r['ok'] and node.t.text==base['text'],(key,second,r)
 node=Node();ar._focused_record=lambda *args:(node,copy.deepcopy(base))
 r=ar._focused_write(req);assert r['ok'] and node.t.text=='prefix NEW suffix' and node.t.caret==10,r
 # Saved initial range still works independently; it is not relabeled as live.
 saved={'identity':base['identity'],'xwindow':'11','text':base['text'],'selection':[7,10]}
 node=Node();ar._focused_record=lambda *args:(node,copy.deepcopy(base))
 r=ar._focused_write(dict(req,live_selection=None,saved_range=saved));assert r['ok'] and node.t.text=='prefix NEW suffix',r
 node=Node();ar._focused_record=lambda *args:(node,dict(copy.deepcopy(base),text='changed'))
 r=ar._focused_write(dict(req,live_selection=None,saved_range=saved));assert not r['ok'] and node.t.text==base['text'],r
finally:subprocess.run=original_run
print('PASS simulated action preflight/final drift; child two-snapshot text/range/caret/identity/geometry; partial replacement; saved-range unchanged/stale refusal')
