from tiptour_linux.input_geometry import panel_origin,smoothed_origin,radial_option
import math
assert panel_origin((500,400),(340,64),(0,0,1280,800))==(556,432)
assert panel_origin((1200,700),(340,64),(0,0,1280,800))==(804,724)
assert panel_origin((-500,200),(340,64),(-1280,0,1280,800))==(-444,232)
assert panel_origin((0,0),(340,64),(0,0,1280,800))==(56,32)
assert smoothed_origin((0,0),(100,100))==(24,24)
assert smoothed_origin((1,1),(1.4,1.4))==(1.4,1.4)
assert smoothed_origin(None,(1,2))==(1,2)
assert radial_option((0,-24),(0,0))=='speak'
assert radial_option((24,0),(0,0))=='type'
assert radial_option((-24,0),(0,0))=='highlight'
assert radial_option((0,24),(0,0))=='type'  # inclusive -90
assert radial_option((0,23.99),(0,0)) is None
for p in [(math.nan,0),(True,1),(math.inf,0)]:
 try: radial_option(p,(0,0))
 except ValueError: pass
 else: raise AssertionError(p)
try:panel_origin((0,0),(1000,1000),(0,0,200,200))
except ValueError:pass
else:raise AssertionError('oversized panel')
print('PASS converted Mac candidate order, edge clamp/negative screen, smoothing, radial cardinal/deadzone, strict numbers/oversize refusal')
