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


class CoordinateError(RuntimeError): pass
_COORD_CACHE = {}
def _screen_rect(node, provenance=False):
    # All failures while establishing native->X11 mapping are refusal conditions,
    # including Display connection creation/close and native ancestry reads.
    try:
        return _screen_rect_unchecked(node, provenance)
    except CoordinateError:
        raise
    except Exception as e:
        raise CoordinateError("native/X11 coordinate mapping unavailable: " + type(e).__name__) from e

def _screen_rect_unchecked(node, provenance=False):
    """Translate AT-SPI logical SCREEN units to X11 root pixels, bound to the same PID/title/frame.
    Only a uniquely matched window and uniform integer scale with matching origin/size are accepted.
    Unknown mapping is unavailable, never an inferred DPI default.
    """
    from Xlib import display as xd
    w = node
    for _ in range(70):
        if w is None: raise CoordinateError('native window ancestor unavailable')
        parent=w.get_parent()
        if parent is not None and parent.get_role_name()=='application':break
        w=parent
    else: raise CoordinateError('native window ancestry too deep')
    native = w.get_extents(Atspi.CoordType.SCREEN); title=w.get_name() or '';pid=w.get_process_id()
    key=(pid,w.path,title,native.x,native.y,native.width,native.height)
    cached=_COORD_CACHE.get(key)
    if cached and _time.monotonic()-cached[0]<0.25:
        mapping=cached[1];check=xd.Display()
        try:
            frame=check.create_resource_object("window",mapping["x11_frame_id"]);g=frame.get_geometry()
            if [g.x,g.y,g.width,g.height]!=mapping["x11_frame"]:raise CoordinateError("X11 frame moved during native coordinate read")
        except CoordinateError:raise
        except Exception as e:raise CoordinateError("cached X11 frame unavailable: "+type(e).__name__)
        finally:check.close()
        r=node.get_extents(Atspi.CoordType.SCREEN);scale=mapping["scale"]
        value=dict(mapping,rect=[r.x*scale,r.y*scale,r.width*scale,r.height*scale],native_rect=[r.x,r.y,r.width,r.height])
        return value if provenance else value["rect"]
    d=xd.Display(); root=d.screen().root; matches=[]
    try:
        pa=d.intern_atom('_NET_WM_PID');na=d.intern_atom('_NET_WM_NAME');utf=d.intern_atom('UTF8_STRING')
        def scan(x,depth=0):
            if depth>4:return
            try:
                p=x.get_full_property(pa,0);name=x.get_full_property(na,utf);nm=(name.value.decode('utf-8','replace') if name else x.get_wm_name()) or ''
                if p is not None and int(p.value[0])==pid and nm==title:
                    frame=x
                    while frame.query_tree().parent.id!=root.id:frame=frame.query_tree().parent
                    g=frame.get_geometry();matches.append((g.x,g.y,g.width,g.height,frame.id))
                for ch in x.query_tree().children:scan(ch,depth+1)
            except Exception:return
        scan(root)
    finally:d.close()
    matches=list(set(matches))
    if len(matches)!=1 or native.width<=0 or native.height<=0:raise CoordinateError('native/X11 window mapping unavailable or ambiguous')
    x,y,ww,hh,frameid=matches[0];sx=ww/native.width;sy=hh/native.height;scale=round(sx)
    if scale not in (1,2,3,4) or abs(sx-scale)>.02 or abs(sy-scale)>.02 or abs(native.x*scale-x)>3 or abs(native.y*scale-y)>3:raise CoordinateError('unsupported native/X11 coordinate mapping native=%r x11=%r' % ([native.x,native.y,native.width,native.height],[x,y,ww,hh]))
    r=node.get_extents(Atspi.CoordType.SCREEN)
    mapped=[r.x*scale,r.y*scale,r.width*scale,r.height*scale]
    value={"rect":mapped,"native_rect":[r.x,r.y,r.width,r.height],"scale":scale,"native_window":[native.x,native.y,native.width,native.height],"x11_frame":[x,y,ww,hh],"x11_frame_id":frameid,"pid":pid,"window_path":w.path}
    _COORD_CACHE.clear(); _COORD_CACHE[key]=(_time.monotonic(),value)
    return value if provenance else mapped

def _coordinate_status(hint):
    desk=Atspi.get_desktop(0);h=(hint or "").strip().lower();found=[]
    for i in range(desk.get_child_count()):
        app=desk.get_child_at_index(i)
        if app is None or _is_self(app):continue
        for j in range(app.get_child_count()):
            w=app.get_child_at_index(j)
            if w is not None and w.get_state_set().contains(Atspi.StateType.ACTIVE) and (h in (app.get_name() or "").lower() or h in (w.get_name() or "").lower()):found.append(w)
    if not h or len(found)!=1:raise RuntimeError("active native target window unavailable or ambiguous")
    return _screen_rect(found[0],True)

def coordinate_status(hint,timeout=4):
    try:
        d=_sub(["--coordinates",hint or ""],timeout)
        return ("ok",d["mapping"]) if d.get("mapping") else ("unavailable",d.get("error","coordinate mapping unavailable"))
    except Exception as e:return "unavailable",str(e)

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
                role = ch.get_role_name()
                # AT-SPI controls expose ENABLED as a state, unlike optional AXEnabled.
                # Do not make disabled controls candidates; still recurse into descendants.
                actionable = role in {"push button", "toggle button", "menu item", "check box", "radio button", "link", "page tab", "entry"}
                if role in CLICKABLE and (not actionable or st.contains(Atspi.StateType.ENABLED)):
                    coord = _screen_rect(ch,True); ext = type("Rect",(),dict(zip(("x","y","width","height"),coord["rect"])))()
                    if ext.width <= 0 or ext.height <= 0:continue
                    out.append({"label": ch.get_name() or "", "role": role, "rect": [ext.x, ext.y, ext.width, ext.height],
                                "coordinate_mapping":coord, "app": node.get_application().get_name() if depth == 0 else None, "native_identity": {"pid": ch.get_process_id(), "path": ch.path}})
        except CoordinateError: raise
        except Exception: pass
        walk(ch, depth + 1, out)
    return out

def _all_targets():
    desk = Atspi.get_desktop(0); res = []
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if _is_self(app): continue
        try: nodes=walk(app)
        except CoordinateError:continue  # unrelated desktop/WM app cannot poison enumeration; plan-window mapping is checked independently before any pointing
        for t in nodes:
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

def _target_window_nodes(hint):
    mapping=_coordinate_status(hint);desk=Atspi.get_desktop(0)
    for i in range(desk.get_child_count()):
        app=desk.get_child_at_index(i)
        if app is not None and app.get_process_id()==mapping["pid"]:
            windows=[app.get_child_at_index(j) for j in range(app.get_child_count())]
            matches=[w for w in windows if w is not None and w.path==mapping["window_path"]]
            if len(matches)!=1:raise CoordinateError("bound native window disappeared")
            nodes=walk(matches[0])
            for t in nodes:t["app"]=app.get_name()
            return nodes
    raise CoordinateError("coordinate-bound app disappeared")
def resolve(label, hint=None, timeout=6):
    l = label.strip().lower()
    ts = _sub(["--resolve-targets",hint],timeout)["targets"] if hint else all_targets()
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
                    r = _screen_rect(ch)
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
            except CoordinateError: raise
            except Exception: pass
            if not skip: rec(ch, app)
    apps = [desk.get_child_at_index(i) for i in range(desk.get_child_count())]
    if hint_pid:  # the window the highlight was painted over goes first
        apps.sort(key=lambda ap: 0 if _pid(ap) == int(hint_pid) else 1)
    hint_walked = False; hint_browser = False
    if hint_pid and not any(_pid(ap) == int(hint_pid) for ap in apps):
        raise TimeoutError("hint window pid %s is not in the AT-SPI registry (stale or not exported yet)" % hint_pid)
    for app in apps:
        if hint_pid and _pid(app)!=int(hint_pid):continue  # a highlighted window binds the probe; unrelated desktops/WM trees cannot supply its text
        if _is_self(app): continue  # never walk our own overlay windows (served by our own main loop; slow and irrelevant)
        try:
            if hint_pid and _pid(app) == int(hint_pid):
                if app.get_child_count() == 0: raise TimeoutError("hint app exports an empty tree (not ready)")
                hint_walked = True; hint_browser = bool(_re_browser.search(app.get_name() or ''))
            rec(app, app.get_name())
        except (TimeoutError,CoordinateError): raise
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
            rec["res"] = "child_error"
            if str(d["error"]).startswith("CoordinateError:"):raise CoordinateError(d["error"])
            raise TimeoutError(d["error"]) if d.get("unavailable") else RuntimeError(d["error"])
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
    """Inspect ALL top-level windows of the identity-matched application. Missing app is unavailable."""
    h = (hint or "").strip().lower()
    if not h: raise TimeoutError("modal check requires app identity")
    desk = Atspi.get_desktop(0); matches = []
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if app is None or _is_self(app): continue
        nm = (app.get_name() or "").lower()
        windows = [app.get_child_at_index(j) for j in range(app.get_child_count())]
        if nm == h or h in nm or any(w is not None and h in (w.get_name() or "").lower() for w in windows): matches.append(windows)
    if len(matches) != 1: raise TimeoutError("modal app unavailable or ambiguous")
    for w in matches[0]:
        if w is None: continue
        st = w.get_state_set()
        if not (st.contains(Atspi.StateType.SHOWING) and st.contains(Atspi.StateType.VISIBLE)): continue
        if w.get_role_name() in MODAL_ROLES or st.contains(Atspi.StateType.MODAL): return w.get_name() or ""
    return None

def _focused_record(hint):
    """Return the focused native object and stable per-session identity. No role-based editable inference."""
    h = (hint or "").strip().lower()
    if not h: return None, None
    desk = Atspi.get_desktop(0)
    matches = []
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if app is None or _is_self(app): continue
        nm = (app.get_name() or "").lower()
        for j in range(app.get_child_count()):
            w = app.get_child_at_index(j)
            if w is not None and w.get_state_set().contains(Atspi.StateType.ACTIVE) and (h == nm or h in nm or h in (w.get_name() or "").lower()):
                matches.append((app, w))
    if len(matches) != 1: return None, None
    app, w = matches[0]; stack = [(w, 0)]; n = 0
    while stack and n < 20000:
        node, dep = stack.pop(); n += 1
        st = node.get_state_set(); rn = node.get_role_name()
        if st.contains(Atspi.StateType.FOCUSED) and rn not in ("frame", "window", "application", "document web", "document frame"):
            txt = None; selection = None; caret = None
            ti = node.get_text_iface()
            import re
            secret = rn == "password text" or bool(re.search(r"password|passcode|\bpin\b|cvv|cvc|one[- ]time|verification code", node.get_name() or "", re.I))
            if ti is not None and not secret:
                txt = ti.get_text(0, min(ti.get_character_count(), 20000)); caret = ti.get_caret_offset()
                if ti.get_n_selections():
                    r = ti.get_selection(0); selection = [r.start_offset, r.end_offset]
            ext = type("Rect",(),dict(zip(("x","y","width","height"),_screen_rect(w))))()
            ident = {"pid": app.get_process_id(), "window_path": w.path, "element_path": node.path,
                     "window_name": w.get_name() or "", "window_rect": [ext.x, ext.y, ext.width, ext.height]}
            # A native object path binds the actual field, rather than a repeated name/role.
            if not ident["pid"] or not ident["window_path"] or not ident["element_path"]: return None, None
            document_rect = None; parent = node
            for _ in range(60):
                if parent is None: break
                if parent.get_role_name() in ("document web", "document frame"):
                    document_rect = _screen_rect(parent); break
                parent = parent.get_parent()
            return node, {"document_rect": document_rect, "identity": ident, "role": rn, "name": node.get_name() or "", "editable": bool(st.contains(Atspi.StateType.EDITABLE) and node.get_editable_text_iface() is not None),
                          "editable_state": bool(st.contains(Atspi.StateType.EDITABLE)), "native_editable_iface": node.get_editable_text_iface() is not None, "element_rect": _screen_rect(node), "password": secret, "text": txt, "selection": selection, "caret": caret}
        if dep < 60:
            for j in range(node.get_child_count()):
                c = node.get_child_at_index(j)
                if c is not None: stack.append((c, dep + 1))
    return None, None

def _focus_info(hint):
    return _focused_record(hint)[1]

def _focused_write(req):
    # Identity-bound native write: a later focus change cannot redirect the write to another object.
    import subprocess, re
    node, f = _focused_record(req.get("app"))
    if not f or f.get("identity") != req.get("identity"): return {"ok": False, "error": "focused native field identity changed; nothing written"}
    if not f["editable"] or f["password"] or re.search(r"password|passcode|\bpin\b|cvv|cvc|one[- ]time|verification code", f["name"], re.I):
        return {"ok": False, "error": "focused field is not a verified non-secret editable field; nothing written"}
    if f["text"] is None or len(f["text"]) >= 20000: return {"ok": False, "error": "complete text unavailable; nothing written"}
    w = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=2)
    if w.returncode or w.stdout.strip() != req.get("xwindow"): return {"ok": False, "error": "active X11 window changed; nothing written"}
    if _modal_title(req.get("app")) is not None: return {"ok": False, "error": "blocking modal present; nothing written"}
    node2, f2 = _focused_record(req.get("app"))
    if not f2 or f2["identity"] != f["identity"] or any(f2[k] != f[k] for k in ("text", "selection", "caret")):
        return {"ok": False, "error": "focused field/text/selection changed during check; nothing written"}
    w = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=2)
    if w.returncode or w.stdout.strip() != req.get("xwindow"): return {"ok": False, "error": "X11 focus changed during native checks; nothing written"}
    # Check editable/secret states again immediately before dispatch to this SAME object.
    st = node.get_state_set()
    if not st.contains(Atspi.StateType.FOCUSED) or not st.contains(Atspi.StateType.EDITABLE) or node.get_role_name() == "password text":
        return {"ok": False, "error": "field state changed; nothing written"}
    et = node.get_editable_text_iface(); ti = node.get_text_iface(); text = req["text"]
    saved = req.get("saved_range")
    if saved:
        if saved.get("identity") != f["identity"] or saved.get("xwindow") != req.get("xwindow") or saved.get("text") != f["text"]:
            return {"ok": False, "error": "saved highlighted field/window/text changed; nothing written"}
        if not saved.get("selection") or len(saved["selection"]) != 2: return {"ok": False, "error": "saved range unavailable; nothing written"}
        f["selection"] = saved["selection"]
    if req["operation"] == "setValue" and not saved:
        expected = text; ok = et.set_text_contents(text)
    else:
        sel = f["selection"]; start, end = sel if sel else (f["caret"], f["caret"])
        if start is None or not (0 <= start <= end <= len(f["text"])): return {"ok": False, "error": "selected range unavailable; nothing written"}
        expected = f["text"][:start] + text + f["text"][end:]
        # One native replacement call avoids a half-completed delete/insert sequence.
        ok = et.set_text_contents(expected)
        if ok:
            caret_ok = ti.set_caret_offset(start + len(text))
            if not caret_ok or ti.get_caret_offset() != start + len(text) or ti.get_n_selections() != 0:
                return {"ok": False, "error": "text was written but caret/selection readback did not match; do not continue", "text_verified": True, "caret_verified": False}
    actual = ti.get_text(0, ti.get_character_count())
    if not ok or actual != expected: return {"ok": False, "error": "native write failed or readback did not match", "text_verified": False}
    return {"ok": True, "status": "performed " + req["operation"], "chars": len(text), "text_verified": True,
            "caret_verified": (req["operation"] == "setValue" and not saved) or ti.get_caret_offset() == start + len(text),
            "delivery": "AT-SPI EditableText on identity-bound object", "field_identity": f["identity"]}

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
    if len(sys.argv) > 1 and sys.argv[1] in ("--probe", "--targets", "--ready", "--modal", "--fp", "--focus", "--focused-write", "--coordinates", "--resolve-targets"):
        try:
            if sys.argv[1] == "--probe":
                rect = _json.loads(sys.argv[2]); hp = int(sys.argv[3]) or None; wall = _time.monotonic() + float(sys.argv[4])
                el, sel = _probe(rect, hp, 4000, wall); print(_json.dumps({"element": el, "selection": sel}))
            elif sys.argv[1] == "--resolve-targets": print(_json.dumps({"targets": _target_window_nodes(sys.argv[2])}))
            elif sys.argv[1] == "--coordinates": print(_json.dumps({"mapping": _coordinate_status(sys.argv[2] if len(sys.argv)>2 else "")}))
            elif sys.argv[1] == "--fp": print(_json.dumps(_fingerprint(sys.argv[2] if len(sys.argv) > 2 else "")))
            elif sys.argv[1] == "--focused-write": print(_json.dumps(_focused_write(_json.load(sys.stdin))))
            elif sys.argv[1] == "--focus": print(_json.dumps({"focus": _focus_info(sys.argv[2] if len(sys.argv) > 2 else "")}))
            elif sys.argv[1] == "--modal": print(_json.dumps({"title": _modal_title(sys.argv[2] if len(sys.argv) > 2 else "")}))
            elif sys.argv[1] == "--ready": print(_json.dumps({"ready": bool(ready(2.5))}))
            elif len(sys.argv) > 3 and sys.argv[2] == "--app": print(_json.dumps({"targets": _app_targets(sys.argv[3])}))  # filter in the child
            else: print(_json.dumps({"targets": _all_targets()}))
        except TimeoutError as e: print(_json.dumps({"error": str(e), "unavailable": True}))
        except Exception as e: print(_json.dumps({"error": type(e).__name__ + ": " + str(e)[:100]}))
        sys.exit(0)
    for t in all_targets(): print(t)
