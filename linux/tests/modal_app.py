"""Host window with a Save button; after the delay in $MODAL_AFTER_S (default 99999 = never) a MODAL dialog titled 'Unsaved changes' opens (blocks the host)."""
import os, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
w = Gtk.Window(title="Modal Host"); w.set_default_size(700, 400); w.move(200, 150)
fx = Gtk.Fixed(); w.add(fx); b = Gtk.Button(label="Save"); b.set_size_request(140, 48); fx.put(b, 60, 120)
def dlg():
    d = Gtk.MessageDialog(transient_for=w, modal=True, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK, text="Unsaved changes"); d.set_title("Unsaved changes"); d.show()
    if os.environ.get("MODAL_CLOSE_S"): GLib.timeout_add(int(float(os.environ["MODAL_CLOSE_S"]) * 1000), lambda: (d.destroy(), False)[1])
    return False
w.connect("destroy", Gtk.main_quit); w.show_all(); GLib.timeout_add(int(float(os.environ.get("MODAL_AFTER_S", "99999")) * 1000), dlg); Gtk.main()
