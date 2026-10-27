from tiptour_linux.radial import State,chord
from Xlib import X
s=State();s.begin((100,100));assert s.hover is None
assert s.end((100,100)) is None
for point,selected in [((100,0),'speak'),((180,150),'type'),((20,150),'highlight')]:
 s.begin((100,100));s.move(point);assert s.hover==selected
 assert s.end(point)==selected and s.center is None and s.hover is None
s.begin((100,100));s.move((180,150));assert s.end((100,100))=='type'
s.begin((100,100));s.move((180,150));s.move((100,100));assert s.end((100,100)) is None
s.begin((1,2));s.cancel();assert s.end((1,2)) is None
for mask in range(256):
 expected=bool(mask & X.ControlMask and mask & X.Mod1Mask and mask & X.Mod4Mask and not mask & X.ShiftMask)
 assert chord(mask)==expected
print('PASS radial begin/move/end/deadzone/last-hover fallback/cancel; all modifier masks')
