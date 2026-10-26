"""Listen-only click detector (analogue of Mac Utilities/ClickDetector.swift).

Mac: CGEventTap listenOnly on leftMouseDown, rect+6pt inflation or 40pt radius
point tolerance, 0.18s post-hit grace, disarmed state ignores clicks.
Linux/X11: XInput2 RawButtonPress hook (listen-only, no grab) when available,
else fallback polling of XQueryPointer button-1 state at ~100 Hz, which can
miss presses shorter than the poll interval. self.backend reports which.
ADDITIVE vs Mac: at press we also require the topmost top-level window under the pointer to equal the one pinned at arm time and focus not to move to a third window (the Mac tap checks coordinates only). Position is read via query_pointer right after the event (small race if the
pointer moves in between). Only button 1 fires; XI2 raw events do not report
which window got the click.
Wayland: not supported (no global pointer state) - start() reports False.
"""
import os, threading, time

POINT_TOL = 40.0
RECT_INFLATE = 6.0
GRACE_S = 0.18


class ClickDetector:
    def __init__(self, poll_hz=100, clock=time.monotonic):
        self._lock = threading.Lock()
        self._point = None
        self._rect = None
        self._cb = None
        self._last_hit = None
        self._clock = clock
        self._poll = 1.0 / poll_hz
        self._thread = None
        self._stop = threading.Event()
        self.available = False
        self.backend = None
        self._d = None; self._gd = None; self._gd_lock = threading.RLock()
        self._pin = None
        self.errors = []  # thread/loop errors (type names only), never swallowed silently
        self.thread_starts = 0  # backend lifecycle evidence: must stay 1 per process
        self.check_windows = True
        self.ignore_classes = ('tiptour-overlay', 'TipTourOverlay')
        self.presses = []  # evidence: every left press seen, with the decision

    def arm(self, point, rect=None, on_hit=None):
        ok = self.start()
        pin = None
        if ok and self.check_windows:
            for _ in range(3):  # bounded identity acquisition; unresolved identity must NOT arm blindly
                pin = self.window_identity_at(point)
                if pin is not None and pin[0] is not None: break
                pin = None; time.sleep(0.1)
            if pin is None: return False
        with self._lock:
            self._point, self._rect, self._cb, self._pin = point, rect, on_hit, pin
        return ok

    # --- window identity (X11): overlap or focus change must not count as a target click ---
    def _top(self, d, w):
        root = d.screen().root
        try:
            while True:
                q = w.query_tree()
                if q.parent == root or q.parent == 0: return w.id
                w = q.parent
        except Exception:
            return None

    def window_identity_at(self, pt, d=None):
        with self._gd_lock:
            return self._window_identity_at(pt, d)

    def _window_identity_at(self, pt, d=None):
        """(topmost mapped top-level at pt, top-level holding input focus). Own overlay windows are ignored via self.ignore_ids/names."""
        try:
            from Xlib import X
            d = d or self._guard_display(); root = d.screen().root
            top = None
            for w in reversed(root.query_tree().children):
                try:
                    a = w.get_attributes()
                    if a.map_state != X.IsViewable or a.override_redirect and self._is_ignored(w): continue
                    if self._is_ignored(w): continue
                    g = w.get_geometry()
                    if g.x <= pt[0] < g.x + g.width and g.y <= pt[1] < g.y + g.height:
                        top = w.id; break
                except Exception: continue
            f = d.get_input_focus().focus
            foc = self._top(d, f) if hasattr(f, "query_tree") else None
            return (top, foc)
        except Exception:
            return None

    def _guard_display(self):
        """Own X connection for the guard poller so it never shares a Display with the detector thread's blocking event loop."""
        if getattr(self, '_gd', None) is None:
            from Xlib import display as _xd
            self._gd = _xd.Display()
        return self._gd

    def pin_state(self, point=None, pin=None):
        """'ok' | 'covered' (another window is now topmost at the target point) | 'focus_other' (input focus moved to a third window) | 'unknown'.
        Compares against the identity pinned at arm time. Used to hide the pointer while it would mislead (a covering window / another app in front)."""
        with self._lock:
            pt = point or self._point; pn = pin or self._pin
        if pt is None or pn is None: return "unknown"
        cur = self.window_identity_at(pt)
        if cur is None: return "unknown"
        if cur[0] != pn[0]: return "covered"
        if cur[1] not in (pn[1], pn[0]): return "focus_other"
        return "ok"

    def app_identity_of_window(self, win_id):
        """(lowercase WM_CLASS class name, 'instance.class' app id) of a top-level X window, or (None, None). Linux mapping of NSRunningApplication localizedName / bundleIdentifier."""
        try:
            d = self._guard_display(); w = d.create_resource_object("window", win_id); c = w.get_wm_class()
            if not c: return (None, None)
            return (c[1].lower(), (c[0] + "." + c[1]).lower())
        except Exception: return (None, None)

    def _is_ignored(self, w):
        try:
            cls = w.get_wm_class() or ()
            return any(c in self.ignore_classes for c in cls)
        except Exception:
            return False

    def disarm(self):
        with self._lock:
            self._point = self._rect = self._cb = None

    def armed(self):
        with self._lock:
            return self._point is not None or self._rect is not None

    def hit_test(self, x, y):
        with self._lock:
            return self._hit(x, y)

    def _hit(self, x, y):
        if self._rect is not None:
            l, t, w, h = self._rect
            i = RECT_INFLATE
            return (l - i) <= x <= (l + w + i) and (t - i) <= y <= (t + h + i)
        if self._point is not None:
            px, py = self._point
            return ((x - px) ** 2 + (y - py) ** 2) ** 0.5 <= POINT_TOL
        return False

    def handle_press(self, x, y):
        """Process one left-button press. Returns 'hit','miss','ignored'."""
        cb = None
        with self._lock:
            if self._point is None and self._rect is None:
                self.presses.append((x, y, "ignored-disarmed")); return "ignored"
            now = self._clock()
            if self._last_hit is not None and now - self._last_hit < GRACE_S:
                self.presses.append((x, y, "ignored-grace")); return "ignored"
            if not self._hit(x, y):
                self.presses.append((x, y, "miss", self._rect, self._point)); return "miss"
            if self._pin is not None and self.check_windows:
                self._lock.release()
                try: now_id = self.window_identity_at((x, y))
                finally: self._lock.acquire()
                # window under the pointer must be the pinned one; focus may stay or move TO the pinned window (a click focuses it), never to another window
                if now_id is not None and (now_id[0] != self._pin[0] or now_id[1] not in (self._pin[1], self._pin[0])):
                    self.presses.append((x, y, "miss-window-changed", {"pinned": self._pin, "now": now_id})); return "miss"
            self.presses.append((x, y, "hit", self._rect, self._point))
            self._last_hit = now
            cb = self._cb
            # one-shot: consumer re-arms for the next step
            self._point = self._rect = self._cb = None
        if cb:
            cb()
        return "hit"

    def start(self):
        if self._thread and self._thread.is_alive():
            return self.available
        try:
            from Xlib import display
            d = display.Display()
            d.screen().root.query_pointer()
            self._d = d  # keep open: closing the last client resets bare Xvfb
        except Exception:
            self.available = False
            return False
        self.available = True
        self._stop.clear()
        self.thread_starts += 1
        self._thread = threading.Thread(target=self._run_guarded, daemon=True)
        self._thread.start()
        t0 = time.time()
        while self.backend is None and time.time() - t0 < 1.5:
            time.sleep(0.01)
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run_guarded(self):
        try:
            self._run()
        except BaseException as e:
            self.errors.append("thread died: " + type(e).__name__)
            self.backend = None
            self.available = False

    def _run(self):
        from Xlib import X
        d = self._d
        root = d.screen().root
        mode = "poll"
        try:
            from Xlib.ext import xinput
            if os.environ.get("TIPTOUR_CLICK_BACKEND") != "poll" and d.has_extension("XInputExtension"):
                d.xinput_query_version()
                root.xinput_select_events([(xinput.AllMasterDevices, xinput.RawButtonPressMask)])
                d.flush()
                mode = "xi2-raw"
        except Exception:
            mode = "poll"
        self.backend = mode
        if mode == "xi2-raw":
            # event hook: raw button press (listen-only, sees every client's
            # clicks, cannot swallow them). Short clicks are not missed.
            while not self._stop.is_set():
                if d.pending_events():
                    ev = d.next_event()
                    try:
                        # python-xlib leaves raw events unparsed: data =
                        # deviceid(2) time(4) detail(4) sourceid(2) ...
                        if (getattr(ev, "evtype", None) == xinput.RawButtonPress
                                and int.from_bytes(bytes(ev.data)[6:10], "little") == 1):
                            q = root.query_pointer()
                            self.handle_press(q.root_x, q.root_y)
                    except Exception as e:
                        self.errors.append("xi2 event: " + type(e).__name__)
                else:
                    time.sleep(0.004)
            d.close()
            return
        down = bool(root.query_pointer().mask & X.Button1Mask)
        while not self._stop.is_set():
            q = root.query_pointer()
            now_down = bool(q.mask & X.Button1Mask)
            if now_down and not down:
                self.handle_press(q.root_x, q.root_y)
            down = now_down
            time.sleep(self._poll)
        d.close()


def guarded_callback(plan_tok, token, on_valid, on_stale):
    """Wrap a hit callback so a press that is delivered after the plan was replaced is ignored (Mac: operationToken == currentOperationToken)."""
    def cb():
        if token != plan_tok["n"]:
            on_stale()
        else:
            on_valid()
    return cb
