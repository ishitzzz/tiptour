"""GTK text input over the existing local proposal path, not a JEV client.

Source: TextCommandPanelView/Manager and GlobalTextCommandShortcutMonitor
at 6e97782. Linux window/focus mechanics substitute for NSPanel.
"""
import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib


def window_id():
    try:
        p = subprocess.run(['xdotool', 'getwindowfocus'], capture_output=True, text=True, timeout=2)
        return int(p.stdout.strip()) if p.returncode == 0 else None
    except (ValueError, OSError, subprocess.TimeoutExpired): return None


def target_identity(wid):
    """Bind an X11 id to process and WM_CLASS, reject our own UI and no identity."""
    if not wid: return None
    d = None
    try:
        from Xlib import display
        d = display.Display(); w = d.create_resource_object('window', wid)
        classes = tuple(w.get_wm_class() or ())
        pid = w.get_full_property(d.intern_atom('_NET_WM_PID'), 0)
        pid = int(pid.value[0]) if pid is not None and len(pid.value) else None
        if not classes or not pid or any('tiptour' in str(c).lower() for c in classes): return None
        if w.get_attributes().map_state != 2: return None
        return (int(wid), pid, classes)
    except Exception: return None
    finally:
        if d: d.close()


class TextPanel(Gtk.Window):
    def __init__(self, post):
        super().__init__(title='TipTour text command')
        self.set_wmclass('tiptour-text', 'TipTourText')
        self.set_name('tiptour-text')
        from pathlib import Path
        css = Gtk.CssProvider(); css.load_from_path(str(Path(__file__).with_name('text_panel.css')))
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.set_default_size(420, 110); self.set_keep_above(True)
        self.post = post; self.target = None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=10)
        self.add(box)
        self.entry = Gtk.Entry(); self.entry.set_placeholder_text('Ask TipTour to point or propose a plan')
        self.entry.connect('activate', self.submit); box.pack_start(self.entry, False, False, 0)
        row = Gtk.Box(spacing=8); box.pack_start(row, False, False, 0)
        for label, callback in [('Submit', self.submit), ('Stop', self.stop_work), ('Hide', lambda *_: self.dismiss())]:
            b = Gtk.Button(label=label); b.connect('clicked', callback); row.pack_start(b, False, False, 0)
        self.activity = Gtk.Label(label='Review each proposed plan before Confirm. Ctrl+K opens this panel.')
        self.activity.set_line_wrap(True); self.activity.set_xalign(0); box.pack_start(self.activity, False, False, 0)
        self.connect('delete-event', lambda *_: (self.dismiss(), True)[1])
        self.connect('key-press-event', self.key)
        self.chord = False; self.closed = threading.Event(); self.epoch = 0; self.busy = False; self.worker_lock = threading.Lock(); self.worker_busy = False
        self.connect("destroy", lambda *_: self.close())
        self.tracking_frozen = False; self.tracking_origin = None
        self.follow_timer = GLib.timeout_add(16, self.follow_tick)
        self.monitor_thread = threading.Thread(target=self.monitor, daemon=True, name="text-shortcut")
        self.monitor_thread.start()

    def async_call(self, work, done):
        with self.worker_lock:
            if self.worker_busy:
                self.activity.set_text('Focus check still running. Stop is available.'); return False
            self.worker_busy = True; self.epoch += 1; epoch = self.epoch
        def valid(): return not self.closed.is_set() and epoch == self.epoch
        def run():
            try: result = work(valid)
            except Exception: result = None
            finally:
                with self.worker_lock: self.worker_busy = False
            def apply():
                if valid(): done(result)
                return False
            GLib.idle_add(apply)
        threading.Thread(target=run, daemon=True, name='text-focus').start()
        return True

    def show_command(self):
        self.epoch += 1; self.busy = False
        own_id = self.get_window().get_xid() if self.get_window() else None
        def read(valid):
            wid = window_id()
            return (wid == own_id, target_identity(wid))
        def done(result):
            if not result: self.target = None
            else:
                own, current = result
                if not own: self.target = current  # invalid unrelated focus MUST clear old target
            self.set_keep_above(True)
            self.activity.set_text('Review each proposal before Confirm. Target: %s' % (self.target[0] if self.target else 'unavailable'))
            self.tracking_origin = None
            self.show_all(); self.follow_tick(); self.present(); self.entry.grab_focus()
        if not self.async_call(read, done): self.target = None
        return False

    def open_from_menu(self):
        # A tray menu can own focus. Never interpret that as the old app's consent.
        self.epoch += 1; self.target = None; self.busy = False
        self.activity.set_text('Focus the target app, then press Ctrl+K before submitting.')
        self.show_all(); self.present(); self.entry.grab_focus()

    def restore(self, target, valid):
        # Cancellation before dispatch prevents activation. An activation already
        # delivered to the WM cannot be recalled. Cancel kills a waiting client.
        if not target or target_identity(target[0]) != target or not valid(): return False
        p = subprocess.Popen(['xdotool', 'windowactivate', '--sync', str(target[0])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            import time
            end = time.monotonic() + 2
            while p.poll() is None:
                if not valid() or time.monotonic() >= end: p.terminate(); return False
                time.sleep(.01)
            return valid() and p.returncode == 0 and window_id() == target[0] and target_identity(target[0]) == target
        finally:
            if p.poll() is None: p.kill()
            p.wait()

    def dismiss(self):
        self.epoch += 1
        self.entry.set_text(''); self.hide()
        self.busy = False; target = self.target
        self.async_call(lambda valid: self.restore(target, valid), lambda *_: None)

    def submit(self, *_):
        text = self.entry.get_text().strip()
        if not text: return
        if text.startswith('@'):
            self.activity.set_text('Use ordinary text. Confirm or Cancel in the proposal panel.'); return
        if self.busy: return
        self.busy = True; self.set_tracking_frozen(True); self.set_keep_above(False)
        def done(ok):
            self.busy = False
            if not ok:
                self.set_tracking_frozen(False)
                self.activity.set_text('Target unavailable. Focus it, then reopen with Ctrl+K.'); return
            self.entry.set_text(''); self.activity.set_text('Request sent. Review the proposal before Confirm.')
            self.post(text)
        target = self.target
        if not self.async_call(lambda valid: self.restore(target, valid), done): self.busy = False

    def key(self, _, event):
        if event.keyval == Gdk.KEY_Escape: self.dismiss(); return True
        return False

    def stop_work(self, *_):
        self.epoch += 1; self.busy = False
        self.post("stop")

    def set_tracking_frozen(self, frozen):
        if not frozen and self.tracking_frozen: self.tracking_origin = None
        self.tracking_frozen = bool(frozen)

    def follow_tick(self):
        if self.closed.is_set(): return False
        if self.worker_busy or self.busy or self.tracking_frozen or not self.get_visible() or not self.get_window(): return True
        from .input_geometry import panel_origin, smoothed_origin
        try:
            display = Gdk.Display.get_default()
            _, x, y = display.get_default_seat().get_pointer().get_position()
            monitor = display.get_monitor_at_point(x, y); area = monitor.get_workarea()
            extent = self.get_window().get_frame_extents()
            target = panel_origin((x,y), (extent.width, extent.height), (area.x, area.y, area.width, area.height))
            self.tracking_origin = smoothed_origin(self.tracking_origin, target)
            self.move(*(round(v) for v in self.tracking_origin))
        except ValueError: pass  # too small a workarea: do not move outside it
        return True

    def close(self):
        self.closed.set(); self.epoch += 1
        if self.follow_timer:
            GLib.source_remove(self.follow_timer); self.follow_timer = None

    def monitor(self):
        xd = None
        try:
            from Xlib import display, X, XK
            xd = display.Display()
            code = xd.keysym_to_keycode(XK.string_to_keysym('k'))
            while not self.closed.wait(1 / 30):
                mask = xd.screen().root.query_pointer().mask
                keys = xd.query_keymap()
                held = bool(mask & X.ControlMask) and not bool(mask & (X.ShiftMask | X.Mod1Mask | X.Mod4Mask)) and bool(keys[code // 8] & (1 << (code % 8)))
                if held and not self.chord: GLib.idle_add(self.show_command)
                self.chord = held
        except Exception: pass
        finally:
            if xd: xd.close()
