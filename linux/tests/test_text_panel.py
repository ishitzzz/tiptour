"""Run under an X11 display. Inject slow activation, not a real X server hang."""
import time, threading
from gi.repository import Gtk, GLib
from tiptour_linux.text_panel import TextPanel
posts=[];p=TextPanel(posts.append);p.target=(1,2,('fixture',));p.entry.set_text('a new request')
entered=threading.Event();finished=threading.Event()
def slow(_,valid):
 entered.set();time.sleep(.8);finished.set();return True
p.restore=slow;p.submit()
assert entered.wait(.5)
start=time.monotonic();p.stop_work();assert time.monotonic()-start<.1
end=time.monotonic()+1
while time.monotonic()<end:
 while Gtk.events_pending():Gtk.main_iteration_do(False)
 time.sleep(.005)
assert finished.is_set() and posts==['stop'],posts
p.destroy()
p.monitor_thread.join(1)
assert not p.monitor_thread.is_alive()
assert p.closed.is_set()
print('PASS injected800ms activation does not block STOP; cancelled handoff posts no late request; monitor closes after destroy')
# Actual state transitions using injected identity reader, not only parser results.
import tiptour_linux.text_panel as mod
p=TextPanel(posts.append);p.target=(77,88,('old',))
mod.window_id=lambda:999;mod.target_identity=lambda _:None
p.show_command()
def pump(seconds=.15):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  while Gtk.events_pending():Gtk.main_iteration_do(False)
  time.sleep(.002)
pump();assert p.target is None,'invalid unrelated focus retained old target'
p.target=(77,88,('old',));mod.window_id=lambda:p.get_window().get_xid()
p.show_command();pump();assert p.target==(77,88,('old',)),'own entry should retain explicitly captured target'
# Single worker backpressure and cancellation before OS activation.
entered=threading.Event();release=threading.Event();activations=[]
def block_identity(_):entered.set();release.wait(1);return (77,88,('old',))
mod.target_identity=block_identity
real_popen=mod.subprocess.Popen
mod.subprocess.Popen=lambda *a,**kw:activations.append(a)  # must never be reached
p.entry.set_text('propose something');p.submit();assert entered.wait(.5)
for _ in range(20):p.show_command()
assert p.worker_busy and p.target is None
p.stop_work();release.set();pump(.3)
assert not activations and not p.worker_busy,activations
assert p.target is None
before=list(posts);p.entry.set_text("must not target old app");p.submit();pump(.1)
assert posts==before and not activations,(posts,activations)
mod.subprocess.Popen=real_popen
p.destroy();p.monitor_thread.join(1);assert not p.monitor_thread.is_alive()
print('PASS invalid unrelated transition clears target; own entry retains;20 replacements backpressured; cancelled identity cannot dispatch activation')
