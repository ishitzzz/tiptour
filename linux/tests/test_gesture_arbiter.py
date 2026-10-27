import itertools
from Xlib import X
from tiptour_linux.gesture_arbiter import Arbiter,mode,MODIFIERS
C,S,A,W=X.ControlMask,X.ShiftMask,X.Mod1Mask,X.Mod4Mask
for mask in range(256):
 expected='radial' if mask&C and mask&A and mask&W and not mask&S else 'highlight' if mask&C and mask&S and not mask&A and not mask&W else None
 assert mode(mask)==expected
for owner,mods in [('radial',(C,A,W)),('highlight',(C,S))]:
 for order in itertools.permutations(mods):
  s=Arbiter();mask=0;events=[]
  for m in order:mask|=m;events+=s.sample(mask,(100,100))
  assert events==[('begin',owner,(100,100),False)],(owner,order,events)
  assert s.sample(mask,(120,120))==[('move',owner,(120,120),False)]
  for release in itertools.permutations(order):
   r=Arbiter();r.sample(mask,(100,100));mm=mask;ev=[]
   for m in release:mm &= ~m;ev+=r.sample(mm,(120,120))
   assert ev==[('end',owner,(120,120),False)],ev
s=Arbiter();s.sample(C|S,(0,0));assert s.sample(C|S|A,(5,5))==[('end','highlight',(5,5),True)]
assert s.sample(C|A|W,(5,5))==[('begin','radial',(5,5),False)]
assert s.sample(C|S,(6,6))==[('end','radial',(6,6),False),('begin','highlight',(6,6),False)]
s.sample(0,(6,6));assert s.sample(C|A|W,(6,6))[0][:2]==('begin','radial')
# Shift breaks radial; the next genuine CtrlShift sample starts highlight as on pinned Mac.
assert s.sample(C|A|W|S,(7,7))==[('end','radial',(7,7),False)]
assert s.sample(C|S,(8,8))==[('begin','highlight',(8,8),False)]
assert s.stop()==[('cancel','highlight',None,False)];assert not s.sample(C|S,(10,10))
s.sample(0,(10,10));assert s.sample(C|S,(11,11));s.stop(close=True);assert not s.sample(0,(0,0)) and not s.sample(C|S,(0,0))
# Mouse buttons and lock state do not widen/narrow modifier ownership.
for extra in (X.Button1Mask,X.Button2Mask,X.LockMask):
 s=Arbiter();assert s.sample(C|S|extra,(0,0))[0][1]=='highlight'
print('PASS all masks; modifier press/release permutations; one owner; pinned cross-chord transitions; Ask provenance; Stop/closed; unrelated mask bits')
