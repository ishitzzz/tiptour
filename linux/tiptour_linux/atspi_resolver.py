"""AT-SPI accessibility resolver: Linux counterpart of AccessibilityTreeResolver.swift.
Finds visible, showing controls by label and returns screen rects. Requires the
AT-SPI typelib (gir1.2-atspi-2.0) and an accessibility bus; apps must expose a11y."""
import os, sys
import threading
# Native libatspi is loaded ONLY in the child subprocess (python -m tiptour_linux.atspi_resolver ...) by default: a native crash (heap corruption was
# observed in-process, exit 134) then kills a bounded child, not the app. TIPTOUR_ATSPI_ISOLATED=0 restores the old in-process native reader (unsafe, test only).
ISOLATED = os.environ.get('TIPTOUR_ATSPI_ISOLATED', '1') != '0'
_NATIVE = (not ISOLATED) or __name__ == "__main__"
Atspi = None
if _NATIVE:
    import gi
    extra = os.environ.get("TIPTOUR_GIR_PATH")
    if extra:
        os.environ["GI_TYPELIB_PATH"] = extra + ":" + os.environ.get("GI_TYPELIB_PATH", "")
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    Atspi.init()
_LOCK = threading.RLock()
import queue, time as _time

class _Worker:
    """ONE dedicated AT-SPI thread. All libatspi/GDBus work runs here (serialized, no per-call executors).
    Bounded: at most one pending request (a newer one supersedes the older still-queued one); a request whose deadline passed before
    it started is dropped without running. An in-flight synchronous GDBus call cannot be cancelled from Python; only walk budgets
    stop work between calls, so a caller timeout means 'unavailable', not 'cancelled'."""
    def __init__(self):
        self.q = queue.Queue(); self.lock = threading.Lock(); self.pending = None; self.stats = []  # count/ms-only call trace (no labels), bounded
        threading.Thread(target=self._loop, daemon=True, name="atspi-worker").start()
    def _loop(self):
        while True:
            self.q.get()
            with self.lock: item, self.pending = self.pending, None
            if item is None: continue
            fn, args, deadline, box, ev = item[:5]
            if _time.monotonic() > deadline: box["err"] = TimeoutError("expired before start"); self._st(fn, 0, 0, 'expired_before_start'); ev.set(); continue
            _t = _time.monotonic()
            try: box["val"] = fn(*args)
            except Exception as e: box["err"] = e
            self._st(fn, 0, _time.monotonic() - _t, type(box.get('err')).__name__ if 'err' in box else 'ok', len(box.get('val') or []) if isinstance(box.get('val'), list) else None)
            if os.environ.get('TIPTOUR_DEBUG_ATSPI_TIMING'): print('atspi-worker', fn.__name__, 'took %.2fs' % (_time.monotonic() - _t), 'err=%s' % type(box.get('err')).__name__ if 'err' in box else 'ok', 'val=%s' % (box.get('val') if fn.__name__ == 'ready' else '-'), flush=True)
            ev.set()
    def _st(self, fn, q_s, run_s, res, n=None):
        self.stats.append({'t': round(_time.time(), 2), 'fn': fn.__name__, 'run_ms': int(run_s * 1000), 'res': res, 'n': n}); del self.stats[:-300]
    def call(self, fn, args, timeout, low=False):
        # low = background warm-up: never supersedes a pending REAL request (it yields instead); real requests supersede anything pending
        box = {}; ev = threading.Event(); deadline = _time.monotonic() + timeout
        with self.lock:
            if low and self.pending is not None: raise RuntimeError("busy: real request pending")
            if self.pending is not None: self.pending[3]["err"] = RuntimeError("superseded"); self.pending[4].set(); self.stats.append({'t': round(_time.time(), 2), 'fn': getattr(self.pending[0], '__name__', '?'), 'res': 'superseded_by_' + getattr(fn, '__name__', '?')})
            self.pending = (fn, args, deadline, box, ev) + (low,)
        self.q.put(1)
        if not ev.wait(timeout): self.stats.append({'t': round(_time.time(), 2), 'fn': getattr(fn, '__name__', '?'), 'res': 'caller_timeout_%ss' % timeout}); raise TimeoutError("atspi call exceeded %ss" % timeout)
        if "err" in box: raise box["err"]
        return box["val"]
_W = _Worker() if _NATIVE and not (__name__ == '__main__') else None  # in-process worker exists only in the unsafe non-isolated mode

CLICKABLE = {"push button", "toggle button", "menu item", "check box", "radio button", "link", "page tab", "list item", "text", "entry"}

def walk(node, depth=0, out=None):
    out = [] if out is None else out
    try: n = node.get_child_count()
    except Exception: return out
    for i in range(n):
        try: ch = node.get_child_at_index(i)
        except Exception: continue
        if ch is None: continue
        try:
            st = ch.get_state_set()
            if st.contains(Atspi.StateType.SHOWING) and st.contains(Atspi.StateType.VISIBLE):
                ext = ch.get_extents(Atspi.CoordType.SCREEN)
                role = ch.get_role_name()
                if role in CLICKABLE and ext.width > 0 and ext.height > 0:
                    out.append({"label": ch.get_name() or "", "role": role, "rect": [ext.x, ext.y, ext.width, ext.height],
                                "app": node.get_application().get_name() if depth == 0 else None})
        except Exception: pass
        walk(ch, depth + 1, out)
    return out

def _all_targets():
    desk = Atspi.get_desktop(0); res = []
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if _is_self(app): continue
        for t in walk(app):
            t["app"] = app.get_name(); res.append(t)
    return res

def _app_targets(name):
    desk = Atspi.get_desktop(0); res = []
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if _is_self(app) or (app.get_name() or "") != name: continue
        for t in walk(app):
            t["app"] = name; res.append(t)
    return res

def app_targets(name, timeout=4):
    """Visible clickable controls of ONE app (the child filters; the parent never walks)."""
    if ISOLATED: return _sub(["--targets", "--app", name], timeout)["targets"]
    return _W.call(_app_targets, (name,), timeout)

def all_targets(timeout=6):
    if ISOLATED: return _sub(["--targets"], timeout)["targets"]
    return _W.call(_all_targets, (), timeout)

def resolve(label):
    l = label.strip().lower()
    ts = all_targets()
    c = [t for t in ts if t["label"].strip().lower() == l] or [t for t in ts if l and l in t["label"].lower()]
    return c



def _inter(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]); h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0

def _selection_of(node):
    try:
        ti = node.get_text_iface()
        if ti is None: return None
        n = Atspi.Text.get_n_selections(ti)
        parts = []
        for i in range(n):
            r = Atspi.Text.get_selection(ti, i)
            s = Atspi.Text.get_text(ti, r.start_offset, r.end_offset)
            s = (s or '').replace('\ufffc', '')  # embedded-object placeholder (container selecting children); real text lives in a descendant
            if s.strip(): parts.append(s.strip())
        return " ".join(parts)[:600] if parts else None
    except Exception:
        return None

import re as _re
_re_browser = _re.compile(r'chrome|chromium|firefox|brave|edge|vivaldi|opera', _re.I)

def _is_self(app):
    try: return app.get_process_id() in (os.getpid(), int(os.environ.get('TIPTOUR_PARENT_PID', '0') or 0))  # child walks must also skip the PARENT app's own windows
    except Exception: return False

def _pid(app):
    try: return app.get_process_id()
    except Exception: return -1

def ready(wall_s=3.0):
    """True when a non-WM, non-self application exposes a populated 'document web' node (Chrome builds the page tree lazily after the first AT-SPI query)."""
    _end = _time.monotonic() + wall_s
    def has_doc(node, depth):
        if _time.monotonic() > _end: return False
        try: n = node.get_child_count()
        except Exception: return False
        for k in range(n):
            try: ch = node.get_child_at_index(k)
            except Exception: continue
            if ch is None: continue
            try:
                if ch.get_role_name() == "document web" and ch.get_child_count() > 0: return True
            except Exception: pass
            if depth < 6 and has_doc(ch, depth + 1): return True
        return False
    desk = Atspi.get_desktop(0)
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if app.get_name() == "xfwm4" or _is_self(app): continue
        if has_doc(app, 0): return True
    return False

def ready_bounded(timeout=3):
    try:
        if ISOLATED: return bool(_sub(["--ready"], timeout).get("ready"))
        return _W.call(ready, (), timeout, True)
    except Exception: return False

def probe(rect, hint_pid=None, timeout=6, max_nodes=4000, low=False):
    """Bounded probe on the AT-SPI worker. Raises TimeoutError when unavailable within timeout (caller must report UNAVAILABLE, not 'none')."""
    if ISOLATED: return probe_isolated(rect, hint_pid, timeout)
    return _W.call(_probe, (rect, hint_pid, max_nodes, _time.monotonic() + max(1.0, timeout - 0.5)), timeout, low)

def _probe(rect, hint_pid=None, max_nodes=4000, wall=None):
    """-> (element, selection). element = smallest showing control/text node intersecting the highlight (most overlap wins ties);
    selection = {text, app, role, rect} for a node intersecting the region that reports a non-empty AT-SPI text selection.
    Either may be None (app exposes no a11y, or nothing intersects)."""
    desk = Atspi.get_desktop(0)
    if os.environ.get('TIPTOUR_DEBUG_ATSPI'): print('atspi desktop apps:', [desk.get_child_at_index(i).get_name() for i in range(desk.get_child_count())], file=sys.stderr, flush=True)
    best = None; sel = None; seen = [0]; trunc = [False]; doc_seen = [False]
    def rec(node, app):
        nonlocal best, sel
        try: n = node.get_child_count()
        except Exception: return
        for i in range(n):
            if seen[0] > max_nodes or (wall and _time.monotonic() > wall): trunc[0] = True; return
            try: ch = node.get_child_at_index(i)
            except Exception: continue
            if ch is None: continue
            seen[0] += 1
            skip = False
            try:
                st = ch.get_state_set()
                if st.contains(Atspi.StateType.SHOWING) and st.contains(Atspi.StateType.VISIBLE):
                    e = ch.get_extents(Atspi.CoordType.SCREEN); r = [e.x, e.y, e.width, e.height]
                    if r[2] > 0 and r[3] > 0 and not _inter(r, rect): skip = True  # a sized container that misses the highlight cannot hold intersecting content: prune its subtree
                    if r[2] > 0 and r[3] > 0 and _inter(r, rect):
                        role = ch.get_role_name()
                        if role == 'document web': doc_seen[0] = True
                        if sel is None:
                            t = _selection_of(ch)
                            if t: sel = {"text": t, "app": app, "role": role, "rect": r}
                        if role in CLICKABLE or role in ("check box", "combo box", "switch", "slider", "spin button", "password text"):
                            key = (_inter(r, rect) / float(r[2] * r[3]), -r[2] * r[3])  # mostly-inside, then smallest
                            if best is None or key > best[0]: best = (key, {"label": ch.get_name() or "", "role": role, "rect": r, "app": app})
            except Exception: pass
            if not skip: rec(ch, app)
    apps = [desk.get_child_at_index(i) for i in range(desk.get_child_count())]
    if hint_pid:  # the window the highlight was painted over goes first
        apps.sort(key=lambda ap: 0 if _pid(ap) == int(hint_pid) else 1)
    hint_walked = False; hint_browser = False
    if hint_pid and not any(_pid(ap) == int(hint_pid) for ap in apps):
        raise TimeoutError("hint window pid %s is not in the AT-SPI registry (stale or not exported yet)" % hint_pid)
    for app in apps:
        if _is_self(app): continue  # never walk our own overlay windows (served by our own main loop; slow and irrelevant)
        try:
            if hint_pid and _pid(app) == int(hint_pid):
                if app.get_child_count() == 0: raise TimeoutError("hint app exports an empty tree (not ready)")
                hint_walked = True; hint_browser = bool(_re_browser.search(app.get_name() or ''))
            rec(app, app.get_name())
        except TimeoutError: raise
        except Exception: pass
        if os.environ.get('TIPTOUR_DEBUG_ATSPI'): print('atspi walked', app.get_name(), 'nodes so far', seen[0], 'best', bool(best), file=sys.stderr, flush=True)
    if hint_browser and not doc_seen[0] and best is None and sel is None: raise TimeoutError("browser page document not exported yet (empty is not 'nothing here')")
    if hint_pid and not hint_walked and best is None and sel is None: raise TimeoutError("hint app tree was not walked")
    if trunc[0] and best is None and sel is None: raise TimeoutError("walk budget exceeded before the region was covered")  # unavailable, not 'none'
    return (best[1] if best else None), sel


# ---- process-isolated API (preferred): fresh libatspi state per call, genuinely cancellable (kill on timeout) ----
import json as _json, subprocess as _sp

SUB_STATS = []  # count/ms/rc only (no labels, no stderr), bounded
_SUB_SEM = threading.Semaphore(1)  # one native child at a time: backpressure instead of piling up concurrent walkers

def sub_stats(): return list(SUB_STATS)

def _sub(args, timeout):
    t0 = _time.monotonic(); kind = str(args[0]); rec = {"t": round(_time.time(), 2), "kind": kind}
    if not _SUB_SEM.acquire(timeout=max(0.1, timeout)):
        rec.update(res="busy_timeout", wait_ms=int((_time.monotonic() - t0) * 1000)); SUB_STATS.append(rec); del SUB_STATS[:-300]
        raise TimeoutError("atspi child busy (another native read in flight)")
    try:
        left = max(0.5, timeout - (_time.monotonic() - t0)); t1 = _time.monotonic(); rec["wait_ms"] = int((t1 - t0) * 1000)
        env = dict(os.environ); env["TIPTOUR_PARENT_PID"] = str(os.getpid()); env["TIPTOUR_ATSPI_ISOLATED"] = "1"
        p = _sp.Popen([sys.executable, "-m", "tiptour_linux.atspi_resolver"] + [str(a) for a in args], stdout=_sp.PIPE, stderr=_sp.PIPE if os.environ.get('TIPTOUR_DEBUG_ATSPI') else _sp.DEVNULL, env=env,
                      cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), start_new_session=True)
        try: out, _ = p.communicate(timeout=left)
        except _sp.TimeoutExpired:
            try: os.killpg(p.pid, 9)
            except Exception: p.kill()
            try: p.communicate(timeout=2)
            except Exception: pass
            p.wait(); rec.update(res="killed_timeout", rc=p.returncode, run_ms=int((_time.monotonic() - t1) * 1000)); raise TimeoutError("atspi subprocess exceeded %ss (killed)" % timeout)
        rec.update(rc=p.returncode, run_ms=int((_time.monotonic() - t1) * 1000))
        if p.returncode != 0 or not out.strip(): rec["res"] = "child_failed"; raise RuntimeError("atspi subprocess failed (rc=%s, no output)" % p.returncode)
        d = _json.loads(out.decode())
        if "error" in d:
            rec["res"] = "child_error"; raise TimeoutError(d["error"]) if d.get("unavailable") else RuntimeError(d["error"])
        rec["res"] = "ok"; rec["n"] = len(d.get("targets", [])) if "targets" in d else None
        return d
    finally:
        SUB_STATS.append(rec); del SUB_STATS[:-300]; _SUB_SEM.release()

FP_MAX_NODES = int(os.environ.get("TIPTOUR_FP_NODES", "400")); FP_MAX_DEPTH = int(os.environ.get("TIPTOUR_FP_DEPTH", "40"))  # Mac: 120 / 8. Measured: on Chromium the page controls start at node 136 and deeper than depth 8, so the Mac caps cannot see the page (see workflow.py)
FP_BUDGET_S = float(os.environ.get("TIPTOUR_FP_BUDGET_S", "0.15"))  # Mac default 0.15s (measured 229-node walk ~0.08s fits); a walk cut by the budget is reported truncated and treated as a FAILED read (never compared)

def _fp_value(ch):
    """Mac: String values as-is, NSNumber stringValue, else ''; truncated to 120 chars. AT-SPI: Text interface contents, else Value interface number."""
    try:
        n = Atspi.Text.get_character_count(ch)
        if n > 0: return (Atspi.Text.get_text(ch, 0, min(n, 120)) or "")[:120]
    except Exception: pass
    try:
        v = Atspi.Value.get_current_value(ch)
        if v is not None: return ("%g" % v)[:120]
    except Exception: pass
    return ""

def _focused_window(app):
    """Mac: kAXFocusedWindow of the app. AT-SPI: the app's top-level child with the ACTIVE state (None -> the Mac returns nil -> validator unavailable)."""
    for j in range(app.get_child_count()):
        try:
            w = app.get_child_at_index(j)
            if w is not None and w.get_state_set().contains(Atspi.StateType.ACTIVE): return w
        except Exception: continue
    return None

def _fingerprint(name, budget=None):
    """Port of captureAccessibilityFingerprint: preorder walk of the FOCUSED WINDOW only, role|title|value triples, <=120 nodes, depth<8, time budget; ORDER and duplicates kept."""
    budget = FP_BUDGET_S if budget is None else budget
    desk = Atspi.get_desktop(0); app = None
    h = (name or "").strip().lower()
    for i in range(desk.get_child_count()):
        c = desk.get_child_at_index(i)
        if c is None or _is_self(c): continue
        nm = (c.get_name() or "").lower()
        if nm == h or (h and h in nm): app = c; break
    if app is None: raise TimeoutError("fingerprint: app not found")
    root = _focused_window(app)
    if root is None: raise TimeoutError("fingerprint: no focused (ACTIVE) window")
    out = []; end = _time.monotonic() + budget; state = {"cut": False}
    def rec(node, depth):
        if len(out) >= FP_MAX_NODES or depth >= FP_MAX_DEPTH: return
        if _time.monotonic() >= end: state["cut"] = True; return
        try: role = node.get_role_name() or ""
        except Exception: role = ""
        try: title = node.get_name() or ""
        except Exception: title = ""
        out.append("%s|%s|%s" % (role, title, _fp_value(node)))
        try: n = node.get_child_count()
        except Exception: return
        for k in range(n):
            if len(out) >= FP_MAX_NODES: return
            try: ch = node.get_child_at_index(k)
            except Exception: continue
            if ch is not None: rec(ch, depth + 1)
    rec(root, 0)
    return {"triples": out, "truncated": state["cut"], "window": (root.get_name() or "")[:60]}

def fingerprint(name, timeout=4):
    if ISOLATED: return _sub(["--fp", name or ""], timeout)
    return _W.call(_fingerprint, (name,), timeout)

MODAL_ROLES = {"dialog", "alert", "file chooser"}

def _modal_title(hint):
    """Linux counterpart of WorkflowRunner.detectBlockingModalDialogTitle (Swift :1321): a showing top-level window of the plan's app that is a dialog (AT-SPI role dialog/alert/file chooser, the
    analogue of AXDialog/AXSystemDialog) or has the MODAL state (the analogue of a blocking AXSheet). Returns the title ('' if untitled) or None. The app is found like runningAppMatching(hint):
    case-insensitive name equality or containment."""
    h = (hint or "").strip().lower()
    if not h: return None
    desk = Atspi.get_desktop(0)
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if app is None or _is_self(app): continue
        nm = (app.get_name() or "").lower()
        if not (nm == h or h in nm): continue
        for j in range(app.get_child_count()):
            try:
                w = app.get_child_at_index(j); st = w.get_state_set()
                if not (st.contains(Atspi.StateType.SHOWING) or st.contains(Atspi.StateType.VISIBLE)): continue
                if w.get_role_name() in MODAL_ROLES or st.contains(Atspi.StateType.MODAL): return w.get_name() or ""
            except Exception: continue
    return None

def modal_title(hint, timeout=3):
    """Bounded child read, like every other native AT-SPI read. Returns (status, title): ('ok', title|None) or ('unavailable', None) - unavailable is never reported as 'no modal'."""
    try:
        d = _sub(["--modal", hint or ""], timeout) if ISOLATED else {"title": _W.call(_modal_title, (hint,), timeout)}
        return "ok", d.get("title")
    except Exception: return "unavailable", None

def probe_isolated(rect, hint_pid=None, timeout=6):
    d = _sub(["--probe", _json.dumps(list(rect)), hint_pid or 0, max(1.0, timeout - 1.5)], timeout)
    return d.get("element"), d.get("selection")

def targets_isolated(timeout=6):
    return _sub(["--targets"], timeout)["targets"]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--probe", "--targets", "--ready", "--modal", "--fp"):
        try:
            if sys.argv[1] == "--probe":
                rect = _json.loads(sys.argv[2]); hp = int(sys.argv[3]) or None; wall = _time.monotonic() + float(sys.argv[4])
                el, sel = _probe(rect, hp, 4000, wall); print(_json.dumps({"element": el, "selection": sel}))
            elif sys.argv[1] == "--fp": print(_json.dumps(_fingerprint(sys.argv[2] if len(sys.argv) > 2 else "")))
            elif sys.argv[1] == "--modal": print(_json.dumps({"title": _modal_title(sys.argv[2] if len(sys.argv) > 2 else "")}))
            elif sys.argv[1] == "--ready": print(_json.dumps({"ready": bool(ready(2.5))}))
            elif len(sys.argv) > 3 and sys.argv[2] == "--app": print(_json.dumps({"targets": _app_targets(sys.argv[3])}))  # filter in the child
            else: print(_json.dumps({"targets": _all_targets()}))
        except TimeoutError as e: print(_json.dumps({"error": str(e), "unavailable": True}))
        except Exception as e: print(_json.dumps({"error": type(e).__name__ + ": " + str(e)[:100]}))
        sys.exit(0)
    for t in all_targets(): print(t)
