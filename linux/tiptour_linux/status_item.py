"""X11 tray adapter for the pinned menu-bar entry, not full CompanionPanel.

Only owned local command/Stop/Quit controls. No settings, provider or action
execution route; a tray host may be missing, so Ctrl+K remains available.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class StatusItem:
    def __init__(self, command, stop, quit):
        self.icon = Gtk.StatusIcon.new_from_icon_name('input-mouse')
        self.icon.set_tooltip_text('TipTour Linux - Ctrl+K opens text commands')
        self.menu = Gtk.Menu()
        for title, callback in [('Open text command', command), ('Stop', stop), ('Quit TipTour', quit)]:
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
