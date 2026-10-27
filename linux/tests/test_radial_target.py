import threading,time
from tiptour_linux import radial_target as r
calls=[];target=(1,2,('fixture',));orig=r.snapshot
r.snapshot=lambda _:target
w=r.request((1,2),lambda t,d:calls.append((t,d)),lambda:True,.1);w.join(1);assert calls[0][0]==target
calls=[];n=[0]
def slow(_):
 n[0]+=1
 if n[0]==2:time.sleep(.2)
 return target
r.snapshot=slow;w=r.request((1,2),lambda t,d:calls.append((t,d)),lambda:True,.04);w.join(1);assert len(calls)==1 and calls[0][0] is None
calls=[];ok=[True]
def invalidate(_):ok[0]=False;return target
r.snapshot=invalidate;w=r.request((1,2),lambda t,d:calls.append((t,d)),lambda:ok[0],.04);w.join(1);assert not calls
r.snapshot=orig
print('PASS two-snapshot identity, slowrecheck deadline/refusal exactlyonce, invalidatedowner no delivery; injectednative reads, notXhang')
