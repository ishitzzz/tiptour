import sys, time, threading
sys.path.insert(0, "/home/sandbox/tiptour/linux")
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from tiptour_linux import atspi_resolver as a
T0 = time.time()
import os
from PIL import ImageGrab
if os.environ.get('LOAD') == '1':
    def stream():
        while True:
            GLib.idle_add(lambda: (win.hide(), False)[1]); time.sleep(0.25); ImageGrab.grab(); GLib.idle_add(lambda: (win.show_all(), False)[1]); time.sleep(0.75)
    threading.Thread(target=stream, daemon=True).start()
win = Gtk.Window(); win.set_default_size(50, 50); win.show_all()
def warm():
    t_end = time.time() + 60
    while time.time() < t_end:
        try: a.probe((0,0,1,1), timeout=3.5, low=True)
        except Exception: pass
        if a.ready_bounded(2): print('warm: ready at %.1fs' % (time.time() - T0), flush=True); break
        time.sleep(1)
def run():
    time.sleep(10)
    for k in range(3):
        t = time.time()
        try: r = a.probe((150, 380, 290, 50), timeout=8); print("probe%d %.2fs element=%s ready=%s" % (k, time.time() - t, (r[0] or {}).get("label"), a.ready_bounded(3)), flush=True)
        except Exception as e: print("probe%d %.2fs FAILED %s" % (k, time.time() - t, type(e).__name__), flush=True)
    t = time.time(); x = a.resolve("Save changes"); print("resolve %.2fs hits=%d" % (time.time() - t, len(x)), flush=True)
    GLib.idle_add(Gtk.main_quit)
threading.Thread(target=warm, daemon=True).start(); threading.Thread(target=run, daemon=True).start()
GLib.timeout_add(70000, Gtk.main_quit)
Gtk.main()
