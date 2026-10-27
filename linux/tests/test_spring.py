import math
from tiptour_linux.spring import step
for x,v,t in [(0,0,1),(50,-20,100),(100,400,-200)]:
 for total in [.016,.032,.1,.5,3]:
  a=step(x,v,t,total);xx,vv=x,v
  for _ in range(100):xx,vv=step(xx,vv,t,total/100)
  assert math.isclose(a[0],xx,rel_tol=1e-10,abs_tol=1e-9) and math.isclose(a[1],vv,rel_tol=1e-10,abs_tol=1e-9)
a=step(0,0,1,.016);assert .102<a[0]<.103
assert step(3,4,5,0)==(3,4)
assert abs(step(0,0,1,10)[0]-1)<1e-12
assert all(math.isfinite(v) for v in step(0,1,1000,10000))
print('PASS exact damped spring analytical step, frame subdivision, first frame, zero time, long elapsed stable; not SwiftUI runtime equivalence')
