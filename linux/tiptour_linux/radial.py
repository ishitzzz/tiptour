"""Opt-in X11 radial preview from pinned Mac switcher, no input-mode dispatch.

Ctrl+Alt+Super without Shift, listen-only polling. No provider/key/mode changes.
View offsets preserve RadialInputSwitcherView. Native X queries can still hang.
"""
import math
import threading
import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from .input_geometry import radial_option


def chord(mask):
    from Xlib import X
    return all(mask & m for m in (X.ControlMask, X.Mod1Mask, X.Mod4Mask)) and not mask & X.ShiftMask


class State:
    def __init__(self): self.center = None; self.hover = None
    def begin(self, point): self.center = point; self.hover = None
    def move(self, point):
        if self.center is not None: self.hover = radial_option(point, self.center)
    def end(self, point):
        selected = (radial_option(point, self.center) or self.hover) if self.center is not None else None
        self.center = self.hover = None
        return selected
    def cancel(self): self.center = self.hover = None


class Monitor:
    def __init__(self, post, hz=60):
        self.post = post; self.dt = 1 / hz; self.closed = threading.Event()
        self.thread = None
    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='tiptour-radial'); self.thread.start()
    def run(self):
        from Xlib import display
        d = None; held = False; last = None
        try:
            d = display.Display(); root = d.screen().root
            while not self.closed.wait(self.dt):
                q = root.query_pointer(); point = (q.root_x, q.root_y); now = chord(q.mask)
                if self.closed.is_set(): break
                if now and not held: self.post('begin', point)
                elif now and point != last: self.post('move', point)
                elif held and not now: self.post('end', point)
                held = now; last = point
        except Exception:
            if not self.closed.is_set(): self.post('error', (0,0))
        finally:
            if d: d.close()
    def close(self):
        self.closed.set()
        if self.thread: self.thread.join(.5)
        return not self.thread or not self.thread.is_alive()


class RadialPreview(Gtk.Window):
    W, H = 270, 220  # Mac content220x190 plus capsule/shadow overflow padding
    def __init__(self, status):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_wmclass('tiptour-radial', 'TipTourRadial')
        self.set_name('tiptour-radial'); self.set_title('TipTour radial preview')
        self.set_decorated(False); self.set_keep_above(True); self.set_accept_focus(False)
        self.set_focus_on_map(False); self.set_app_paintable(True)
        self.set_default_size(self.W, self.H)
        visual = self.get_screen().get_rgba_visual()
        self.composited = bool(visual and self.get_screen().is_composited())
        if self.composited: self.set_visual(visual)
        self.state = State(); self.status = status; self.closed = False; self.events = []
        self.connect('realize', lambda *_: self.shape())
        self.connect('draw', lambda _, c: (self.paint(c), False)[1])
        self.monitor = Monitor(self.post); self.monitor.start()
    def post(self, kind, point):
        if not self.closed: GLib.idle_add(self.transition, kind, point)
    def transition(self, kind, point):
        if self.closed or self.monitor.closed.is_set(): return False
        self.events.append((kind, point))
        if kind == 'error':
            self.state.cancel(); self.hide(); self.status('Radial preview unavailable: X11 monitor failed. No mode was selected.'); return False
        if kind == 'begin':
            self.status('Radial preview only. Close separate Ask/shortcut apps: partial modifier chords may activate them.')
            self.state.begin(point)
            display = Gdk.Display.get_default(); area = display.get_monitor_at_point(*point).get_workarea()
            # Keep the true gesture center; refuse instead of silently shifting wedges.
            x,y = round(point[0]-self.W/2),round(point[1]-self.H/2)
            if x < area.x or y < area.y or x+self.W > area.x+area.width or y+self.H > area.y+area.height:
                self.state.cancel(); self.status('Radial preview unavailable near the screen edge. Move inward and try again.'); return False
            self.move(x,y); self.show_all()
        elif kind == 'move': self.state.move(point)
        elif kind == 'end':
            selected = self.state.end(point); self.hide()
            if selected: self.status('Radial preview: %s selected. Input-mode dispatch is not connected.' % selected.title())
        self.queue_draw()
        if self.get_window(): self.shape()
        return False
    def shape(self):
        win = self.get_window()
        if not win: return
        if not self.composited:
            surface = cairo.ImageSurface(cairo.FORMAT_A8, self.W, self.H); self.paint(cairo.Context(surface))
            win.shape_combine_region(Gdk.cairo_region_create_from_surface(surface), 0, 0)
        win.input_shape_combine_region(cairo.Region(), 0, 0)
    def paint(self, c):
        c.set_operator(cairo.OPERATOR_SOURCE); c.set_source_rgba(0,0,0,0); c.paint(); c.set_operator(cairo.OPERATOR_OVER)
        cx,cy = self.W/2,self.H/2
        c.arc(cx,cy,27,0,math.tau); c.set_source_rgba(0,0,0,.22 if self.composited else 1); c.fill_preserve();c.set_source_rgb(55/255,59/255,57/255);c.set_line_width(.7);c.stroke()
        c.rectangle(28,self.H-22,self.W-56,19);c.set_source_rgba(0,0,0,.8 if self.composited else 1);c.fill()
        c.select_font_face('Sans',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_NORMAL);c.set_font_size(10)
        text='Preview only: no dispatch';ext=c.text_extents(text)
        c.set_source_rgb(.68,.71,.70);c.move_to(cx-ext.x_advance/2,self.H-8);c.show_text(text)
        for label,dx,dy in [('speak',0,-76),('type',74,46),('highlight',-74,46)]:
            # Linux top-left uses the SwiftUI view's down-positive offsets.
            x,y=cx+dx-48,cy+dy-17;r=17
            c.new_sub_path();c.arc(x+96-r,y+r,r,-math.pi/2,math.pi/2);c.arc(x+r,y+r,r,math.pi/2,math.pi*1.5);c.close_path()
            on=self.state.hover==label
            c.set_source_rgba(*( (37/255,99/255,235/255,1) if on else (0,0,0,.48 if self.composited else 1)));c.fill_preserve()
            c.set_source_rgb(*( (37/255,99/255,235/255) if on else (55/255,59/255,57/255)));c.set_line_width(.7);c.stroke()
            c.select_font_face('Sans',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_BOLD);c.set_font_size(12)
            c.set_source_rgb(*( (1,1,1) if on else (173/255,181/255,178/255)))
            text=label.title();ext=c.text_extents(text);c.move_to(cx+dx-ext.x_advance/2,cy+dy+4);c.show_text(text)
    def close(self):
        self.closed = True; self.state.cancel(); self.hide()
        return self.monitor.close()
