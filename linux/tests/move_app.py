"""Host window with a Save button. When $MOVE_FLAG appears the button MOVES (+320,+160). After every layout change the button's absolute screen rect is written to $ORACLE_FILE (independent oracle for 'points at the right control')."""
import os, json, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
w = Gtk.Window(title="Move Host"); w.set_default_size(900, 600); w.move(200, 150)
fx = Gtk.Fixed(); w.add(fx); b = Gtk.Button(label="Save"); b.set_size_request(140, 48); fx.put(b, 60, 120)
st = {"moved": False}
def rect():
    ox, oy = b.get_window().get_origin()[1:]; a = b.get_allocation()
    open(os.environ["ORACLE_FILE"], "w").write(json.dumps({"moved": st["moved"], "rect": [ox + (a.x if b.get_has_window() else 0) if False else b.translate_coordinates(w, 0, 0)[0] + w.get_window().get_origin()[1], b.translate_coordinates(w, 0, 0)[1] + w.get_window().get_origin()[2], a.width, a.height]}))
def tick():
    if not st["moved"] and os.path.exists(os.environ["MOVE_FLAG"]):
        st["moved"] = True; fx.move(b, 380, 280)
    rect(); return True
w.connect("destroy", Gtk.main_quit); w.show_all(); GLib.timeout_add(300, tick); Gtk.main()
