"""Known-geometry target window; writes each button's screen rect to /tmp/target-rects.json."""
import json, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
w = Gtk.Window(title="Export Settings Demo"); w.set_default_size(900, 600); w.move(200, 150)
fx = Gtk.Fixed(); w.add(fx)
lab = Gtk.Label(label="Project export settings"); fx.put(lab, 40, 30)
btns = {}
for name, (x, y) in {"Save": (60, 120), "Cancel": (260, 120), "Export PDF": (60, 300), "Preferences": (560, 480), "Help": (700, 60)}.items():
    b = Gtk.Button(label=name); b.set_size_request(140, 48); fx.put(b, x, y); btns[name] = b; b.connect('clicked', lambda _b, n=name: open('/tmp/clicked.log','a').write(n + '\n'))
def dump():
    r = {}
    for n, b in btns.items():
        _, ox, oy = w.get_window().get_origin(); tx, ty = b.translate_coordinates(w, 0, 0); a = b.get_allocation()
        r[n] = [ox + tx, oy + ty, a.width, a.height]
    json.dump(r, open("/tmp/target-rects.json", "w")); return False
w.connect("destroy", Gtk.main_quit); w.show_all(); GLib.timeout_add(800, dump); Gtk.main()
