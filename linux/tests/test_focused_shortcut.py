"""Actual action driver binding/dispatch; native reads/OS dispatch are explicit doubles. Mac-faithful dispatch (Ishit 1:24 / main 1:28): focusedElement keyboard shortcuts POST without a recipient binding gate - Mac WorkflowRunner L1085-1114 activates the target app and posts the shortcut, operation-token gate only. focused_shortcut_recipient stays a strict read-only bind (unchanged); it is advisory context for the app-side approval, not a dispatch gate. The old binding-required/identity-change/modal refusal assertions encoded the removed Linux-only gate."""
import sys;from pathlib import Path;sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tiptour_linux import actions as a,atspi_resolver as ar
import copy,threading
identity={'pid':123,'window_path':'w','element_path':'field','window_name':'Doc','window_rect':[0,0,500,500]}
f={'ok':True,'identity':identity,'element_rect':[10,30,400,400],'password':False}
state={'field':f};calls=[]
a.focus_info=lambda *x,**kw:copy.deepcopy(state['field']);a.activate_target=lambda *x,**kw:(True,'test');a._window_state=lambda:('7',123);ar.modal_title=lambda *x,**kw:('ok',None);a._x=lambda *x:calls.append(x)
# The read-only bind helper is unchanged and strict.
b=a.focused_shortcut_recipient('test',('7',123));assert b and not a.focused_shortcut_recipient('test',('8',456))
for change in [dict(f,password=True),dict(f,element_rect=[0,0,0,10]),dict(f,element_rect=None),dict(f,ok=False)]:
 state['field']=change;assert a.focused_shortcut_recipient('test') is None
state['field']=f
# Mac-faithful: the shortcut dispatches WITHOUT a binding (no recipient gate).
step={'type':'keyboardShortcut','label':'control+a','targetContext':'focusedElement'}
r=a.execute(step,None,'test');assert r['ok'] and calls[-1]==('key','--clearmodifiers','ctrl+a'),(r,calls)
# With a binding present it dispatches identically (advisory context, not a gate).
calls.clear();r=a.execute(dict(step,**b),None,'test');assert r['ok'] and calls[-1]==('key','--clearmodifiers','ctrl+a')
# Focus/PID/rect changes do NOT gate dispatch (no identity re-read on the key path).
for change in [dict(f,identity=dict(identity,element_path='other')),dict(f,element_rect=[11,30,400,400])]:
 state['field']=change;calls.clear();r=a.execute(dict(step,**b),None,'test');assert r['ok'] and calls[-1]==('key','--clearmodifiers','ctrl+a'),(r,change)
state['field']=f
# Cancellation before dispatch still refuses.
calls.clear();ev=threading.Event();ev.set();assert not a.execute(dict(step,**b),None,'test',cancel=ev)['ok'] and not calls
print('PASS Mac-faithful focused shortcut: strict read-only bind helper retained; dispatch posts without binding/identity/modal gates; cancel refuses')
