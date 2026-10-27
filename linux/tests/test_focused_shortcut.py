"""Actual action driver binding/dispatch; native reads/OS dispatch are explicit doubles."""
from tiptour_linux import actions as a,atspi_resolver as ar
import copy,threading
identity={'pid':123,'window_path':'w','element_path':'field','window_name':'Doc','window_rect':[0,0,500,500]}
f={'ok':True,'identity':identity,'element_rect':[10,30,400,400],'password':False}
state={'field':f};calls=[]
a.focus_info=lambda *x,**kw:copy.deepcopy(state['field']);a.activate_target=lambda *x,**kw:(True,'test');a._window_state=lambda:('7',123);ar.modal_title=lambda *x,**kw:('ok',None);a._x=lambda *x:calls.append(x)
step={'type':'keyboardShortcut','label':'control+a','targetContext':'focusedElement'}
assert not a.execute(step,None,'test')['ok'] and not calls
b=a.focused_shortcut_recipient('test',('7',123));assert b and not a.focused_shortcut_recipient('test',('8',456))
for change in [dict(f,password=True),dict(f,element_rect=[0,0,0,10]),dict(f,element_rect=None),dict(f,ok=False)]:
 state['field']=change;assert a.focused_shortcut_recipient('test') is None
state['field']=f;r=a.execute(dict(step,**b),None,'test');assert r['ok'] and calls[-1]==('key','--clearmodifiers','ctrl+a');calls.clear()
for change in [dict(f,identity=dict(identity,element_path='other')),dict(f,element_rect=[11,30,400,400])]:
 state['field']=change;assert not a.execute(dict(step,**b),None,'test')['ok'] and not calls
state['field']=f
ar.modal_title=lambda *x,**kw:('unavailable',None);assert not a.execute(dict(step,**b),None,'test')['ok'] and not calls
ar.modal_title=lambda *x,**kw:('ok','Dialog');assert not a.execute(dict(step,**b),None,'test')['ok'] and not calls
ar.modal_title=lambda *x,**kw:('ok',None);ev=threading.Event();ev.set();assert not a.execute(dict(step,**b),None,'test',cancel=ev)['ok'] and not calls
print('PASS actual driver focused shortcut: binding required, keys match, wrongPID/secret/missinggeometry/refocus/move/modal/Stop refuse without dispatch')
