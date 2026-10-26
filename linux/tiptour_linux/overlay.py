"""Pointer overlay for X11 using TipTour's own cursor art: CursorArrowShape path from
OverlayWindow.swift (24-unit viewBox, 44x44, white fill, 4.2pt #4F8EF7 round stroke, soft blue glow)
and the navigation bubble (11pt medium white text, #4F8EF7 rounded-rect r=6, padding 8x4).
Click-through. Glow needs a compositing manager; without one (e.g. bare Xvfb) the window is shaped
and the glow is omitted. Not ported yet: travel-direction rotation, breathing animation, Neko mode,
multi-display. Wayland-native sessions cannot place windows this way (X11/XWayland only)."""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import cairo, os

BLUE = (0x4F / 255, 0x8E / 255, 0xF7 / 255)
SIZE = 44

def arrow_path(c, cx, cy, size=SIZE):
    s = size / 24.0; ox = cx - 12 * s; oy = cy - 12 * s
    P = lambda x, y: (ox + x * s, oy + y * s)
    def quad(c, p0, ctl, p1):  # cairo has cubic only: elevate quad -> cubic
        c1 = (p0[0] + 2 / 3 * (ctl[0] - p0[0]), p0[1] + 2 / 3 * (ctl[1] - p0[1])); c2 = (p1[0] + 2 / 3 * (ctl[0] - p1[0]), p1[1] + 2 / 3 * (ctl[1] - p1[1]))
        c.curve_to(*c1, *c2, *p1)
    c.new_path(); p = P(4.037, 4.688); c.move_to(*p)
    cur = P(4.037, 4.688)
    quad(c, cur, P(3.90, 3.90), P(4.688, 4.037)); c.line_to(*P(20.688, 10.537)); cur = P(20.688, 10.537)
    quad(c, cur, P(21.42, 10.84), P(20.625, 11.484)); c.line_to(*P(14.501, 13.064)); cur = P(14.501, 13.064)
    quad(c, cur, P(13.43, 13.34), P(13.063, 14.499)); c.line_to(*P(11.484, 20.625)); cur = P(11.484, 20.625)
    quad(c, cur, P(11.17, 21.42), P(10.537, 20.688)); c.close_path()

class PointerOverlay(Gtk.Window):
    W, H = 420, 90
    CX, CY = 30, 30           # arrow center inside the window
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_wmclass('tiptour-overlay', 'TipTourOverlay')  # lets the click detector ignore our own click-through pointer window
        self.set_app_paintable(True); self.set_decorated(False); self.set_keep_above(True); self.set_accept_focus(False)
        self.set_default_size(self.W, self.H); self.label = ""
        scr = self.get_screen(); vis = scr.get_rgba_visual()
        self.composited = bool(vis and scr.is_composited())
        if self.composited: self.set_visual(vis)
        self.connect("draw", lambda w, c: (self.paint(c), False)[1]); self.connect("realize", self.on_realize)
        self.cur = (100, 100); self.tip = (100, 100)
    def on_realize(self, *_):
        self.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
        if not self.composited: self.apply_shape()
    def apply_shape(self):
        s = cairo.ImageSurface(cairo.FORMAT_A8, self.W, self.H); self.paint(cairo.Context(s))
        self.get_window().shape_combine_region(Gdk.cairo_region_create_from_surface(s), 0, 0)
        self.get_window().input_shape_combine_region(cairo.Region(), 0, 0)  # re-assert: bounding shape would otherwise also become the input shape and steal real pointer events
    def paint(self, c):
        c.set_operator(cairo.OPERATOR_SOURCE); c.set_source_rgba(0, 0, 0, 0); c.paint(); c.set_operator(cairo.OPERATOR_OVER)
        if self.composited:
            for w, a in ((14, .10), (9, .16), (5, .24)):
                arrow_path(c, self.CX, self.CY); c.set_source_rgba(*BLUE, a); c.set_line_width(w); c.set_line_join(cairo.LINE_JOIN_ROUND); c.stroke()
        arrow_path(c, self.CX, self.CY); c.set_source_rgb(1, 1, 1); c.fill_preserve()
        c.set_source_rgb(*BLUE); c.set_line_width(4.2 * SIZE / 44); c.set_line_cap(cairo.LINE_CAP_ROUND); c.set_line_join(cairo.LINE_JOIN_ROUND); c.stroke()
        if self.label:
            c.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL); c.set_font_size(11)
            ext = c.text_extents(self.label); bw, bh = ext.x_advance + 16, 11 + 8 + 3
            bx, by = self.CX + 10 + 12, self.CY + 18  # right/below the cursor (bubbleLeft/TopOffsetFromCursor)
            r = 6; c.new_sub_path()
            c.arc(bx + bw - r, by + r, r, -1.5708, 0); c.arc(bx + bw - r, by + bh - r, r, 0, 1.5708); c.arc(bx + r, by + bh - r, r, 1.5708, 3.1416); c.arc(bx + r, by + r, r, 3.1416, 4.7124); c.close_path()
            c.set_source_rgb(*BLUE); c.fill(); c.set_source_rgb(1, 1, 1); c.move_to(bx + 8, by + bh - 7); c.show_text(self.label)
    def point_to(self, x, y, label="", glide_ms=600):
        self.label = label[:40]; self.show_all()
        if self.get_window() and not self.composited: self.apply_shape()
        self.queue_draw(); sx, sy = self.cur; steps = max(1, glide_ms // 16); n = [0]
        def tick():
            n[0] += 1; t = n[0] / steps; e = 1 - (1 - t) ** 3
            self.move(int(sx + (x - sx) * e) - self.CX, int(sy + (y - sy) * e) - self.CY)
            if n[0] >= steps: self.cur = self.tip = (x, y); return False
            return True
        GLib.timeout_add(16, tick)


class PausePanel(Gtk.Window):
    """Small on-screen Retry / Skip prompt shown while a taught step is paused (click had no observable effect, or another app took focus).
    Own WM_CLASS (ignored by the click detector). Never takes keyboard focus. on_retry/on_skip are called on the GTK thread: hand work off to another thread."""
    def __init__(self, on_retry, on_skip):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_wmclass('tiptour-overlay', 'TipTourOverlay'); self.set_keep_above(True); self.set_accept_focus(False)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); box.set_border_width(8)
        self.msg = Gtk.Label(label=""); self.retry = Gtk.Button(label="Retry"); self.skip = Gtk.Button(label="Skip")
        self.retry.connect("clicked", lambda *_: on_retry()); self.skip.connect("clicked", lambda *_: on_skip())
        for w in (self.msg, self.retry, self.skip): box.pack_start(w, False, False, 0)
        frame = Gtk.Frame(); frame.add(box); self.add(frame)
    tok = -1  # -1 = hidden/no episode: a click on it can never match a live plan token
    def show_at(self, x, y, text, tok=None):
        self.tok = tok; self.msg.set_text(text); self.show_all(); self.move(max(0, int(x) - 40), int(y) + 60)
        import os
        if os.environ.get("TIPTOUR_PANEL_COORDS"): GLib.timeout_add(600, self._dump)
    def hide_panel(self): self.tok = -1; self.hide()

    def _dump(self):  # test aid only (env-gated): screen centers of the buttons so a harness can press them with real synthetic input
        try:
            ox, oy = self.get_window().get_origin()[1:]
            out = []
            for n, b in (("retry", self.retry), ("skip", self.skip)):
                a = b.get_allocation(); out.append("%s %d %d" % (n, ox + a.x + a.width // 2, oy + a.y + a.height // 2))
            open(os.environ["TIPTOUR_PANEL_COORDS"], "w").write("\n".join(out) + "\n")
        except Exception as e: open(os.environ["TIPTOUR_PANEL_COORDS"], "w").write("err %s\n" % type(e).__name__)
        return False
