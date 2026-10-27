import threading,time,queue,types
from Xlib import X
from tiptour_linux.gesture_arbiter import Monitor
C,S=X.ControlMask,X.ShiftMask
samples=queue.Queue();events=[];threads=[];closed=[]
class D:
 def __init__(self):threads.append(('open',threading.get_ident()))
 def screen(self):return types.SimpleNamespace(root=self)
 def query_pointer(self):
  threads.append(('query',threading.get_ident()))
  try:v=samples.get(timeout=.01)
  except queue.Empty:v=(0,0,0)
  if isinstance(v,Exception):raise v
  if callable(v):return v()
  return types.SimpleNamespace(mask=v[0],root_x=v[1],root_y=v[2])
 def close(self):closed.append(threading.get_ident())
def wait(fn,t=1):
 end=time.monotonic()+t
 while not fn() and time.monotonic()<end:time.sleep(.005)
 assert fn()
m=Monitor(events.append,hz=200,display_factory=D)
samples.put((C|S,10,10));m.start();wait(lambda:len(events)>=1)
token=events[0].generation;assert events[0].events[0].kind=='begin' and events[0].events[0].owner=='highlight' and m.valid(token)
m.stop();assert not m.valid(token);samples.put((C|S,20,20));time.sleep(.03)
assert not any(t.kind=='move' for b in events for t in b.events)
samples.put((0,20,20));time.sleep(.03);samples.put((C|S,30,30));wait(lambda:len([t for b in events for t in b.events if t.kind=='begin'])==2)
assert m.close() and not m.valid(events[-1].generation)
assert len(set(t for _,t in threads))==1 and closed==[threads[0][1]] and closed[0]!=threading.get_ident()
# Query exception emits failure but never silently commits a held highlight.
events=[];samples.put((C|S,40,40));samples.put(RuntimeError('controlled'))
n=Monitor(events.append,hz=200,display_factory=D);n.start();wait(lambda:any(t.kind=='error' for b in events for t in b.events));assert not any(t.kind=='end' for b in events for t in b.events);assert n.close()
# Native call genuinely blocked beyond close budget returns false, then can unwind.
entered=threading.Event();release=threading.Event()
def blocked():entered.set();release.wait(3);return types.SimpleNamespace(mask=C|S,root_x=1,root_y=1)
samples.put(blocked);h=Monitor(events.append,hz=200,display_factory=D);h.start();assert entered.wait(1)
t=time.monotonic();assert h.close() is False and time.monotonic()-t<.8
release.set();h.thread.join(1);assert not h.thread.is_alive()
print('PASS single worker Display open/query/close; epochs; Stop barrier; query error no commit; native hang honest bounded false receipt')

# Queued genuine radial end and highlight begin survive later gesture identity.
A,W=X.Mod1Mask,X.Mod4Mask
batches=[];m=Monitor(batches.append);m.sample(C|A|W,(100,100));m.sample(C|A|W,(20,150));m.sample(C|S,(20,150));m.sample(0,(20,150))
seen=[]
assert len(batches[2].events)==2
assert [(t.kind,t.owner,t.gesture) for t in batches[2].events]==[('end','radial',1),('begin','highlight',2)]
assert m.valid(batches[0].generation)  # newer genuine gesture did not revoke end
assert not m.deliver(batches[1],seen.append)  # out of order refuses, can retry FIFO
for b in batches: assert m.deliver(b,seen.append)
assert [t.kind for t in seen]==['begin','move','end','begin','end']
assert not m.deliver(batches[-1],seen.append)  # no duplicate effects
# Stop kills old queued generation but delivers its own cancellation before new input.
batches=[];m=Monitor(batches.append);m.sample(C|S,(0,0));old=batches[0];m.stop();m.sample(C|S,(5,5));m.sample(0,(5,5));m.sample(C|S,(10,10))
seen=[];assert not m.deliver(old,seen.append)
for b in batches[1:]:assert m.deliver(b,seen.append)
assert [t.kind for t in seen]==['cancel','begin']
assert seen[0].owner is None and seen[1].gesture==2
print('PASS immutable ordered batches; genuine end+begin preserved; generation only Stop/error/close; no duplicate/out-of-order effects')

# End handler may synchronously Stop: its batch's later begin is then stale.
batches=[];m=Monitor(batches.append);m.sample(C|A|W,(0,0));m.sample(C|S,(1,1));seen=[]
assert m.deliver(batches[0],seen.append)
def stop_on_end(event):
 seen.append(event)
 if event.kind=='end':m.stop()
assert m.deliver(batches[1],stop_on_end) is False
assert [t.kind for t in seen]==['begin','end']
print('PASS cancellation rechecked between transitions in one genuine cross-chord batch')

# Reentrant close also refuses the batch remainder.
batches=[];m=Monitor(batches.append);m.sample(C|A|W,(0,0));m.sample(C|S,(1,1));seen=[]
assert m.deliver(batches[0],seen.append)
def close_on_end(event):
 seen.append(event)
 if event.kind=='end':m.close()
assert not m.deliver(batches[1],close_on_end)
assert [t.kind for t in seen]==['begin','end']
# An exception after an end side effect retires the generation, then one error notice.
batches=[];m=Monitor(batches.append);m.sample(C|A|W,(0,0));m.sample(C|S,(1,1));seen=[]
assert m.deliver(batches[0],seen.append)
def fail_end(event):
 seen.append(event);raise RuntimeError('controlled callback failure')
assert not m.deliver(batches[1],fail_end) and m.failed and not m.valid(m.generation)
assert [t.kind for t in seen]==['begin','end']
notice=batches[-1];assert notice.events[0].kind=='error' and m.deliver(notice,seen.append)
assert not m.deliver(notice,seen.append)
m.sample(C|S,(5,5));assert batches[-1] is notice
print('PASS reentrant close; partial callback failure terminal generation; one guarded error notice/dead input refusal')
