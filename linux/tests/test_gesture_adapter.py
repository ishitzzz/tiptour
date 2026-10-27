from Xlib import X
from tiptour_linux.gesture_adapter import Adapter
C,S,A,W=X.ControlMask,X.ShiftMask,X.Mod1Mask,X.Mod4Mask
pending=[];calls=[]
def record(name):return lambda *args:calls.append((name,args))
a=Adapter(pending.append,record('radial'),record('begin'),record('move'),record('commit'),record('cancel'),record('error'))
a.monitor.sample(C|A|W,(100,100));a.monitor.sample(C|A|W,(20,150));a.monitor.sample(C|S,(20,150));a.monitor.sample(C|S,(24,150));a.monitor.sample(C|S|A,(24,150))
for fn in pending:assert fn()
assert [x[0] for x in calls]==['radial','radial','radial','begin','move','commit'],calls
assert calls[2][1][0]=='end' and calls[3][1][1]==(0,2)
assert calls[-1][1]==(((20,150),(24,150)),True,(0,2)),calls[-1]
# Stop while native/GTK events are queued must not begin/commit them later.
pending.clear();calls.clear();a.monitor.sample(0,(0,0));a.monitor.sample(C|S,(0,0));a.stop();a.monitor.sample(C|S,(20,20))
for fn in pending:fn()
assert [x[0] for x in calls]==['radial','cancel'],calls
pending.clear();calls.clear();a.monitor.sample(0,(0,0));a.monitor.sample(C|S,(0,0));a.monitor.sample(C|S,(2,0));a.monitor.sample(C|S,(3,0));a.monitor.sample(0,(3,0))
for fn in pending:assert fn()
assert calls[-1][0]=='commit' and calls[-1][1][0]==((0,0),(3,0))
pending.clear();a.monitor.sample(C|S,(0,0));a.close()
for fn in pending:assert fn() is False
print('PASS ordered radial end/new highlight; immutable copied-point 3px sampling; Ask commit; Stop queued discard; closed gate')

# Failure retires both mode owners even if neither has a current painted point list.
pending=[];calls=[];a=Adapter(pending.append,record('radial'),record('begin'),record('move'),record('commit'),record('cancel'),record('error'))
a.monitor.sample(C|A|W,(0,0));pending.pop(0)()
with a.monitor.lock:a.monitor._fail()
assert not a.monitor.valid(a.monitor.generation)
pending.pop(0)()
assert calls[-3:]==[('radial',('cancel',None,None)),('cancel',(None,)),('error',())],calls
print('PASS failed sampler retires radial/highlight async-owner callbacks once and refuses valid continuation')

# Applied begin survives sampler's physical end until delivery. Stop/close must
# retire it even when the sampler no longer has an active chord.
for owner,mask in [('highlight',C|S),('radial',C|A|W)]:
 for ending in ('stop','close'):
  pending=[];calls=[];a=Adapter(pending.append,record('radial'),record('begin'),record('move'),record('commit'),record('cancel'),record('error'))
  a.monitor.sample(mask,(0,0));assert pending.pop(0)();assert owner in a.applied
  a.monitor.sample(0,(0,0));stale=pending.pop(0)
  if ending=='stop':
   a.stop();assert stale() is False;assert pending.pop(0)()
  else:
   a.close();assert stale() is False
  assert not a.applied and not a.points
  assert calls[-2:]==[('radial',('cancel',None,None)),('cancel',(None,))],(owner,ending,calls)
  assert not any(x[0]=='commit' for x in calls)
print('PASS applied begin/queued physical end then Stop/close retire both owners independently of sampleractive; async key is generation+gesture')

# Independent cleanup attempts even when either owner or status callback raises.
for source in ('stop','error','close'):
 for broken in ('radial','highlight','status'):
  pending=[];calls=[]
  def radial(*args):
   calls.append('radial')
   if broken=='radial':raise RuntimeError('controlled radial cleanup')
  def highlight(*args):
   calls.append('highlight')
   if broken=='highlight':raise ValueError('controlled highlight cleanup')
  def status():
   calls.append('status')
   if broken=='status':raise LookupError('controlled status')
  a=Adapter(pending.append,radial,lambda *_:None,lambda *_:None,lambda *_:None,highlight,status)
  if source=='stop':
   a.stop();assert pending.pop(0)()
  elif source=='error':
   with a.monitor.lock:a.monitor._fail()
   assert pending.pop(0)()
  else:
   result=a.close();assert result==(broken=='status')
  assert calls==(['radial','highlight','status'] if source=='error' else ['radial','highlight']), (source,broken,calls)
  assert len(a.cleanup_errors)==(0 if broken=='status' and source!='error' else 1)
  assert not a.points and not a.applied
print('PASS independent cleanup/status attempts with radial/highlight/status faults on Stop/error/close; close false on cleanup fault')
