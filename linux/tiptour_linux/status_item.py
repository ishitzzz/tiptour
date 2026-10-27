"""X11 tray adapter for the pinned menu-bar entry, not full CompanionPanel.

Only owned local command/Stop/Quit and supported Linux settings controls.
No new provider or action execution route; a tray host may be missing, so Ctrl+K remains available.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import cairo, threading

def pointer_icon(size=18):
    """Pinned MenuBarPanelManager cubic path, not the overlay quadratic approximation."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size); c = cairo.Context(surface)
    scale = size * .78 / 24; origin = size/2 - 12*scale
    c.translate(origin,origin);c.scale(scale,scale)
    c.move_to(4.037,4.688);c.curve_to(3.90,3.90,3.90,3.90,4.688,4.037)
    c.line_to(20.688,10.537);c.curve_to(21.42,10.84,21.42,10.84,20.625,11.484)
    c.line_to(14.501,13.064);c.curve_to(13.43,13.34,13.43,13.34,13.063,14.499)
    c.line_to(11.484,20.625);c.curve_to(11.17,21.42,11.17,21.42,10.537,20.688)
    c.close_path();c.set_source_rgb(0,0,0);c.fill()
    return Gdk.pixbuf_get_from_surface(surface,0,0,size,size)


class StatusItem:
    def __init__(self, command, stop, quit, settings=None):
        self.icon = Gtk.StatusIcon.new_from_pixbuf(pointer_icon())
        self.icon.set_tooltip_text('TipTour Linux - Ctrl+K opens text commands')
        self.capture_busy = threading.Event()
        self.menu = Gtk.Menu()
        self.menu.connect("map", lambda *_: self.capture_busy.set())
        self.menu.connect("unmap", lambda *_: self.capture_busy.clear())
        controls = [('Open text command', command), ('Stop', stop)]
        if settings: controls.append(('Settings', settings))
        controls.append(('Quit TipTour', quit))
        for title, callback in controls:
            item = Gtk.MenuItem(label=title); item.connect('activate', lambda _, fn=callback: fn()); self.menu.append(item)
        self.menu.show_all()
        self.icon.connect('activate', lambda *_: self.popup(0, Gtk.get_current_event_time()))
        self.icon.connect('popup-menu', lambda _, button, timestamp: self.popup(button, timestamp))
        self.icon.set_visible(True)

    def popup(self, button, timestamp):
        self.menu.popup(None, None, Gtk.StatusIcon.position_menu, self.icon, button, timestamp)

    def capture_window(self):
        top = self.menu.get_toplevel()
        return top if isinstance(top, Gtk.Window) and top.get_window() else None

    def dismiss_for_capture(self):
        # Never reopen a menu that the user dismissed while capture ran.
        self.menu.popdown()

    def close(self):
        self.menu.popdown(); self.menu.destroy(); self.icon.set_visible(False)
