"""Click-through full-screen trail window (counterpart of the freeform focus trail drawn by OverlayWindow.swift).
Without a compositor the trail is shaped with an A8 mask, like the pointer overlay."""
import cairo, gi
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk
BLUE = (0x4F / 255, 0x8E / 255, 0xF7 / 255)

class TrailOverlay(Gtk.Window):
    def __init__(self, w, h):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.W, self.H, self.pts = w, h, []
        self.set_wmclass("tiptour-trail", "TipTourTrail"); self.set_title("TipTour highlight trail")
        self.closed = False
        self.set_app_paintable(True); self.set_decorated(False); self.set_keep_above(True); self.set_accept_focus(False)
        self.set_default_size(w, h); self.move(0, 0)
        scr = self.get_screen(); vis = scr.get_rgba_visual(); self.composited = bool(vis and scr.is_composited())
        if self.composited: self.set_visual(vis)
        self.connect("draw", lambda _w, c: (self.paint(c), False)[1]); self.connect("realize", lambda *_: self.get_window().input_shape_combine_region(cairo.Region(), 0, 0))
    def paint(self, c):
        c.set_operator(cairo.OPERATOR_SOURCE); c.set_source_rgba(0, 0, 0, 0); c.paint(); c.set_operator(cairo.OPERATOR_OVER)
        if len(self.pts) < 2: return
        c.set_line_cap(cairo.LINE_CAP_ROUND); c.set_line_join(cairo.LINE_JOIN_ROUND)
        for width, alpha in ((14, .25), (6, 1.0)):
            c.move_to(*self.pts[0])
            for p in self.pts[1:]: c.line_to(*p)
            c.set_source_rgba(*BLUE, alpha if self.composited else 1.0); c.set_line_width(width); c.stroke()
    def set_points(self, pts):
        if self.closed: return False
        self.pts = list(pts); self.show_all()
        if self.get_window() and not self.composited:
            s = cairo.ImageSurface(cairo.FORMAT_A8, self.W, self.H); self.paint(cairo.Context(s))
            self.get_window().shape_combine_region(Gdk.cairo_region_create_from_surface(s), 0, 0)
            self.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
        self.queue_draw()
    def clear(self): self.pts = []; self.hide()
    def close(self): self.closed = True; self.clear()
