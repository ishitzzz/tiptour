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

import math, time

# --- Movement ported from TipTour/UI/OverlayWindow.swift (pinned 6e97782). Constants are the Mac's, quoted with their source: ---
FOLLOW_OFFSET = (35, 25)        # startTrackingCursor: buddy = mouse + (35, 25)
TICK_MS = 16                    # Timer 0.016 (tracking); flights 1/60
SPRING_RESPONSE, SPRING_DAMPING = 0.2, 0.6   # .animation(.spring(response: 0.2, dampingFraction: 0.6), value: cursorPosition) while following
POINTER_DISTANCE_FROM_TARGET, SCREEN_PADDING = 42, 34   # pointerLandingPose
SETTLE_S, SETTLE_FRAC = 0.22, 0.08   # settleAtDestination: ease-in-out 0.22s from a 8% overshoot offset, then 0.24s before onComplete
RETURN_CANCEL_PX, DOCK_BELOW_PX, DOCK_S = 100, 72, 0.34   # return-flight cancel by mouse move >100; dockBackToCursor when the return is < 72 px (0.34s smoothstep)
RELEASE_DELAY_S = 0.25          # releaseHeldPointerAndFlyBack: bubble fades, 0.25s later the return flight starts
SIDES = {"left": 0.0, "right": math.pi, "above": math.pi / 2, "below": -math.pi / 2, "upperLeft": math.pi / 4, "upperRight": math.pi * 3 / 4, "lowerLeft": -math.pi / 4, "lowerRight": -3 * math.pi / 4}
CORNERS = ("upperLeft", "upperRight", "lowerLeft", "lowerRight")

def rot_deg(rad): return rad * 180.0 / math.pi + 137.0           # cursorRotationDegrees
def lerp_angle(a, b, amt):                                          # interpolatedAngleDegrees
    d = math.fmod(b - a, 360)
    d = d - 360 if d > 180 else (d + 360 if d < -180 else d)
    return a + d * amt
def smootherstep(p): return p * p * p * (p * (p * 6.0 - 15.0) + 10.0)

class PointerOverlay(Gtk.Window):
    W, H = 420, 90
    CX, CY = 30, 30           # arrow center inside the window
    def __init__(self):
        from . import x11_capture
        self.clean_capture_ready=False
        try:x11_capture.prepare();self.clean_capture_ready=True
        except Exception as e:print('capture backing unavailable:',e,flush=True)
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_wmclass('tiptour-overlay', 'TipTourOverlay')  # lets the click detector ignore our own click-through pointer window
        self.set_app_paintable(True); self.set_decorated(False); self.set_keep_above(True); self.set_accept_focus(False)
        self.set_default_size(self.W, self.H); self.label = ""; self.show_label = False
        scr = self.get_screen(); vis = scr.get_rgba_visual()
        self.composited = bool(vis and scr.is_composited())
        if self.composited: self.set_visual(vis)
        self.connect("draw", lambda w, c: (self.paint(c), False)[1]); self.connect("realize", self.on_realize)
        m = self._mouse(); self.cur = (m[0] + FOLLOW_OFFSET[0], m[1] + FOLLOW_OFFSET[1]); self.tip = self.cur; self.vel = (0.0, 0.0)
        self.mode = "follow"; self.rot = 0.0; self.scale = 1.0; self.flight = None; self.returning = False; self.nav_mouse = m; self.target = None; self.land_rot = 0.0; self.events = []
        GLib.timeout_add(TICK_MS, self._tick)
    # ---- helpers ----
    def _mouse(self):
        try:
            seat = Gdk.Display.get_default().get_default_seat(); _, x, y = seat.get_pointer().get_position(); return (float(x), float(y))
        except Exception: return getattr(self, "cur", (100.0, 100.0))
    def _screen(self):
        d = Gdk.Display.get_default(); g = d.get_monitor(0).get_geometry() if d.get_n_monitors() else None
        return (g.width, g.height) if g else (1920, 1080)
    def _log(self, kind, **kw): self.events.append(dict(kind=kind, t=round(time.time(), 3), **kw)); self.events = self.events[-400:]
    def on_realize(self, *_):
        self.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
        if not self.composited: self.apply_shape()
    def apply_shape(self):
        s = cairo.ImageSurface(cairo.FORMAT_A8, self.W, self.H); self.paint(cairo.Context(s))
        self.get_window().shape_combine_region(Gdk.cairo_region_create_from_surface(s), 0, 0)
        self.get_window().input_shape_combine_region(cairo.Region(), 0, 0)  # re-assert: bounding shape would otherwise also become the input shape and steal real pointer events
    def paint(self, c):
        c.set_operator(cairo.OPERATOR_SOURCE); c.set_source_rgba(0, 0, 0, 0); c.paint(); c.set_operator(cairo.OPERATOR_OVER)
        c.save(); c.translate(self.CX, self.CY); c.rotate(self.rot * math.pi / 180.0); c.scale(self.scale, self.scale); c.translate(-self.CX, -self.CY)
        if self.composited:
            for w, a in ((14, .10), (9, .16), (5, .24)):
                arrow_path(c, self.CX, self.CY); c.set_source_rgba(*BLUE, a); c.set_line_width(w); c.set_line_join(cairo.LINE_JOIN_ROUND); c.stroke()
        arrow_path(c, self.CX, self.CY); c.set_source_rgb(1, 1, 1); c.fill_preserve()
        c.set_source_rgb(*BLUE); c.set_line_width(4.2 * SIZE / 44); c.set_line_cap(cairo.LINE_CAP_ROUND); c.set_line_join(cairo.LINE_JOIN_ROUND); c.stroke()
        c.restore()
        if self.label and self.show_label:
            c.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL); c.set_font_size(11)
            ext = c.text_extents(self.label); bw, bh = ext.x_advance + 16, 11 + 8 + 3
            bx, by = self.CX + 10 + 12, self.CY + 18  # right/below the cursor (bubbleLeft/TopOffsetFromCursor)
            r = 6; c.new_sub_path()
            c.arc(bx + bw - r, by + r, r, -1.5708, 0); c.arc(bx + bw - r, by + bh - r, r, 0, 1.5708); c.arc(bx + r, by + bh - r, r, 1.5708, 3.1416); c.arc(bx + r, by + r, r, 3.1416, 4.7124); c.close_path()
            c.set_source_rgb(*BLUE); c.fill(); c.set_source_rgb(1, 1, 1); c.move_to(bx + 8, by + bh - 7); c.show_text(self.label)
    # ---- landing pose (pointerLandingPose) ----
    def landing_pose(self, target):
        W, H = self._screen(); best = None
        for side, rad in SIDES.items():
            dx, dy = math.cos(rad), math.sin(rad); ideal = (target[0] - dx * POINTER_DISTANCE_FROM_TARGET, target[1] - dy * POINTER_DISTANCE_FROM_TARGET)
            ctr = (max(SCREEN_PADDING, min(ideal[0], W - SCREEN_PADDING)), max(SCREEN_PADDING, min(ideal[1], H - SCREEN_PADDING)))
            clamp_pen = math.hypot(ctr[0] - ideal[0], ctr[1] - ideal[1]) * 4.0; travel_pen = math.hypot(ctr[0] - self.cur[0], ctr[1] - self.cur[1]) * 0.08
            hb = 28 if side in CORNERS else (18 if side in ("left", "right") else 0); corner_pen = 0 if side in CORNERS else 8
            clear = min(target[0], W - target[0], target[1], H - target[1]) * 0.02
            sc = hb + clear - clamp_pen - travel_pen - corner_pen
            if best is None or sc > best[0]: best = (sc, side, ctr)   # Swift max(by:) keeps the FIRST maximal element on ties; strict > here is the same (comment corrected, behavior unchanged)
        _, side, ctr = best; ang = math.atan2(target[1] - ctr[1], target[0] - ctr[0])
        return ctr, rot_deg(ang), side
    # ---- flights ----
    def _start_flight(self, dest, land_rot, follows, on_done):   # animateBezierFlightArc
        sx, sy = self.cur; dx, dy = dest[0] - sx, dest[1] - sy; dist = math.hypot(dx, dy)
        dur = min(max(dist / 520.0, 1.05), 2.2)
        ux, uy = (dx / dist, dy / dist) if dist > 0 else (1.0, 0.0); nx, ny = -uy, ux
        arc_dir = -1 if sx <= dest[0] else 1; cd = min(max(dist * 0.38, 70), 220); ah = min(max(dist * 0.08, 18), 58) * arc_dir
        c1 = (sx + ux * cd + nx * ah, sy + uy * cd + ny * ah); c2 = (dest[0] - ux * cd - nx * ah * 0.65, dest[1] - uy * cd - ny * ah * 0.65)
        self.flight = dict(kind="bezier", t0=time.monotonic(), dur=dur, start=(sx, sy), end=dest, c1=c1, c2=c2, land=land_rot, follows=follows, done=on_done, prev=(sx, sy), smooth_rot=self.rot)
        self._log("flight_start", dist=round(dist, 1), dur=round(dur, 3), to=(round(dest[0], 1), round(dest[1], 1)), returning=self.returning)
    def point_to(self, x, y, label="", glide_ms=None):
        """startNavigatingToElement: leave follow mode, fly a bezier arc to the landing pose, settle, then hold and point (bubble shown)."""
        self.label = label[:40]; self.show_label = False; self.retired = False; self.target = (float(x), float(y)); self.show_all()
        self.nav_mouse = self._mouse(); self.mode = "nav"; self.returning = False
        pose_c, pose_rot, side = self.landing_pose(self.target); self.land_rot = pose_rot; self.tip = self.target
        self._log("nav_start", target=self.target, pose=(round(pose_c[0], 1), round(pose_c[1], 1)), side=side)
        self._start_flight(pose_c, pose_rot, True, self._arrived)
    def _arrived(self):   # startPointingAtElement
        if self.mode != "nav" or self.returning or getattr(self, "retired", False): self._log("arrival_ignored", retired=getattr(self, "retired", False)); return   # release must win: a late arrival may not revive the label
        self.mode = "point"; self.rot = self.land_rot; self.show_label = True; self._log("pointing", at=(round(self.cur[0], 1), round(self.cur[1], 1)))
    def retire(self):
        """releaseHeldPointerAndFlyBack: the held pointer is released (target clicked / skipped / plan ended); 0.25s later it flies back to the user's cursor."""
        if self.mode not in ("point", "nav") or self.returning: return
        self.retired = True; self.show_label = False; self.queue_draw(); self._log("release", mode=self.mode)
        GLib.timeout_add(int(RELEASE_DELAY_S * 1000), lambda: (self._fly_back(), False)[1])
    def _fly_back(self):   # startFlyingBackToCursor
        if self.mode not in ("point", "nav") or self.returning: return
        m = self._mouse(); dest = (m[0] + FOLLOW_OFFSET[0], m[1] + FOLLOW_OFFSET[1]); self.nav_mouse = m; self.mode = "nav"; self.returning = True
        dist = math.hypot(dest[0] - self.cur[0], dest[1] - self.cur[1])
        if dist < DOCK_BELOW_PX:
            self.flight = dict(kind="dock", t0=time.monotonic(), dur=DOCK_S, start=self.cur, end=dest, rot0=self.rot); self._log("dock", dist=round(dist, 1)); return
        self._start_flight(dest, 0.0, False, self._finish_follow)
    def _finish_follow(self):   # finishNavigationAndResumeFollowing
        self.flight = None; self.mode = "follow"; self.returning = False; self.rot = 0.0; self.scale = 1.0; self.show_label = False; self.retired = False; self.vel = (0.0, 0.0); self.queue_draw(); self._log("follow")
    # ---- frame tick ----
    def _tick(self):
        now = time.monotonic(); m = self._mouse(); dt = TICK_MS / 1000.0
        if self.mode == "nav" and self.returning and math.hypot(m[0] - self.nav_mouse[0], m[1] - self.nav_mouse[1]) > RETURN_CANCEL_PX:
            self._log("return_cancelled_by_mouse"); self.show_label = False; self._finish_follow()
        if self.mode == "follow":
            k = (2 * math.pi / SPRING_RESPONSE) ** 2; cc = 2 * SPRING_DAMPING * math.sqrt(k)   # SwiftUI spring(response, dampingFraction) as a mass-1 spring
            tx, ty = m[0] + FOLLOW_OFFSET[0], m[1] + FOLLOW_OFFSET[1]; vx, vy = self.vel
            vx += (k * (tx - self.cur[0]) - cc * vx) * dt; vy += (k * (ty - self.cur[1]) - cc * vy) * dt
            self.cur = (self.cur[0] + vx * dt, self.cur[1] + vy * dt); self.vel = (vx, vy); self.tip = self.cur
        elif self.flight:
            f = self.flight; p = min(1.0, (now - f["t0"]) / f["dur"])
            if f["kind"] == "dock":
                t = p * p * (3 - 2 * p); self.cur = (f["start"][0] + (f["end"][0] - f["start"][0]) * t, f["start"][1] + (f["end"][1] - f["start"][1]) * t); self.rot = lerp_angle(f["rot0"], 0.0, t)
                if p >= 1.0: self.cur = f["end"]; self.rot = 0.0; self._finish_follow()
            elif f["kind"] == "bezier":
                if p >= 1.0:
                    ex, ey = f["end"]; self.cur = (ex, ey); self.scale = 1.0; done = f["done"]
                    if f["follows"]:   # settleAtDestination: 8% overshoot offset, ease back over 0.22s, onComplete 0.24s after
                        self.cur = (ex + (self.cur[0] - ex) * SETTLE_FRAC, ey + (self.cur[1] - ey) * SETTLE_FRAC)
                        self.flight = dict(kind="settle", t0=now, dur=SETTLE_S, start=self.cur, end=(ex, ey), rot0=self.rot, rot1=f["land"], done=done, fired=False)
                    else: self.flight = None; done()
                else:
                    t = smootherstep(p); o = 1 - t; (sx, sy), (c1x, c1y), (c2x, c2y), (ex, ey) = f["start"], f["c1"], f["c2"], f["end"]
                    bx = o * o * o * sx + 3 * o * o * t * c1x + 3 * o * t * t * c2x + t * t * t * ex; by = o * o * o * sy + 3 * o * o * t * c1y + 3 * o * t * t * c2y + t * t * t * ey
                    ang = math.atan2(by - f["prev"][1], bx - f["prev"][0]); travel = rot_deg(ang)
                    if f["follows"] and f["land"] is not None:
                        rb = min(1.0, max(0.0, (p - 0.66) / (1.0 - 0.66))); eb = rb * rb * (3.0 - 2.0 * rb); target_rot = lerp_angle(travel, f["land"], eb)
                    elif f["follows"]: target_rot = travel
                    else: target_rot = f["land"] if f["land"] is not None else f["smooth_rot"]
                    f["smooth_rot"] = lerp_angle(f["smooth_rot"], target_rot, 0.11 if f["follows"] else 0.05); self.rot = f["smooth_rot"]; f["prev"] = (bx, by); self.cur = (bx, by)
                    self.scale = 1.0 + math.sin(p * math.pi) * 0.045
            elif f["kind"] == "settle":
                p2 = min(1.0, (now - f["t0"]) / SETTLE_S); t = (1 - math.cos(math.pi * p2)) / 2   # easeInOut
                self.cur = (f["start"][0] + (f["end"][0] - f["start"][0]) * t, f["start"][1] + (f["end"][1] - f["start"][1]) * t); self.rot = lerp_angle(f["rot0"], f["rot1"], t)
                if (now - f["t0"]) >= SETTLE_S + 0.02 and not f["fired"]: f["fired"] = True; self.cur = f["end"]; self.flight = None; f["done"]()
        if self.get_visible():
            self.move(int(self.cur[0]) - self.CX, int(self.cur[1]) - self.CY)
            if self.flight or self.mode != "follow":
                self.queue_draw()
                if not self.composited and self.get_window() and now - getattr(self, "_shape_t", 0) > 0.07: self._shape_t = now; self.apply_shape()   # bare X (no compositor) needs the shape refreshed as the arrow rotates; throttled so the tick stays cheap
        return True


class PausePanel(Gtk.Window):
    """Small on-screen Retry / Skip prompt shown while a taught step is paused (click had no observable effect, or another app took focus).
    Own WM_CLASS (ignored by the click detector). Never takes keyboard focus. on_retry/on_skip are called on the GTK thread: hand work off to another thread."""
    def __init__(self, on_retry, on_skip):
        from . import x11_capture
        self.clean_capture_ready=False
        try:x11_capture.prepare();self.clean_capture_ready=True
        except Exception as e:print('capture backing unavailable:',e,flush=True)
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_wmclass('tiptour-overlay', 'TipTourOverlay'); self.set_keep_above(True); self.set_accept_focus(False)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); box.set_border_width(8)
        self.msg = Gtk.Label(label=""); self.row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._on_retry, self._on_skip = on_retry, on_skip
        self.retry = self.skip = None
        box.pack_start(self.msg, False, False, 0); box.pack_start(self.row, False, False, 0)
        frame = Gtk.Frame(); frame.add(box); self.add(frame)
    tok = -1
    def show_at(self, x, y, text, tok=None):
        self.tok = -1
        for child in list(self.row.get_children()): self.row.remove(child); child.destroy()
        self.retry = Gtk.Button(label="Retry"); self.skip = Gtk.Button(label="Skip")
        # New widgets per pause episode; a queued old callback carries its OLD token.
        self.retry.connect("clicked", lambda *_, t=tok: self._on_retry(t))
        self.skip.connect("clicked", lambda *_, t=tok: self._on_skip(t))
        self.row.pack_start(self.retry, False, False, 0); self.row.pack_start(self.skip, False, False, 0)
        self.msg.set_text(text); self.tok = tok; self.show_all(); self.move(max(0, int(x) - 40), int(y) + 60)
        import os
        if os.environ.get("TIPTOUR_PANEL_COORDS"): GLib.timeout_add(600, self._dump)
    def hide_panel(self):
        self.tok = -1
        self.retry and self.retry.set_sensitive(False); self.skip and self.skip.set_sensitive(False)
        self.hide()

    def _dump(self):  # test aid only (env-gated): screen centers of the buttons so a harness can press them with real synthetic input
        try:
            ox, oy = self.get_window().get_origin()[1:]
            out = []
            for n, b in (("retry", self.retry), ("skip", self.skip)):
                a = b.get_allocation(); out.append("%s %d %d" % (n, ox + a.x + a.width // 2, oy + a.y + a.height // 2))
            open(os.environ["TIPTOUR_PANEL_COORDS"], "w").write("\n".join(out) + "\n")
        except Exception as e: open(os.environ["TIPTOUR_PANEL_COORDS"], "w").write("err %s\n" % type(e).__name__)
        return False


class ProposalPanel(Gtk.Window):
    """On-screen plan proposal: the COMPLETE ordered plan text (goal, app, every step with its action values) plus revision-bound Confirm / Cancel buttons.
    Own WM_CLASS (ignored by the click detector), never takes keyboard focus. Buttons call on_answer(kind, rev) on the GTK thread: hand work off to another thread."""
    def __init__(self, on_answer):
        from . import x11_capture
        self.clean_capture_ready=False
        try:x11_capture.prepare();self.clean_capture_ready=True
        except Exception as e:print('capture backing unavailable:',e,flush=True)
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_wmclass('tiptour-overlay', 'TipTourOverlay'); self.set_keep_above(True); self.set_accept_focus(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); box.set_border_width(12)
        self.head = Gtk.Label(label=""); self.head.set_xalign(0); self.body = Gtk.Label(label=""); self.body.set_xalign(0); self.body.set_line_wrap(True); self.body.set_max_width_chars(80)
        self.row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); self._on_answer = on_answer; self.ok = self.no = None
        row = self.row
        import gi; from gi.repository import Pango
        self.body.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR); self.body.set_selectable(False)
        sw = Gtk.ScrolledWindow(); sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); sw.set_min_content_width(560); sw.set_max_content_height(420); sw.set_propagate_natural_height(True); inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6); self.detail = Gtk.Label(label=""); self.detail.set_xalign(0); self.detail.set_line_wrap(True); self.detail.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR); self.detail.set_max_width_chars(80); self.detail.set_selectable(False)
        exp = Gtk.Expander(label="Details (every field the plan carries)"); exp.add(self.detail); inner.pack_start(self.body, False, False, 0); inner.pack_start(exp, False, False, 0); sw.add(inner); self.sw = sw  # a long plan scrolls instead of being cut off
        box.pack_start(self.head, False, False, 0); box.pack_start(sw, True, True, 0); box.pack_start(row, False, False, 0)
        frame = Gtk.Frame(); frame.add(box); self.add(frame)
    rev = -1  # -1 = hidden: a click can never match a live proposal
    def show_plan(self, rev, text, details="", on_shown=None):
        self.rev = -1; self._pending_rev = rev; self._on_shown = on_shown
        for _c in list(self.row.get_children()): self.row.remove(_c); _c.destroy()  # NEW button instances per episode, each bound to ITS revision at creation (closure), dead until this episode is drawn: an old button/queued click cannot exist for a newer revision
        self.ok = Gtk.Button(label="Confirm"); self.no = Gtk.Button(label="Cancel")
        self.ok.connect("clicked", lambda *_, r=rev: self._on_answer("confirm", r)); self.no.connect("clicked", lambda *_, r=rev: self._on_answer("cancel", r))
        self.ok.set_sensitive(False); self.no.set_sensitive(False); self.row.pack_start(self.ok, False, False, 0); self.row.pack_start(self.no, False, False, 0); self.row.show_all()
        if not getattr(self, "_draw_hooked", False): self._draw_hooked = True; self.connect("draw", self._drawn)
        self.head.set_markup("<b>Proposed plan, revision %d. Nothing runs until you confirm.</b>" % rev); self.body.set_text(text); self.detail.set_text(details); self.show_all(); GLib.idle_add(lambda: (self.sw.get_vadjustment().set_value(0), False)[1])  # always start at the TOP of the plan
        self.move(40, 40)
        import os
        if os.environ.get("TIPTOUR_PANEL_COORDS"): GLib.timeout_add(600, self._dump)
    def _drawn(self, *_):
        cb = getattr(self, "_on_shown", None)
        if cb and getattr(self, "_pending_rev", -1) >= 0:
            rv = self._pending_rev; self._pending_rev = -1; self._on_shown = None; self.rev = rv; self.ok.set_sensitive(True); self.no.set_sensitive(True); cb(rv)
        return False
    def hide_panel(self): self.rev = -1; self._pending_rev = -1; self._on_shown = None; self.ok and self.ok.set_sensitive(False); self.no and self.no.set_sensitive(False); self.hide()
    def _dump(self):  # test aid only (env-gated)
        import os
        try:
            ox, oy = self.get_window().get_origin()[1:]; out = []
            for n, b in (("confirm", self.ok), ("cancel", self.no)):
                a = b.get_allocation(); out.append("%s %d %d" % (n, ox + a.x + a.width // 2, oy + a.y + a.height // 2))
            open(os.environ["TIPTOUR_PANEL_COORDS"], "w").write("\n".join(out) + "\n")
        except Exception as e: open(os.environ["TIPTOUR_PANEL_COORDS"], "w").write("err %s\n" % type(e).__name__)
        return False
