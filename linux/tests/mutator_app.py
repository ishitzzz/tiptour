"""Unrelated owned GTK app: when $MUTATE_FLAG appears, add a button and rename another (a visible AT-SPI change in a DIFFERENT app)."""
import os, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
w = Gtk.Window(title="UnrelatedMutator"); box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6); w.add(box)
b = Gtk.Button(label="Unrelated button"); box.add(b)
w.move(1000, 600); w.set_default_size(260, 120); w.connect("destroy", Gtk.main_quit); w.show_all()
done = [False]
def tick():
    if not done[0] and os.path.exists(os.environ["MUTATE_FLAG"]):
        done[0] = True; b.set_label("Unrelated button (changed)"); n = Gtk.Button(label="Brand new unrelated button"); box.add(n); n.show()
    return True
GLib.timeout_add(100, tick); Gtk.main()
