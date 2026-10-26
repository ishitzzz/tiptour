"""Owned GTK app: when $MUTATE_FLAG appears, a large non-focusable window covering most of the screen shows different content (screen change P1 -> P2)."""
import os, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk
w = Gtk.Window(title="P2Cover"); w.set_accept_focus(False); w.set_focus_on_map(False); w.set_keep_above(True)
lb = Gtk.Label(label="P2 SCREEN - completely different content"); lb.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0.9, 0.1, 0.1, 1)); w.add(lb)
w.move(0, 0); w.set_default_size(1200, 700); w.connect("destroy", Gtk.main_quit)
def tick():
    if os.path.exists(os.environ["MUTATE_FLAG"]): w.show_all(); open(os.environ["MUTATE_FLAG"] + ".shown", "w").write("1")
    return not os.path.exists(os.environ["MUTATE_FLAG"] + ".shown")
GLib.timeout_add(100, tick); Gtk.main()
