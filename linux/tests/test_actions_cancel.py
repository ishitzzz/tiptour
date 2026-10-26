"""Unit-only explicit boundary doubles. Native/PID/modal are simulated here; real native coverage lives in runtime evidence."""
import os,sys,threading,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tiptour_linux import actions as a,atspi_resolver as ar
calls=[];focus={'n':1}
a.activate_target=lambda hint:(True,'simulated target')
a._window_state=lambda:('11',123)
a.focus_info=lambda hint,editable=True:{'ok':True,'identity':{'pid':123,'element_path':str(focus['n'])},'editable':True}
ar.modal_title=lambda hint:('ok',None)
ev=threading.Event()
def x(*v):
 a._chk('test dispatch');calls.append(v)
 if v[0]=='key':ev.set()
a._x=x
r=a.execute({'type':'scroll','direction':'down','amount':20},None,'test',None,ev);assert not r['ok'] and len(calls)==1,(r,calls)
calls.clear();ev=threading.Event();ev.set();r=a.execute({'type':'scroll','direction':'down'},None,'test',None,ev);assert not r['ok'] and not calls
# Different field after first dispatch must refuse continuation independently of STOP.
def drift(*v):
 a._chk('test dispatch');calls.append(v);focus['n']=2
a._x=drift;r=a.execute({'type':'scroll','direction':'down','amount':3},None,'test');assert not r['ok'] and len(calls)==1,(r,calls)
# Unavailable modal is refused before dispatch.
calls.clear();ar.modal_title=lambda hint:('unavailable',None);r=a.execute({'type':'pressKey','label':'Escape'},None,'test');assert not r['ok'] and not calls
# Checked launch cancellation, no external service.
d=Path(tempfile.mkdtemp());p=d/'xdg-open';p.write_text('#!/bin/sh\nsleep 20\n');p.chmod(0o755);os.environ['PATH']=str(d)+':/usr/bin:/bin';ev=threading.Event();out={}
t=threading.Thread(target=lambda:out.update(a.execute({'type':'openURL','label':'https://example.invalid'},None,None,None,ev)));t.start();time.sleep(.2);ev.set();t.join(3);assert not t.is_alive() and not out['ok']
print('PASS cancellation/field drift/modal refusal/launcher cancellation (explicit simulated boundaries)')
