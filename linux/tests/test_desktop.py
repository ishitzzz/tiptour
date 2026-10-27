import os,tempfile
from tiptour_linux.desktop import readiness,command
c=readiness({'DISPLAY':':1','XDG_SESSION_TYPE':'wayland'})
assert not c[0][1] and not c[1][1]
with tempfile.TemporaryDirectory() as d:
 p=os.path.join(d,'key');open(p,'w').write('test-placeholder')
 c=readiness({'DISPLAY':':1','TIPTOUR_KEYS_GLOB':p})
 assert c[0][1] and c[1][1] and 'validity and quota not checked' in c[1][2]
assert '--act' not in command() and '--voice' not in command()
assert '--act' in command(act=True) and '--voice' in command(voice=True)
assert command()[2:]==['-m','tiptour_linux.app','--text-ui']
print('PASS defaults pointonly/text; explicit voice/action flags; Wayland/no-key refusal; configured-not-validated key state')

# Directory/unreadable/invalid encoding glob members cannot crash runtime loader.
from tiptour_linux.keypool import configured_keys
with tempfile.TemporaryDirectory() as d:
 open(os.path.join(d,'valid'),'w').write('placeholder')
 os.mkdir(os.path.join(d,'directory'))
 open(os.path.join(d,'invalid'),'wb').write(b'\xff')
 assert configured_keys(d+'/*',{})==['placeholder']
 assert readiness({'DISPLAY':':1','TIPTOUR_KEYS_GLOB':d+'/*'})[1][1]
print('PASS consistent readiness/runtime loader skips directory, unreadable and invalid encoding without secret output')

from tiptour_linux.desktop import initial_target_snapshot
import threading,time
release=threading.Event()
def late():release.wait();return (999,2,('changed',))
snapshot=initial_target_snapshot(late,.01);assert snapshot is None
release.set();time.sleep(.03);assert snapshot is None
assert initial_target_snapshot(lambda:(1,2,('initial',)))==(1,2,('initial',))
print('PASS startup deadline result frozen; late setup/other-app identity cannot change launch target')
