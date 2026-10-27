"""X11 action driver (counterpart of Mac ActionExecutor, ported from git 6e97782 TipTour/Actions/ActionExecutor.swift + WorkflowRunner execute*Step).
Gated by the caller: --act (default OFF = point-only), the user-confirmed plan, and exact current-step approval. Every xdotool call is CHECKED (non-zero exit, timeout or missing binary = ok False, never "performed").
EXPLICIT DIFFERENCES: X11 keys are focus-bound rather than per-PID posted, with a non-atomic final check/dispatch gap. Type/setValue use identity-bound native EditableText and exact text/caret readback. Type reconstructs plain selected-span text in one whole-value call, not Mac AXSelectedText; rich text/events/undo and stored highlight ranges are not parity-proven. Cmd maps to Ctrl, Option to Alt; Wayland is not covered."""
import subprocess, re, os, shutil, time, glob, threading
_TL = threading.local()  # per-execution cancel Event (set by the caller on STOP/supersede/cancel): checked before EVERY OS side effect
SECRET = re.compile(r"password|passcode|\bpin\b|card number|cvv|cvc|verification code|one[- ]time", re.I)
class _XFail(Exception): pass
def _chk(what=""):
    ev = getattr(_TL, "ev", None)
    if ev is not None and ev.is_set(): raise _XFail("cancelled (stop/supersede) before %s: nothing further was sent" % (what or "the next OS call"))
def _sleep(sec):
    ev = getattr(_TL, "ev", None); end = time.monotonic() + sec
    while time.monotonic() < end:
        _chk("waiting"); time.sleep(min(0.05, max(0.0, end - time.monotonic())))
def _run(cmd, timeout, what, input_data=None):
    """Checked cancellable process. Files avoid waiting forever on inherited child pipes. No success inference from a still-running launcher."""
    import tempfile
    _chk(what)
    with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe, tempfile.TemporaryFile() as fi:
        if input_data is not None: fi.write(input_data.encode()); fi.seek(0)
        try: p = subprocess.Popen(cmd, stdin=fi, stdout=fo, stderr=fe, start_new_session=True)
        except OSError as e: raise _XFail("%s unavailable: %s" % (what, e))
        end = time.monotonic() + timeout
        while p.poll() is None:
            ev = getattr(_TL, "ev", None)
            if (ev is not None and ev.is_set()) or time.monotonic() > end:
                try: os.killpg(p.pid, 9)
                except ProcessLookupError: pass
                p.wait(timeout=2)
                raise _XFail("%s %s; outcome not verified" % (what, "cancelled" if ev is not None and ev.is_set() else "timed out"))
            time.sleep(0.03)
        fe.seek(0); e = fe.read(400).decode("utf-8", "replace"); fo.seek(0); o = fo.read().decode("utf-8", "replace")
        if p.returncode: raise _XFail("%s failed rc=%s: %s" % (what, p.returncode, e.strip()[:200]))
        _chk("result of " + what)
        return o
def _x(*a):
    """Run xdotool and CHECK it: a non-zero exit, a timeout or a missing binary raises _XFail."""
    _chk("xdotool " + " ".join(map(str, a[:2])))
    try: r = subprocess.run(["xdotool", *map(str, a)], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired: raise _XFail("xdotool %s timed out" % " ".join(map(str, a[:2])))
    except OSError as e: raise _XFail("xdotool unavailable: %s" % e)
    if r.returncode != 0: raise _XFail("xdotool %s failed rc=%s: %s" % (" ".join(map(str, a[:2])), r.returncode, (r.stderr or "").strip()[:200]))
    return r
# ---- Mac normalizeShortcutToken / normalizedHotkeyTokens (port) -> X11 keysyms
_MOD = {"cmd": "ctrl", "option": "alt", "ctrl": "ctrl", "shift": "shift"}  # Mac Cmd -> Ctrl on Linux (explicit difference)
_SYM = {"escape": "Escape", "delete": "BackSpace", "return": "Return", "enter": "Return", "tab": "Tab", "space": "space", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
        "pageup": "Prior", "pagedown": "Next", "home": "Home", "end": "End", "forwarddelete": "Delete"}
def normalize_token(t):
    n = (t or "").strip().strip(".,;:").lower()
    return {"cmd": "cmd", "command": "cmd", "\u2318": "cmd", "opt": "option", "option": "option", "alt": "option", "\u2325": "option", "ctrl": "ctrl", "control": "ctrl", "\u2303": "ctrl",
            "shift": "shift", "\u21e7": "shift", "esc": "escape", "del": "delete", "backspace": "delete", "return": "return"}.get(n, n)
def hotkey_tokens(s):
    raw = [x.strip() for x in re.split(r"[+\-]", s or "") if x.strip()]
    if not raw: raise _XFail("unparseable keyboard shortcut %r" % s)
    mods, final = [], None
    for r in raw:
        n = normalize_token(r)
        if n == "fn": raise _XFail("the fn modifier cannot be sent on X11 (no fn keysym); shortcut %r not sent" % s)
        if n in ("cmd", "option", "ctrl", "shift"): mods.append(n)
        else:
            if final is not None: raise _XFail("unparseable keyboard shortcut %r" % s)
            final = n
    if final is None: raise _XFail("unparseable keyboard shortcut %r" % s)
    return mods + [final]
def _keysym(tok): return _SYM.get(tok) or (tok if len(tok) == 1 else tok.capitalize() if re.fullmatch(r"f\d{1,2}", tok) is None else tok.upper())
def scroll_key(direction, granularity):  # Mac scrollKeyName (port, incl. page left/right -> arrow)
    return {("up", "line"): "Up", ("down", "line"): "Down", ("left", "line"): "Left", ("right", "line"): "Right", ("up", "page"): "Prior", ("down", "page"): "Next", ("left", "page"): "Left", ("right", "page"): "Right"}.get(((direction or "").lower(), (granularity or "").lower()))
def normalize_url(raw):  # Mac normalizedURL (port, simplified): keep an explicit scheme, absolute paths become file://, bare hosts get https://
    r = (raw or "").strip()
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", r): return r
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+\-]*:(?!\d+(/|$))", r) and "." not in r.split(":", 1)[0]: return r  # any explicit scheme (mailto:, tel:, sms:, ...) like the Mac; host:port is NOT a scheme
    if r.startswith("/") or r.startswith("~"): return "file://" + os.path.expanduser(r)
    return "https://" + r
# ---- target app activation (Mac activateTargetApplicationIfNeeded: X11 = window activation, no per-pid posting)
def _windows():
    try: ids = _x("search", "--onlyvisible", "--name", ".").stdout.split()
    except _XFail: return []
    out = []
    for w in ids:
        try:
            name = _x("getwindowname", w).stdout.strip()
            cls = subprocess.run(["xprop", "-id", w, "WM_CLASS"], capture_output=True, text=True, timeout=3).stdout
        except (_XFail, OSError, subprocess.TimeoutExpired): continue
        out.append((w, cls.lower(), name.lower()))
    return out
def activate_target(app_hint):
    """Return (ok, detail). REQUIRES a plan app hint: without one nothing is sent (an arbitrary active window is never assumed). Candidates = visible windows whose WM_CLASS or title contains the hint;
    one that is already the ACTIVE window wins, else exactly one candidate is activated; several distinct candidates = ambiguous = refuse. The active window is re-read after activation and must equal the chosen window."""
    if not (app_hint or "").strip(): return False, "no target app named by the plan; keys/typing are not sent to an unknown active window"
    h = app_hint.strip().lower()
    cands = [w for w in _windows() if h in w[1] or h in w[2]]
    if not cands: return False, "target app %r has no visible window; nothing was sent" % app_hint
    try: cur = _x("getactivewindow").stdout.strip()
    except _XFail: cur = ""
    pick = [c for c in cands if c[0] == cur]
    if not pick:
        if len(cands) > 1: return False, "target app %r matches %d windows (%s); ambiguous, nothing was sent" % (app_hint, len(cands), ", ".join(c[0] for c in cands[:5]))
        pick = cands
    w = pick[0][0]
    try:
        if w != cur: _x("windowactivate", "--sync", w); _sleep(0.2)
        act = _x("getactivewindow").stdout.strip()
    except _XFail as e: return False, str(e)
    if act != w: return False, "could not activate the target window %s (active is %s); nothing was sent" % (w, act)
    return True, "target window %s for %r is active" % (w, app_hint)
# ---- launchers
def _app_dirs():
    home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    dirs = [home] + [d for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if d] + ["/usr/local/share", "/usr/share"]
    seen, out = set(), []
    for d in dirs:
        p = os.path.join(d, "applications")
        if p not in seen: seen.add(p); out.append(p)
    return out
def _desktop_entry(name):
    """(basename, full path) of the .desktop entry whose Name= or file basename equals the app name (XDG_DATA_HOME, XDG_DATA_DIRS, then the usual system dirs; first dir wins)."""
    n = name.strip().lower()
    for d in _app_dirs():
        for f in sorted(glob.glob(d + "/*.desktop")):
            try: txt = open(f, errors="ignore").read()
            except OSError: continue
            m = re.search(r"^Name=(.+)$", txt, re.M)
            if (m and m.group(1).strip().lower() == n) or os.path.basename(f)[:-8].lower() == n: return os.path.basename(f), f
    return None
def open_application(name):
    if not (name or "").strip(): raise _XFail("openApp has no app name")
    de = _desktop_entry(name)
    if de:
        _run(["gtk-launch", de[0]], 15, "gtk-launch " + de[0]); return "launched %s via gtk-launch (launcher exited 0; window/foreground not verified)" % de[0]
    exe = shutil.which(name.strip().lower().replace(" ", "-")) or shutil.which(name.strip())
    if not exe: raise _XFail("application %r not found (no desktop entry, not on PATH)" % name)
    _chk("launching " + exe)
    try: p = subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e: raise _XFail("could not start %s: %s" % (exe, e))
    _sleep(0.5)
    if p.poll() is not None and p.returncode != 0: raise _XFail("%s exited immediately with rc=%s" % (exe, p.returncode))
    return "started %s pid %s (still running after 0.5 s; window/foreground not verified)" % (exe, p.pid)
def open_url(raw, preferred_app=None):
    url = normalize_url(raw)
    if not url or url in ("https://",): raise _XFail("openURL has no URL")
    if (preferred_app or "").strip():
        de = _desktop_entry(preferred_app)
        if not de: raise _XFail("preferred application %r not found" % preferred_app)
        _run(["gio", "launch", de[1], url], 15, "gio launch " + de[0])
    else: _run(["xdg-open", url], 15, "xdg-open")
    if url.lower().startswith(("http://", "https://")): _sleep(2.0)  # Mac: wait 2 s after an http(s) open
    return "opened %s" % url
ACTION_TYPES = ("openApp", "openURL", "keyboardShortcut", "pressKey", "type", "setValue", "scroll")
def execute(step, px, app_hint=None, plan_app=None, cancel=None, click_guard=None, expected_window=None):
    """One step. Click types need px (pointer position from the resolver); the other types need no pointer. Returns the tool-response dict; ok True only when every OS call succeeded."""
    _TL.expected_focus = step.get('_expected_focus') or step.get('_browser_find'); _TL.document_shortcut = step.get('type') == 'keyboardShortcut' and step.get('label','').lower() in ('ctrl+f','control+f','cmd+f','command+f'); _TL.ev = cancel; _TL.bound = None; _TL.click_guard = click_guard; _TL.expected_window = expected_window
    try: return _execute(step, px, app_hint if app_hint is not None else plan_app)
    except _XFail as e: return {"ok": False, "error": str(e)}
    finally: _TL.ev = None; _TL.bound = None; _TL.click_guard = None; _TL.expected_window = None
def focus_info(app_hint, editable=True):
    try:
        from . import atspi_resolver as ar
        d = ar._sub(["--focus-document" if getattr(_TL,"document_shortcut",False) and not editable else "--focus", app_hint or ""], 5); f = d.get("focus")
    except Exception as e: return {"ok": False, "error": "focused element unavailable: " + type(e).__name__}
    if not f or not f.get("identity"): return {"ok": False, "error": "focused native element identity unavailable"}
    if f.get("password") or SECRET.search(f.get("name") or ""): return {"ok": False, "error": "secret/password field refused"}
    if editable and not f.get("editable"): return {"ok": False, "error": "not an EDITABLE native text field"}
    return dict(f, ok=True)

def _window_state():
    w = _x("getactivewindow").stdout.strip()
    r = subprocess.run(["xprop", "-id", w, "_NET_WM_PID"], capture_output=True, text=True, timeout=2)
    m = re.search(r"=\s*(\d+)", r.stdout)
    if r.returncode or not m: raise _XFail("active X11 window PID unavailable; nothing sent")
    state = (w, int(m.group(1)))
    expected = getattr(_TL, 'expected_window', None)
    if expected is not None and state != expected: raise _XFail('approved destination window/PID changed; nothing sent')
    return state

def _check_bound(app_hint, editable=False):
    _chk("native identity check")
    old = getattr(_TL, "bound", None)
    if old and _window_state() != old[0]: raise _XFail("active X11 window/PID changed; nothing further sent")
    f = focus_info(app_hint, editable)
    if not f.get("ok"): raise _XFail(f["error"])
    if getattr(_TL,"expected_focus",None) and f.get("identity") != _TL.expected_focus: raise _XFail("original approved native focus changed; nothing sent")
    ws = _window_state()  # recheck AFTER potentially slow native read
    if ws[1] != f["identity"]["pid"]: raise _XFail("native app PID does not match active X11 window; nothing sent")
    if old and (ws != old[0] or f["identity"] != old[1]): raise _XFail("focused window or element identity changed; nothing further sent")
    from . import atspi_resolver as ar
    status, title = ar.modal_title(app_hint)
    if status != "ok" or title is not None: raise _XFail("modal state unavailable or blocking dialog present; nothing sent")
    f2 = focus_info(app_hint, editable)
    if not f2.get("ok") or f2.get("identity") != f["identity"]: raise _XFail("native focus changed during modal check; nothing sent")
    if _window_state() != ws: raise _XFail("active window changed during modal check; nothing sent")
    _chk("input dispatch")
    _TL.bound = (ws, f["identity"])
    return f

def _focus(app_hint):
    if getattr(_TL, 'expected_window', None) is not None:
        _window_state()  # Do not activate a different same-name destination after a slow read.
    ok, d = activate_target(app_hint)
    if not ok: raise _XFail(d)
    _TL.bound = None
    _check_bound(app_hint)
    return d

def _skill_numeric_text(step, app_hint):
    """Pinned ActionExecutor.typeText skill-directed key branch, never setValue."""
    if step.get('type') != 'type': return None
    from .app_skills import AppSkillRegistry
    skill = AppSkillRegistry().skill(app_hint)
    text = step.get('value') if step.get('value') is not None else step.get('label', '')
    if not skill or not skill.should_type_physical_keys(text): return None
    if step.get('_native_range'):
        raise _XFail('skill numeric key input cannot apply a saved native range; nothing sent')
    # The bundled numeric policy has an ASCII key mapping. Unknown policy
    # characters refuse; no Unicode clipboard/whole-value fallback is inferred.
    keysyms = {'.':'period','-':'minus','+':'plus','*':'asterisk','/':'slash'}
    trimmed = text.strip()
    if any(c not in '0123456789.-+*/' for c in trimmed):
        raise _XFail('skill numeric character has no supported X11 key mapping; nothing sent')
    detail = _focus(app_hint)
    sent = 0; attempted = 0
    try:
        for char in trimmed:
            _check_bound(app_hint, False)
            _chk('skill numeric key')
            attempted += 1  # dispatch may apply even when the subprocess reports failure
            _x('key', '--clearmodifiers', keysyms.get(char,char))
            sent += 1
            _sleep(.035)
    except _XFail as exc:
        return {'ok':False,'status':'skill_numeric_partial' if attempted else 'skill_numeric_refused',
                'error':('Numeric input may be partial; no further keys sent. ' if attempted else '') + str(exc),'character_commands_confirmed':sent,'character_commands_attempted':attempted,'possibly_applied':bool(attempted),'retry_safe':False,
                'text_verified':False,'delivery':'skill-directed identity-bound X11 numeric keys'}
    return {'ok':True,'status':'performed type','character_commands_confirmed':sent,'character_commands_attempted':attempted,'text_verified':False,
            'delivery':'skill-directed identity-bound X11 numeric keys','detail':detail}

def _native_text(step, app_hint):
    numeric = _skill_numeric_text(step, app_hint)
    if numeric is not None: return numeric
    import json, sys
    saved = step.get('_native_range')
    if saved:
        ws = _window_state()
        if str(ws[0]) != str(saved.get('xwindow')) or ws[1] != (saved.get('identity') or {}).get('pid'):
            raise _XFail('saved selection recipient no longer focused; nothing written')
    d = _focus(app_hint); f = _check_bound(app_hint, False)
    if step.get('_browser_find'):
        # App-owned binding exists only for the immediate approved Find-text suffix.
        if (f.get('identity') != step['_browser_find'] or step.get('type') != 'type' or f.get('role') != 'entry' or f.get('name') != 'Find' or
                not f.get('editable_state') or f.get('password') or f.get('document_rect') is not None):
            raise _XFail('verified browser Find recipient unavailable; nothing sent')
        before = f; text = step.get('value');sel = f.get('selection') or [f.get('caret'),f.get('caret')]
        if not isinstance(text,str) or '\n' in text or '\r' in text or None in sel:raise _XFail('Find text/range unsupported')
        expected = f['text'][:sel[0]] + text + f['text'][sel[1]:]
        fresh = _check_bound(app_hint,False)
        if any(fresh.get(k)!=before.get(k) for k in ('identity','text','selection','caret','element_rect','document_rect','name')):raise _XFail('Find recipient changed before typing')
        _chk('bound Find typing');_x('type','--clearmodifiers','--delay','0','--',text)
        after = _check_bound(app_hint,False)
        if after.get('text')!=expected or after.get('caret')!=sel[0]+len(text) or after.get('selection'):
            return {'ok':False,'possibly_applied':True,'retry_safe':False,'error':'Find typing dispatched but readback differs; do not retry'}
        return {'ok':True,'status':'performed type','chars':len(text),'text_verified':True,'caret_verified':True,'delivery':'identity-bound native Find keystrokes + AT-SPI readback','detail':d}
    if not f.get("editable"):
        if f.get("editable_state") and not f.get("native_editable_iface"):
            from . import browser_text
            # Worker-local cancellation state must be checked on this thread, not inside a new asyncio worker.
            def recheck(): return _check_bound(app_hint, False)
            result = browser_text.write(step, app_hint, f, recheck, _chk); result["detail"] = d; return result
        raise _XFail("focused field not native EDITABLE; nothing written")
    f = _check_bound(app_hint, True)
    req = {"operation": step["type"], "text": step.get("value") if step.get("value") is not None else step.get("label", ""),
           "app": app_hint, "identity": f["identity"], "xwindow": _TL.bound[0][0], "saved_range": step.get("_native_range")}
    raw = _run([sys.executable, "-m", "tiptour_linux.atspi_resolver", "--focused-write"], 7, "identity-bound native write", json.dumps(req))
    try: result = json.loads(raw)
    except Exception: raise _XFail("native write result unreadable")
    if "ok" not in result: return {"ok": False, "error": "native write unavailable: " + result.get("error", "unknown")}
    result["detail"] = d
    return result
def _execute(step, px, app_hint):
    t = (step.get("type") or "click"); label = step.get("label", "") or ""
    if SECRET.search(label) and t in ("type", "setValue"): return {"ok": False, "error": "refused: secret field"}
    if t in ("click", "doubleClick", "rightClick"):
        if px is None: return {"ok": False, "error": "no coordinates"}
        guard = getattr(_TL, "click_guard", None)
        if guard is None or not guard(): raise _XFail("click recipient not verified before pointer move")
        _x("mousemove", px[0], px[1])
        _chk("click hit test")
        if not guard(): raise _XFail("click recipient covered, moved or unavailable before button dispatch")
        if t == "doubleClick": _x("click", "--repeat", "2", "1")
        else: _x("click", "3" if t == "rightClick" else "1")
        return {"ok": True, "status": "performed " + t, "at": list(px)}
    if t == "openApp": return {"ok": True, "status": "performed openApp", "detail": open_application(label or app_hint)}
    if t == "openURL": return {"ok": True, "status": "performed openURL", "detail": open_url(label, app_hint)}
    if t == "keyboardShortcut":
        if not label.strip(): return {"ok": False, "error": "keyboardShortcut step has no label"}
        toks = hotkey_tokens(label); d = _focus(app_hint)
        combo = "+".join([_MOD[m] for m in toks[:-1]] + [_keysym(toks[-1])])
        _check_bound(app_hint); _x("key", "--clearmodifiers", combo); return {"ok": True, "status": "performed keyboardShortcut", "keys": combo, "detail": d}
    if t == "pressKey" and step.get("_native_range") and normalize_token(label) == "delete":
        result = _native_text(dict(step, type="type", value=""), app_hint)
        if result.get("ok"): result["status"] = "performed pressKey"; result["effect"] = "deleted saved native selected range"
        return result
    if t == "pressKey":
        if not label.strip(): return {"ok": False, "error": "pressKey step has no key"}
        tok = normalize_token(label)
        if tok in _MOD or tok == "cmd": return {"ok": False, "error": "pressKey needs a non-modifier key, got %r" % label}
        d = _focus(app_hint); ks = _keysym(tok)
        _check_bound(app_hint)
        if step.get('_navigation_guard') and not step['_navigation_guard']():raise _XFail('original approved GET form changed; nothing sent')
        if step.get('_navigation_guard'):_check_bound(app_hint)
        _chk('navigation dispatch'); _x("key", "--clearmodifiers", ks); return {"ok": True, "status": "performed pressKey", "keys": ks, "detail": d}
    if t in ("type", "setValue"): return _native_text(step, app_hint)
    if t == "scroll":
        direction = step.get("direction") or label or "down"; amount = step.get("amount") if isinstance(step.get("amount"), int) else 3; gran = step.get("by") or "line"
        key = scroll_key(direction, gran)
        if not key: return {"ok": False, "error": "invalid scroll direction %s/%s" % (direction, gran)}
        n = max(1, min(amount, 50)); d = _focus(app_hint)
        _TL.sent = 0
        for _i in range(n): _check_bound(app_hint); _x("key", "--clearmodifiers", key); _TL.sent += 1; _sleep(0.03)  # one key per call so a cancel stops between presses
        return {"ok": True, "status": "performed scroll", "keys": "%dx %s" % (n, key), "detail": d}
    return {"ok": False, "error": "unsupported step type " + t}
