"""Unit-only explicit boundary doubles. Mac-faithful behavior (Ishit 1:24 / main 1:28): scroll/pressKey post keys with NO identity re-read, drift refusal, or modal gate - Mac WorkflowRunner L1116-1168 posts the key after activation, operation-token gate only. The retained guard is cancellation between dispatches (STOP always wins). The old field-drift and modal-refusal assertions encoded Linux-only guards and were removed with them."""
import os,sys,threading,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tiptour_linux import actions as a,atspi_resolver as ar
calls=[]
a.activate_target=lambda hint, **kwargs:(True,'simulated target')
a._window_state=lambda:('11',123)
ev=threading.Event()
def x(*v):
 a._chk('test dispatch');calls.append(v)
 if v[0]=='key':ev.set()
a._x=x
# Cancel between scroll presses stops the run after the first dispatched key.
r=a.execute({'type':'scroll','direction':'down','amount':20},None,'test',None,ev);assert not r['ok'] and len(calls)==1,(r,calls)
# Pre-set cancel refuses scroll before any dispatch.
calls.clear();ev=threading.Event();ev.set();r=a.execute({'type':'scroll','direction':'down'},None,'test',None,ev);assert not r['ok'] and not calls
# pressKey dispatches after activation even when modal state is UNAVAILABLE (no modal gate on key posting; Mac has none).
calls.clear();ar.modal_title=lambda hint, **kwargs:('unavailable',None);ev=threading.Event()
r=a.execute({'type':'pressKey','label':'Escape'},None,'test',None,ev);assert r['ok'] and calls[-1]==('key','--clearmodifiers','Escape'),(r,calls)
# Pre-set cancel still refuses pressKey before dispatch.
calls.clear();ev=threading.Event();ev.set();r=a.execute({'type':'pressKey','label':'Escape'},None,'test',None,ev);assert not r['ok'] and not calls
# Checked launch cancellation, no external service.
d=Path(tempfile.mkdtemp());p=d/'xdg-open';p.write_text('#!/bin/sh\nsleep 20\n');p.chmod(0o755);os.environ['PATH']=str(d)+':/usr/bin:/bin';ev=threading.Event();out={}
t=threading.Thread(target=lambda:out.update(a.execute({'type':'openURL','label':'https://example.invalid'},None,None,None,ev)));t.start();time.sleep(.2);ev.set();t.join(3);assert not t.is_alive() and not out['ok']
print('PASS cancellation (Mac-faithful: key posting has no drift/modal guards; cancel between dispatches retained)')
