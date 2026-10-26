import gi; gi.require_version("Gtk","3.0"); from gi.repository import Gtk
w=Gtk.Window(title="owned-entry-B"); w.set_default_size(400,120); e=Gtk.Entry(); w.add(e); w.connect("destroy",Gtk.main_quit); w.show_all()
from gi.repository import GLib
import os
def dump(): open(os.environ["ENTRY_DUMP_B"],"w").write(e.get_text()); return True
GLib.timeout_add(300,dump); Gtk.main()
