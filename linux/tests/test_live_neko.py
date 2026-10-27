"""Run under X11. Visual toggle does not replace action-flight state."""
import os,tempfile
os.environ['TIPTOUR_NEKO']='0';os.environ['TIPTOUR_CONFIG_DIR']=tempfile.mkdtemp(prefix='tiptour-live-neko-')
import gi;gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from tiptour_linux import settings
from tiptour_linux.overlay import PointerOverlay
calls=[]
w=settings.gtk_window(standalone=False,on_neko_changed=calls.append)
c=next(x for x in w.get_children()[0].get_children() if isinstance(x,Gtk.CheckButton))
c.set_active(True);assert calls==[True] and settings.load()['isNekoModeEnabled']
# Explicit environment remains authoritative even when saved state differs.
settings.apply_env();assert os.environ['TIPTOUR_NEKO']=='0'
o=PointerOverlay();o.show_all();assert o.neko is None and o.paws is None
done=lambda:None
o.point_to(900,650,'Owned fixture',done)
f=o.flight;target=o.target;mode=o.mode
o.set_neko_enabled(True);assert o.neko and o.paws
assert o.flight is f and o.target==target and o.mode==mode
p=o.paws.window
o.set_neko_enabled(False)
assert o.flight is f and o.target==target and o.mode==mode
assert o.neko is None and o.paws is None and p._tiptour_destroyed and not p.get_visible()
o.set_neko_enabled(True);assert o.paws.window is not p
p=o.paws.window;o.set_neko_enabled(True);assert o.paws.window is p
o.destroy();w.destroy()
print('PASS saved callback, explicit env, live art replacement preserves exact flight and target, retired paw hidden, repeated mode idempotent')
