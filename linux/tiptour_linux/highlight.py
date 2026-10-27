"""Linux (X11 only) counterpart of GlobalHighlightShortcutMonitor + FocusHighlightContext.
Hold Control+Shift (no Option/Super) and move the mouse to paint a freeform trail. Listen-only: polls XQueryPointer,
never grabs keys or pointer. Release commits a context (>=2 points, 12px padded bbox, min 4x4).
Option(Alt) present at release = Ask-harness chord provenance: the trail stays LOCAL and is never handed to a provider.
Wayland does not allow this global monitoring; this module refuses to start there."""
import os, sys, subprocess, threading, time
from Xlib import X, display as xdisplay

CTRL, SHIFT, ALT, SUPER = X.ControlMask, X.ShiftMask, X.Mod1Mask, X.Mod4Mask

def held(mask): return bool(mask & CTRL) and bool(mask & SHIFT) and not (mask & ALT) and not (mask & SUPER)
def ask_chord(mask): return bool(mask & CTRL) and bool(mask & SHIFT) and bool(mask & ALT)

class HighlightMonitor:
    def __init__(self, on_begin=None, on_move=None, on_commit=None, hz=60):
        if os.environ.get("XDG_SESSION_TYPE") == "wayland" and not os.environ.get("DISPLAY"): raise RuntimeError("X11 required")
        self.d = xdisplay.Display(); self.root = self.d.screen().root
        self.on_begin, self.on_move, self.on_commit, self.dt = on_begin, on_move, on_commit, 1.0 / hz
        self.points, self.active, self.stop_flag = [], False, False

    def start(self): self.t = threading.Thread(target=self._run, daemon=True); self.t.start()
    def stop(self): self.stop_flag = True

    def _run(self):
        while not self.stop_flag:
            q = self.root.query_pointer(); p = (q.root_x, q.root_y); h = held(q.mask)
            if h and not self.active:
                self.active, self.points = True, [p]
                if self.on_begin: self.on_begin(p)
            elif h and self.active:
                if not self.points or ((p[0] - self.points[-1][0]) ** 2 + (p[1] - self.points[-1][1]) ** 2) ** 0.5 >= 3:  # >=3px spacing like Mac
                    self.points.append(p)
                    if self.on_move: self.on_move(p)
            elif self.active and not h:
                self.active = False; pts, self.points = self.points, []
                if self.on_commit: self.on_commit(pts, ask_chord(q.mask))
            time.sleep(self.dt)

def build_context(points, window_probe=None, element_probe=None, probe_timeout=6, selection_probe=None):
    """FocusHighlightContext analog. None when <2 points or bbox <=4px."""
    if len(points) < 2: return None
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    rect = (min(xs) - 12, min(ys) - 12, max(xs) - min(xs) + 24, max(ys) - min(ys) + 24)
    if rect[2] <= 4 or rect[3] <= 4: return None
    ctx = {"points": points, "rect": rect, "last_point": points[-1]}
    ctx["window"] = window_probe(points) if window_probe else None
    ctx["element"], ctx["text_selection"], ctx["atspi_status"] = None, None, "not requested"
    if element_probe:
        # the window was captured above (commit time). The probe is bounded; an expired probe is reported as UNAVAILABLE, never as "nothing selected".
        pid = (ctx.get("window") or {}).get("pid")
        try: pid_ok = int(pid or 0) > 0
        except (TypeError, ValueError): pid_ok = False
        if not pid_ok:  # no window under the highlight, or its pid is unknown/0: the freshness gates cannot run, so say UNAVAILABLE rather than probe unscoped
            ctx["atspi_status"] = "unavailable: no window pid for the highlighted area"
            return ctx
        try:
            ctx["element"], ctx["text_selection"] = element_probe(rect, points, hint_pid=pid, timeout=probe_timeout); ctx["atspi_status"] = "ok"
        except TimeoutError:
            ctx["atspi_status"] = "unavailable: accessibility probe exceeded %ds" % probe_timeout
        except Exception as e:
            ctx["atspi_status"] = "unavailable: probe error %s" % type(e).__name__
    if selection_probe and not ctx.get("text_selection"):  # browser DOM selection fallback (bound tab, provenance in text_selection["source"]); never overrides an AT-SPI selection
        try:
            sel, st = selection_probe(rect, (ctx.get("window") or {}).get("pid"))
            ctx["dom_selection_status"] = st
            if sel: ctx["text_selection"] = sel
        except Exception as e:
            ctx["dom_selection_status"] = "unavailable: %s" % type(e).__name__
    # Capture native selected-range identity only for the actual focused field in the painted window.
    if ctx.get("text_selection") and ctx.get("window"):
        try:
            from . import atspi_resolver as ar
            wd = ctx["window"]; f = ar._sub(["--focus", wd.get("title") or ""], probe_timeout).get("focus")
            if f and f.get("editable") and not f.get("password") and f.get("selection") and f["identity"]["pid"] == int(wd["pid"]):
                r0, r1 = f["selection"]
                if f.get("text") is not None and f["text"][r0:r1] == ctx["text_selection"].get("text"):
                    ctx["native_range"] = {"identity": f["identity"], "text": f["text"], "selection": f["selection"], "xwindow": wd["id"]}
        except Exception: pass  # unavailable remains explicit; execution refuses a missing native range
    return ctx

def xdotool_window_at(points):
    """Topmost client window (EWMH _NET_CLIENT_LIST_STACKING) whose frame contains the last painted point."""
    def xo(*a):
        try: return subprocess.run(["xdotool", *a], capture_output=True, text=True, timeout=2).stdout.strip()
        except Exception: return ""
    d = xdisplay.Display(); root = d.screen().root; px, py = points[-1]
    prop = root.get_full_property(d.intern_atom("_NET_CLIENT_LIST_STACKING"), X.AnyPropertyType)
    if not prop: prop = root.get_full_property(d.intern_atom("_NET_CLIENT_LIST"), X.AnyPropertyType)  # no stacking order from this WM: fallback below
    ids = list(prop.value) if prop else []
    act = root.get_full_property(d.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
    if act and act.value and act.value[0] in ids: ids = [i for i in ids if i != act.value[0]] + [act.value[0]]  # active window wins overlaps (true z-order unknown without _NET_CLIENT_LIST_STACKING)
    for w in reversed(ids):
        g = dict(l.split("=") for l in xo("getwindowgeometry", "--shell", str(w)).splitlines() if "=" in l)
        x, y, ww, hh = (int(g.get(k, 0)) for k in ("X", "Y", "WIDTH", "HEIGHT"))
        try:
            client = d.create_resource_object('window', int(w)); geom = client.get_geometry(); absolute = root.translate_coords(client, 0, 0)
            x, y, ww, hh = absolute.x, absolute.y, geom.width, geom.height
        except Exception: continue  # no trustworthy screen coordinates means no window binding
        if x <= px <= x + ww and y <= py <= y + hh and ww > 0:
            return {"id": str(w), "title": xo("getwindowname", str(w)), "pid": xo("getwindowpid", str(w)), "rect": (x, y, ww, hh)}
    return None

def prompt(ctx, ack=False):
    """Prompt text mirroring CompanionManager.focusHighlightContextPrompt (same wording where the concept exists)."""
    x, y, w, h = ctx["rect"]
    lines = ["user focus highlight context:",
             'the user just painted a freeform highlight region. treat phrases like "this", "this area", "this line", "that text", "rewrite this", or "change this" as referring to this highlighted region.',
             "global screen rect (x11 pixels): x=%d, y=%d, width=%d, height=%d." % (x, y, w, h),
             "current hover / last painted point: x=%d, y=%d." % ctx["last_point"]]
    try:
        sc = xdisplay.Display().screen(); SW, SH = sc.width_in_pixels, sc.height_in_pixels
        lines.append("same region in the 0-1000 normalized coordinates you must use for point_2d / box_2d (a pixel value is NOT a normalized value): box_2d=[%d, %d, %d, %d] (ymin, xmin, ymax, xmax)." % (round(y * 1000 / SH), round(x * 1000 / SW), round((y + h) * 1000 / SH), round((x + w) * 1000 / SW)))
    except Exception: pass
    wd = ctx.get("window")
    if wd:
        lines.append('hovered app/window target: window_title="%s", pid=%s, window_rect x=%d, y=%d, width=%d, height=%d.' % ((wd["title"] or "")[:120], wd["pid"] or "unknown", *wd["rect"]))
        lines.append("for this request, keep actions inside that hovered app/window unless the user explicitly asks to switch apps.")
    el = ctx.get("element")
    if el:
        lines.append('highlight-intersected accessibility element: role="%s", title="%s", element_rect x=%d, y=%d, width=%d, height=%d.' % (el.get("role", "unknown"), (el.get("label") or "")[:180], *[int(v) for v in el["rect"]]))
        lines.append("prefer this intersected element over any stale focused element when deciding what text area or control the highlight refers to.")
    st = ctx.get("atspi_status", "")
    if st.startswith("unavailable"):
        lines.append("accessibility metadata for this highlight is %s. Do not infer the element or any selected text from its absence; rely on the screenshot and ask the user if the target is unclear." % st)
    ts = ctx.get("text_selection")
    if ts and ts.get("source") == "cdp_dom":
        lines.append('browser page text selection (read from the focused tab\'s DOM; its on-screen rect intersects the highlight): "%s".' % ts["text"][:400].replace('"', "'"))
    elif ts:
        lines.append('accessibility text selection intersecting the highlight (app=%s, role=%s): "%s".' % (ts.get("app"), ts.get("role"), ts["text"][:400].replace('"', "'")))
    lines.append("when editing, prefer the accessibility element or text field intersecting this region; choose exactly one next action.")
    if ack: lines.append("Briefly tell the user what the highlighted region appears to refer to. Do not take any desktop action yet.")
    return "\n".join(lines)


import re as _re
_REF = _re.compile(r"\b(highlight(ed)?|this (area|region|part|section|spot)|these|in here|selected|painted|marked)\b")

def refers_to_highlight(utterance):
    return bool(_re.search(_REF, (utterance or "").lower()))

def outside_scope(utterance, region, point, pad=12):
    """True when the user's request refers to the highlight and the point lies outside the (padded) region."""
    if not region or not refers_to_highlight(utterance): return False
    x, y, w, h = region
    return not (x - pad <= point[0] <= x + w + pad and y - pad <= point[1] <= y + h + pad)


def atspi_probe(rect, points=None, hint_pid=None, timeout=6):
    from . import atspi_resolver
    r = atspi_resolver.probe(rect, hint_pid=hint_pid, timeout=timeout)
    if os.environ.get('TIPTOUR_DEBUG_ATSPI'): print('atspi probe (DEBUG ONLY, may contain labels/selected text):', rect, '->', r, file=sys.stderr, flush=True)
    return r


def outside_window(utterance, ctx, point):
    """Highlight-scoped requests stay inside the app window the highlight was painted over (ctx["window"]["rect"])."""
    w = (ctx or {}).get("window")
    if not w or not w.get("rect") or not refers_to_highlight(utterance): return False
    x, y, ww, hh = w["rect"]
    return not (x <= point[0] <= x + ww and y <= point[1] <= y + hh)


_NOACT_NEG = _re.compile(r"\b(do not|don't|dont|never|no need to|without)\b[^.?!]{0,25}\b(point|click|act|move|touch|press|type|do anything|take (any )?action)\b|\bno action\b")
_NOACT_ONLY = _re.compile(r"\b(just|only) (tell|answer|say|read|quote|describe)\b")
_NEGATED_ONLY = _re.compile(r"\b(do not|don't|dont|never)\s+$")
_ACT_VERB = _re.compile(r"\b(point|show me|where|click|press|tap|open|go to|take me|find|locate|type|change|rewrite|fix|edit|delete|move|scroll|drag|fill|submit|send|copy|paste|highlight where)\b")

_Q_TEXT = _re.compile(r"\b(text|words?|says?|written|quote|read|selected|describe|explain|summari[sz]e)\b")

def no_action_requested(utterance):
    """True when the USER's words ask for an answer only (explicit 'do not point/click', or a text/quote/describe question
    with no action verb). Such requests never get a cursor, click, right-click or workflow step, whatever the model calls."""
    t = (utterance or "").lower().strip()
    if not t: return False
    if _re.search(_NOACT_NEG, t): return True
    for match in _NOACT_ONLY.finditer(t):
        # A negated answer-only phrase is not itself a request for an answer.
        # Still require an action elsewhere, and never override explicit action prohibitions.
        if not (_NEGATED_ONLY.search(t[:match.start()]) and _ACT_VERB.search(t[:match.start()] + t[match.end():])):
            return True
    first = t.split()[0] if t.split() else ""
    question = first in ("what", "which", "quote", "read", "tell", "describe", "explain", "summarize", "summarise") or t.endswith("?") and first in ("is", "are", "does", "do")
    return bool(question and _re.search(_Q_TEXT, t) and not _re.search(_ACT_VERB, t))


def action_matches_intent(step_type, utterance):
    """--act only: the executed action must be asked for in the USER's words. rightClick needs an explicit right-click/context-menu request,
    doubleClick an explicit double-click, click an explicit click/press/tap/select/choose/open/submit/toggle request. Bounded regex guard, not semantic trust."""
    t = (utterance or "").lower()
    if no_action_requested(t): return False
    if step_type == "rightClick": return bool(_re.search(r"right[- ]?click|context menu", t))
    if step_type == "doubleClick": return bool(_re.search(r"double[- ]?click", t))
    return bool(_re.search(r"\b(click|press|tap|select|choose|check|uncheck|toggle|open|submit|hit|push|activate)\b", t))


def action_type_matches_intent(step_type, utterance):
    """--act only, for the non-click action step types: the user's own words must ask for THAT kind of action. Bounded regex guard, not semantic trust."""
    t = (utterance or "").lower()
    if step_type in ("click", "doubleClick", "rightClick"): return action_matches_intent(step_type, utterance)
    if no_action_requested(t): return False
    pats = {"openApp": r"\b(open|launch|start|run|switch to)\b", "openURL": r"\b(open|go to|visit|navigate|browse|load|show me)\b|https?://|www\.", "keyboardShortcut": r"\b(press|hit|use|shortcut|hotkey|key|keys|ctrl|control|cmd|command|alt|shift|save|copy|paste|undo|redo|select all|new|close)\b",
            "setValue": r"\b(set (?:the )?value|replace (?:the )?(?:whole |entire )?(?:field|value)|fill)\b", "pressKey": r"\b(press|hit|key|enter|return|escape|esc|tab|backspace|delete|space|page ?up|page ?down|arrow)\b", "type": r"\b(type|write|enter|input|fill|put|insert|dictate)\b", "scroll": r"\b(scroll|page down|page up|move down|move up|go down|go up|down|up)\b"}
    return bool(step_type in pats and _re.search(pats[step_type], t))


def point_authorized(utterance):
    """The user's words ask to be shown/pointed at something (not an answer-only request). Bounded regex."""
    t = (utterance or "").lower()
    return (not no_action_requested(t)) and bool(_re.search(r"\b(point|show|where|find|locate|which)\b", t))

def inside_intersection_point(region, elem_rect, min_side=4):
    """Centre of (region ∩ element) in screen px, or None when they do not overlap by at least min_side px each way."""
    rx, ry, rw, rh = region; ex, ey, ew, eh = elem_rect
    x0, y0, x1, y1 = max(rx, ex), max(ry, ey), min(rx + rw, ex + ew), min(ry + rh, ey + eh)
    if x1 - x0 < min_side or y1 - y0 < min_side: return None
    return (round((x0 + x1) / 2), round((y0 + y1) / 2))


def suppressed_payload(text, ctx):
    """toolResponse for an answer-only request whose tool call was suppressed. Selected text only when actually present; the source label follows the real source."""
    ctx = ctx or {}; ts = ctx.get("text_selection") or {}
    r = {"ok": True, "status": "suppressed_no_action", "user_question": text,
         "instruction": "The user asked for an answer only. No cursor was placed and nothing was clicked. Answer the user's question now in words, without any tool call."}
    if ts.get("text"):
        dom = ts.get("source") == "cdp_dom"
        r["selected_text"] = ts["text"]
        r["selected_text_source"] = ("browser page DOM selection in the focused tab (at least part of it overlaps the user's highlight; the whole selection up to 600 chars is shown)" if dom
                                     else "AT-SPI accessibility text selection intersecting the user's highlight")
    else:
        notes = [x for x in (ctx.get("atspi_status"), ctx.get("dom_selection_status")) if x]
        r["selected_text_note"] = "No selected text was read (%s). Say so instead of guessing." % "; ".join(notes or ["no selection probe ran"])
    return r
