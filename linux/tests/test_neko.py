"""Original Neko state/asset contract; no input/provider or window."""
from tiptour_linux.neko import Neko,direction
from pathlib import Path
import math,cairo
assert [direction(math.cos(i*math.pi/4)*2,math.sin(i*math.pi/4)*2) for i in range(8)]==['right','downright','down','downleft','left','upleft','up','upright']
assert direction(1,0) is None and direction(.5,0,.5)=='right'
n=Neko();n.tick((10,0),0);assert n.sprite=='right2'
n.tick((10,0),.2);assert n.sprite=='awake'
for i in range(2,8):n.tick((10,0),i*.201)
assert n.sprite.startswith('scratch'),n.sprite
for i in range(8,24):n.tick((10,0),i*.201)
assert n.sprite.startswith('sleep'),n.sprite
n.tick((10,5),5);assert n.sprite.startswith('down')
for name in [d+str(i) for d in ('right','downright','down','downleft','left','upleft','up','upright') for i in (1,2)]+['awake','sleep1','sleep2','scratch1','scratch2']:
 assert n.surface(name),name
assert n.surface('missing-explicit-fixture') is None
s=cairo.ImageSurface(cairo.FORMAT_ARGB32,64,64);n.paint(cairo.Context(s),32,32,name='missing-explicit-fixture')
from tiptour_linux import settings
assert settings.DEFAULTS['isNekoModeEnabled'] is False
print('PASS original direction/idle/run thresholds/assets/fallback paint/default false. Cairo JPEG/pixel/native app tests separate.')
