"""Label-free randomized layout: icon-only buttons at seeded random positions; writes rects to /tmp/target-rects.json."""
import json, random, sys, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1; random.seed(seed)
ICONS = {"Save": "document-save", "Delete": "edit-delete", "Print": "document-print", "Search": "edit-find", "Home": "go-home", "Mail": "mail-send"}
w = Gtk.Window(title="icons"); w.set_default_size(1100, 700); w.move(random.randint(0, 300), random.randint(0, 150))
fx = Gtk.Fixed(); w.add(fx); btns = {}; taken = []
for name, ic in ICONS.items():
    while True:
        x, y = random.randint(20, 1000), random.randint(20, 600)
        if all(abs(x - a) > 130 or abs(y - b) > 110 for a, b in taken): taken.append((x, y)); break
    b = Gtk.Button(); b.set_image(Gtk.Image.new_from_icon_name(ic, Gtk.IconSize.DIALOG)); b.set_size_request(90, 80); fx.put(b, x, y); btns[name] = b
def dump():
    r = {}; _, ox, oy = w.get_window().get_origin()
    for n, b in btns.items():
        tx, ty = b.translate_coordinates(w, 0, 0); a = b.get_allocation(); r[n] = [ox + tx, oy + ty, a.width, a.height]
    json.dump(r, open("/tmp/target-rects.json", "w")); return False
w.connect("destroy", Gtk.main_quit); w.show_all(); GLib.timeout_add(800, dump); Gtk.main()
