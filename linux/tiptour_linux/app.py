import queue
"""TipTour Linux tracer bullet: text/voice-turn -> Gemini Live (screenshot + tool call)
-> pointer overlay. Point-only mode. Usage: python -m tiptour_linux.app --ask "..." --keys-glob '/path/*/password'"""
import os as _os
_g = _os.environ.get('TIPTOUR_GIR_PATH')
if _g: _os.environ['GI_TYPELIB_PATH'] = _g + ':' + _os.environ.get('GI_TYPELIB_PATH', '')
import gi
gi.require_version('Gtk', '3.0')
import argparse, asyncio, glob, json, os, sys, threading, time, wave
gi.require_version("Gdk", "3.0")
from gi.repository import GLib, Gtk, Gdk
from .keypool import KeyPool, mask
from .live import LiveClient, connect_with_pool
from .capture import grab, norm_to_px, changed_fraction, target_changed_fraction
from .overlay import PointerOverlay
from .detector import IconDetector
from . import perception, workflow
from .workflow import PlanTargetMatcher
from .target_cache import LocalPerceptionTargetCache
TARGET_CACHE = LocalPerceptionTargetCache()

def _mouse_location():
    """Mac: NSEvent.mouseLocation = proximity anchor when there is no previous-step point (ElementResolver.localPerceptionResolution)."""
    import subprocess
    try:
        o = subprocess.run(["xdotool", "getmouselocation", "--shell"], capture_output=True, text=True, timeout=2).stdout
        d = dict(l.split("=", 1) for l in o.split() if "=" in l); return (float(d["X"]), float(d["Y"]))
    except Exception: return None
PREV_STEP_POINT = {"p": None}  # Mac previousStepResolvedGlobalScreenPoint (voice flow is one step per turn, so it stays None unless a multi-step runner sets it)
def _half_up(v):
    import math
    return int(math.floor(v + 0.5))  # Swift .rounded() half away from zero (coordinates are >= 0); Python round() is banker's
def _local_resolve(lab, cache=None):
    anchor = PREV_STEP_POINT["p"] or _mouse_location()
    return (cache or TARGET_CACHE).resolve(lab, prefer_near_global_point=anchor)
try:
    from . import atspi_resolver
except Exception as _e:
    print('AT-SPI stage unavailable:', type(_e).__name__, str(_e)[:100]); atspi_resolver = None

def main():
    if os.environ.get('TIPTOUR_HANG_DUMP'):  # diagnostic: dump all thread stacks to stderr after N seconds if still running
        import faulthandler; faulthandler.dump_traceback_later(int(os.environ['TIPTOUR_HANG_DUMP']), repeat=False, file=sys.stderr)
    _neko_env_override = 'TIPTOUR_NEKO' in os.environ
    from . import settings as _st; _st.apply_env()  # settings.json -> env (explicit env wins); never enables --act
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", action="append", default=[])
    ap.add_argument("--serve", default="", help="keep ONE Gemini session open; text lines appended to this FIFO/file path are user utterances, painted highlights arrive from the live Ctrl+Shift monitor; @quit ends")
    ap.add_argument("--keys-glob", default=os.environ.get("TIPTOUR_KEYS_GLOB", ""))
    ap.add_argument("--out", default="/tmp/tiptour-run")
    ap.add_argument("--act", action="store_true", help="allow one-step actions (click/type/key); default point-only")
    ap.add_argument("--highlight", action="store_true", help="enable the X11 Ctrl+Shift focus-highlight monitor; ask text @highlight waits for one painted trail")
    ap.add_argument("--hold", type=float, default=2.0)
    ap.add_argument("--voice", action="store_true", help="push-to-talk voice (Ctrl+Alt toggles a live mic session, replies are played); needs --serve FIFO path (can stay unused) and PulseAudio/pipewire-pulse tools")
    ap.add_argument("--readonly-harness", action="store_true", help="opt-in loopback read-only observe/skills/targets/screenshots; no action endpoints")
    ap.add_argument("--text-ui", action="store_true", help="opt-in GTK text command panel and Ctrl+K, same local proposal/Yes path")
    ap.add_argument('--radial-preview', action='store_true', help='opt-in Ctrl+Alt+Super visual preview only; no input-mode dispatch')
    ap.add_argument('--radial-input', action='store_true', help='opt-in radial Speak toggles enabled voice; replaces Ctrl+Alt hotkey; Type unsupported without JEV')
    a = ap.parse_args()
    if a.radial_preview and (a.voice or a.highlight):
        ap.error('--radial-preview cannot run with --voice or --highlight: partial modifier chords can activate those monitors')
    if a.radial_input and (not a.voice or a.radial_preview):
        ap.error('--radial-input requires --voice, cannot combine with --radial-preview; its monitor replaces Ctrl+Alt hotkey')
    os.makedirs(a.out, exist_ok=True)
    if a.text_ui and not a.serve: a.serve = os.path.join(a.out, "control.fifo")
    from .keypool import configured_keys
    keys = configured_keys(a.keys_glob)
    keys = [k for k in os.environ.get("GEMINI_API_KEYS_FIRST", "").split(",") if k] + keys  # test hook: put (invalid) keys first to exercise real failover
    text_status = {"panel": None}
    log_f = open(os.path.join(a.out, "trace.log"), "w")
    def log(*x):
        s = (time.strftime("%H:%M:%S") + (".%03d" % int((time.time() % 1) * 1000) if _os.environ.get("TIPTOUR_LOG_MS") == "1" else "") + " ") + " ".join(map(str, x)); print(s, flush=True); log_f.write(s + "\n"); log_f.flush()
        if text_status['panel']:
            msg = ' '.join(map(str, x))
            status = None
            if 'proposal rev ' in msg and 'displayed' in msg: status = 'Plan ready. Review the proposal, then Confirm or Cancel.'
            elif 'user approved plan rev ' in msg: status = 'Approved plan running. Stop cancels remaining work.'
            elif 'STOP (' in msg: status = 'Stopped. Pending and running work cancelled.'
            elif 'plan complete' in msg: status = 'Plan finished. Ready for another request.'
            elif 'pending plan rev ' in msg and 'cleared' in msg: status = 'Proposal cleared without running.'
            if status:
                GLib.idle_add(text_status['panel'].activity.set_text, status)
    def dlog(*x):  # detailed lines (window titles, element labels, utterances, replies): only with TIPTOUR_DEBUG_LOG=1; default logs carry no page/user text
        if os.environ.get("TIPTOUR_DEBUG_LOG") == "1": log(*x)
    overlay = PointerOverlay(); overlay.show_all()
    from .overlay import PausePanel
    panel = PausePanel(lambda t: _control_post('retry', t), lambda t: _control_post('skip', t))
    from .overlay import ProposalPanel
    hl_post = {"fn": None}
    pprop = ProposalPanel(lambda k, rev: hl_post["fn"] and hl_post["fn"]("@%s %d" % (k, rev)))
    text_ui = None; status_item = None; radial_preview = None; shared_gestures = None; radial_gesture = {"key": None, "highlight": None, "retired": False}; radial_post = {"fn": None, "invalidate": None}; shell_windows = {"settings": None, "closed": False, "busy": threading.Event()}
    if a.text_ui:
        from .text_panel import TextPanel
        text_ui = TextPanel(lambda t: hl_post["fn"] and hl_post["fn"](t))
        text_status["panel"] = text_ui
        from .status_item import StatusItem
        def open_settings():
            if shell_windows['closed']: return
            if shell_windows['settings']: shell_windows['settings'].present(); return
            def closed(): shell_windows['settings'] = None
            def live_neko(enabled):
                # Never block GTK on a worker which may be awaiting GTK capture
                # hide/restore. Retry after capture exits; newest toggle wins.
                shell_windows['neko_revision'] = shell_windows.get('neko_revision',0)+1
                revision=shell_windows['neko_revision']
                def apply():
                    if shell_windows['closed'] or revision != shell_windows.get('neko_revision'):return False
                    if not _cap_lk.acquire(blocking=False):return True
                    try:
                        overlay.set_neko_enabled(enabled)
                        os.environ['TIPTOUR_NEKO']='1' if enabled else '0'
                    finally:_cap_lk.release()
                    return False
                GLib.timeout_add(16,apply)
            w = _st.gtk_window(closed, standalone=False, on_neko_changed=None if _neko_env_override else live_neko)
            shell_windows['settings'] = w; shell_windows['busy'].set()
            w.connect('map', lambda *_: shell_windows['busy'].set())
            w.connect('unmap', lambda *_: shell_windows['busy'].clear())
            w.connect('destroy', lambda *_: setattr(w, '_tiptour_destroyed', True))
        status_item = StatusItem(text_ui.open_from_menu, text_ui.stop_work, lambda: hl_post['fn'] and hl_post['fn']('@quit'), open_settings)
    if a.radial_preview or a.radial_input:
        from .radial import RadialPreview
        def radial_status(message):
            log(message)
            if text_ui: text_ui.activity.set_text(message)
        def radial_select(option, point):
            if radial_post['fn']: radial_post['fn'](option, point, radial_gesture['key'])
            else: radial_status('Radial input unavailable: runtime is not ready.')
        radial_preview = RadialPreview(radial_status, radial_select if a.radial_input else None, external_monitor=a.radial_input and a.highlight)
    def shell_busy():
        return shell_windows["busy"].is_set() or bool(status_item and status_item.capture_busy.is_set())
    def own_windows():
        menu_window = status_item.capture_window() if status_item else None
        return tuple(w for w in (overlay, overlay.paws.window if overlay.paws else None, panel, pprop, text_ui, menu_window, radial_preview, shell_windows["settings"], hl.get("trail")) if w is not None)
    from .highlight_owner import Owner
    highlight_owner = Owner()
    hl = {"loop": None, "q": None, "mon": None, "trail": None, "closed": threading.Event(), "commit_worker": None, "commit_queue": None}
    def clear_trail_owned():
        with highlight_owner.lock: clear_epoch = highlight_owner.epoch
        def clear_current():
            with highlight_owner.lock:
                if not highlight_owner.closed and highlight_owner.epoch == clear_epoch:
                    if hl['trail']: hl['trail'].clear()
            return False
        GLib.idle_add(clear_current)
    if a.highlight:
        from . import highlight as _hl
        from .trail_overlay import TrailOverlay
        _scr = Gdk.Screen.get_default(); hl["trail"] = TrailOverlay(_scr.get_width(), _scr.get_height())
        _commit_q = queue.Queue(maxsize=1); hl["commit_queue"] = _commit_q
        def _commit_worker():  # context building (incl. the bounded AT-SPI probe) runs OFF the 60Hz sampler thread; commits stay in order
            while True:
                item = _commit_q.get()
                if item is None or hl["closed"].is_set(): return
                token, pts, ask_chord = item
                if not highlight_owner.valid(token): continue
                _t0 = time.time()
                try:
                    ctx = _hl.build_context(pts, _hl.xdotool_window_at, _hl.atspi_probe if os.environ.get('TIPTOUR_USE_ATSPI', '1') == '1' else None, selection_probe=(__import__('tiptour_linux.cdp_resolver', fromlist=['x']).selection if os.environ.get('TIPTOUR_USE_CDP', '1') == '1' else None))
                except Exception:
                    ctx = None
                print(time.strftime('%H:%M:%S'), 'commit: context built in %.2fs; atspi=%s element=%s selection=%s src=%s dom=%s' % (time.time() - _t0, (ctx or {}).get('atspi_status'), bool(ctx and ctx.get('element')), bool(ctx and ctx.get('text_selection')), ((ctx or {}).get('text_selection') or {}).get('source', 'atspi' if ctx and ctx.get('text_selection') else '-'), (ctx or {}).get('dom_selection_status')), flush=True)
                highlight_owner.publish(token, (ctx, ask_chord))
        hl["commit_worker"] = threading.Thread(target=_commit_worker, daemon=True, name="commit-worker"); hl["commit_worker"].start()
        gesture = {'token': None}
        def _commit(pts, ask_chord):
            token = gesture['token']
            if not highlight_owner.valid(token): return
            future = highlight_owner.job(token)
            if not future: return
            try: _commit_q.put_nowait((token, list(pts), ask_chord))
            except queue.Full: highlight_owner.publish(token, (None, ask_chord))
            if hl['loop']:
                def enqueue():
                    if highlight_owner.valid(token): hl_post['fn']('@highlight %d' % token)
                hl['loop'].call_soon_threadsafe(enqueue)
        def _warm():  # Chrome builds its AT-SPI tree lazily; poll until an app tree is non-empty (max 40s), serialized with probes by the resolver lock
            from . import atspi_resolver as _ar
            t_end = time.time() + 60
            while time.time() < t_end and not hl["closed"].is_set():  # SHORT slices (3s wall each) so a real request is never stuck behind a long warm walk; Chrome keeps its progress between slices
                try: _ar.probe((0, 0, 1, 1), timeout=3.5, max_nodes=4000, low=True)
                except Exception: pass
                if _ar.ready_bounded(2): break
                hl["closed"].wait(1)
        if os.environ.get('TIPTOUR_USE_ATSPI', '1') == '1' and atspi_resolver and os.environ.get('TIPTOUR_NO_WARM') != '1': threading.Thread(target=_warm, daemon=True).start()
        def paint_trail(points, token):
            frozen = list(points)
            def apply():
                with highlight_owner.lock:
                    if highlight_owner.valid(token) and highlight_owner.visible:
                        highlight_owner.points = frozen
                        if not highlight_owner.suppressed: hl['trail'].set_points(frozen)
                return False
            GLib.idle_add(apply)
        def begin_trail(point):
            token = highlight_owner.begin(); gesture['token'] = token
            if token is not None: paint_trail([point], token)
        def monitor_failed(error):
            with highlight_owner.lock:
                highlight_owner.invalidate(); failure_epoch = highlight_owner.epoch
            def report():
                with highlight_owner.lock:
                    if highlight_owner.closed or highlight_owner.epoch != failure_epoch: return False
                    hl['trail'].clear()
                    message = 'Highlight unavailable: X11 sampler failed (%s).' % error
                    log(message)
                    if text_ui: text_ui.activity.set_text(message)
                return False
            GLib.idle_add(report)
        if a.radial_input:
            from .gesture_adapter import Adapter
            def shared_radial(kind, point, key):
                radial_gesture['key'] = key
                radial_preview.transition(kind, point)
                if kind == 'cancel' and radial_post['invalidate']:
                    radial_post['invalidate']()
            def shared_begin(point, key):
                # Shared sampler alone owns the Stop/full-release barrier. A
                # genuine new chord may begin without a neutral gap, as on Mac.
                def admit():
                    if not shared_gestures.monitor.valid(key[0]): return
                    radial_gesture['highlight'] = key
                    highlight_owner.released(); begin_trail(point)
                if hl.get('loop'): hl['loop'].call_soon_threadsafe(admit)
            def shared_move(points, key):
                def apply():
                    if shared_gestures.monitor.valid(key[0]) and radial_gesture['highlight'] == key:
                        paint_trail(points, gesture['token'])
                if hl.get('loop'): hl['loop'].call_soon_threadsafe(apply)
            def shared_commit(points, ask, key):
                def apply():
                    if shared_gestures.monitor.valid(key[0]) and radial_gesture['highlight'] == key:
                        _commit(points, ask)
                if hl.get('loop'): hl['loop'].call_soon_threadsafe(apply)
            def shared_cancel(key):
                highlight_owner.invalidate()
                hl['trail'].clear()
            def schedule_transition(fn):
                GLib.idle_add(lambda: (fn(), False)[1])
            def shared_retired(generation):
                # Logical cancellation is immediate on the sampler, not delayed
                # behind GTK. Only the paint/status cleanup waits for GTK.
                radial_gesture['retired'] = True
                highlight_owner.invalidate()
                if radial_post['invalidate']: radial_post['invalidate'](generation)
            shared_gestures = Adapter(schedule_transition, shared_radial,
                shared_begin, shared_move, shared_commit, shared_cancel,
                lambda: monitor_failed('shared sampler'), retire=shared_retired)
            radial_preview.monitor = shared_gestures.monitor
            shared_gestures.start()
        else:
            hl["mon"] = _hl.HighlightMonitor(on_begin=begin_trail, on_move=lambda p: paint_trail(hl["mon"].points, gesture['token']), on_commit=_commit, on_release=highlight_owner.released, on_error=monitor_failed); hl["mon"].start()
    results = []
    onnx_path = os.environ.get('TIPTOUR_DETECTOR_ONNX', '/tmp/uielement.onnx')
    detector = IconDetector(onnx_path) if os.path.exists(onnx_path) else None
    def on_gtk(fn):
        ev = threading.Event()
        def w(): fn(); ev.set(); return False
        GLib.idle_add(w); ev.wait(5)
    import subprocess
    def ident():
        def xo(*c):
            try: return subprocess.run(["xdotool", *c], capture_output=True, text=True, timeout=2).stdout.strip()
            except Exception: return ""
        w = xo("getwindowfocus")
        return (w, xo("getwindowname", w) if w else "", xo("getwindowgeometry", "--shell", w).replace("\n", " ") if w else "")
    frame_id = {"v": None}; ov = {"hidden": False}; cur = {}; glock = threading.RLock(); pause_rs = {'r': None}; gate = {'turn': False, 'replay': False}
    def _target_valid(app, label, rect, expected=None):
        if not app or not rect or not atspi_resolver: return False  # unverifiable source (CDP/model box): fail closed
        try:
            ts = []
            for _try in range(3):  # Chrome's tree can be empty/wobbling right after a switch: bounded retry, never a blind match
                try: ts = atspi_resolver.app_targets(app, timeout=5) or []
                except Exception: ts = []  # timeout counts as an empty read; retried (bounded)
                if ts: break
                time.sleep(0.3)
            _same = [t for t in ts if (t.get('label') or '').strip().lower() == (label or '').strip().lower()]
            dlog("target_valid n_targets=%d same_label=%d rect_match=%s tries=%d" % (len(ts), len(_same), any(t.get('rect') and all(abs(t['rect'][k] - rect[k]) <= 8 for k in range(4)) for t in _same), _try + 1))
            for t in ts:
                r = t.get('rect')
                if (t.get('label') or '').strip().lower() == (label or '').strip().lower() and r and all(abs(r[i] - rect[i]) <= 8 for i in range(4)) and (expected is None or t.get("native_identity") == expected): return True
        except Exception as e:
            dlog("target_valid error %s" % type(e).__name__); return False
        return False
    from .clickdetect import ClickDetector, guarded_callback
    clicks = ClickDetector(); plan_tok = {"n": 0}; click_events = []; validators = []
    _cap_lk = threading.RLock(); _own_cap = {}; _pin_lk = threading.Lock(); _pin_seq = {"started": 0, "applied": 0}
    def capture_clean(pin=False, fast=False, eligible=None):
        with _cap_lk: return _capture_clean_locked(pin, fast, eligible)  # serialized: concurrent worker-thread captures must not interleave overlay hide/grab/show
    def _capture_clean_locked(pin, fast, eligible=None):
        # own overlay must not appear in frames sent to the model
        _capture_token = plan_tok["n"]
        def _eligible():
            if not (eligible() if eligible else _capture_token == plan_tok["n"]):raise RuntimeError("stale capture discarded")
        _eligible()
        _clean = overlay.clean_capture_ready
        _was = [];_hidden_ack=[False]; _trail_token = highlight_owner.epoch
        def _hide_own():
            if not (eligible() if eligible else _capture_token == plan_tok["n"]):return
            if fast and shell_busy():return  # never dismiss a shell menu/settings for an idle frame
            for w in own_windows():
                if w.get_visible():
                    if status_item and w is status_item.capture_window(): status_item.dismiss_for_capture()
                    else: _was.append(w);w.hide()
            _hidden_ack[0]=True
        with highlight_owner.lock: highlight_owner.suppressed += 1
        try:
            if not _clean:
                on_gtk(_hide_own);time.sleep(0.05 if fast else 0.25);_eligible()
                if not _hidden_ack[0]:raise RuntimeError("clean capture hide not acknowledged")
            if pin:
                with _pin_lk: _pin_seq["started"] += 1; _my_seq = _pin_seq["started"]  # newest-STARTED pinned capture owns the frame identity (captures now run in worker threads, so a slow/cancelled older one can finish after a newer one)
            try:
                _eligible()
                r = grab(exclude_xid=[w.get_window().get_xid() for w in own_windows() if w.get_window()]) if _clean else grab()
                _eligible()
            except Exception as e:
                _eligible()  # stale exclusion failure must never trigger a raw capture
                if not _clean:raise
                log("capture exclusion fallback: " + str(e))
                on_gtk(_hide_own);time.sleep(0.05 if fast else 0.25);_eligible()
                if not _hidden_ack[0]:raise RuntimeError("clean capture hide not acknowledged")
                r=grab();_eligible()
            if pin:
                with _pin_lk:
                    _idv = ident()
                    if _my_seq >= _pin_seq["applied"]: _pin_seq["applied"] = _my_seq; frame_id['v'] = _idv; frame_id['img'] = r[0]  # ask-specific identity: only the per-ask capture pins it; the 1fps stream must not overwrite it
                _own_cap.clear(); _own_cap.update(seq=_my_seq, token=_capture_token, pair=(_idv, r[0]))  # this capture's OWN (identity, image) pair, read by capture_pinned under _cap_lk
            _eligible()
            return r
        finally:
            with highlight_owner.lock: highlight_owner.suppressed -= 1
            if _was:
                def _restore_own():
                    if not (eligible() if eligible else _capture_token == plan_tok["n"]): return
                    for w in _was:
                        if getattr(w, "_tiptour_destroyed", False): continue
                        if w is hl.get("trail") and (not highlight_owner.valid(_trail_token) or not highlight_owner.visible or w.closed): continue
                        if w is overlay and ov.get('covered'): continue
                        if w is radial_preview and (w.state.center is None or w.monitor.closed.is_set()): continue
                        if w is text_ui or w is shell_windows["settings"]:
                            w.set_focus_on_map(False); w.show_all(); w.set_focus_on_map(True)
                        elif w is hl.get("trail"):
                            with highlight_owner.lock:
                                if highlight_owner.valid(_trail_token) and highlight_owner.visible and not highlight_owner.suppressed:
                                    w.set_points(list(highlight_owner.points))
                        else: w.show_all()
                on_gtk(_restore_own)

    def capture_pinned():
        """Pinned capture + this capture's own ownership record (pin seq, identity/image pair). Resolves bind to THIS record, not the shared latest state (Mac: per-plan latestCaptureForActivePlan)."""
        with _cap_lk:
            r = _capture_clean_locked(True, False); return r, dict(_own_cap)

    def _on_loop(fn):
        lp = hl.get('loop')
        if lp: lp.call_soon_threadsafe(fn)
        else: fn()
    def _control_post(cmd, tok=None):
        """All pause controls (FIFO / panel buttons) are applied ON the asyncio loop thread, so they are ordered with resolve/arm/render (which are synchronous after their last await) like the Mac's @MainActor."""
        lp = hl.get("loop")
        if lp: lp.call_soon_threadsafe(_control, cmd, tok)
        else: _control(cmd, tok)
    def _control(cmd, tok=None):
        if tok is not None and tok != plan_tok['n']:  # TOKEN ELIGIBILITY FIRST, before ANY cancellation or redundancy classification: a panel button queued/clicked for an earlier target/pause episode must neither cancel the current valid task nor be mislabelled redundant
            click_events.append({"control": cmd + "_refused", "reason": "stale panel"}); log("control %s refused: stale panel (belongs to an earlier target/pause; current task untouched)" % cmd); return
        _sk = hl.get('skip_adv')  # a previous Skip's advance for THIS plan token is still pending (queued behind a turn/replay or resolving): a further Skip is the same press, not another step. Check BEFORE cancelling, else the old code cancelled that valid advance and then refused ("no current target"), stranding the plan.
        if cmd == 'skip' and _sk and _sk[0] is hl.get('task') and not _sk[0].done() and _sk[1] == plan_tok['n']:
            click_events.append({"control": "skip_redundant", "reason": "previous Skip advance still pending"}); log("control skip: redundant, the previous Skip's advance is still pending (kept, not doubled)"); return
        if cmd == 'skip' and radial_post.get('invalidate'): radial_post['invalidate']()
        if cmd == 'skip' and hl.get('cancel_task'): hl['cancel_task']()  # cancel queued/in-flight Retry/Resume/advance before the Skip takes effect
        """Pause controls for a target whose click was seen but whose effect is unverified/unchanged. Not routed through the model."""
        if cmd in ("retry", "resume") and hl.get("replay"):  # Mac retryCurrentStep()/resume(): re-capture + rerun the full cascade for the active step (resume only while paused, like `guard pausedReason != nil`)
            if tok is not None and tok != plan_tok["n"]:
                click_events.append({"control": cmd + "_refused", "reason": "stale panel"}); log("control %s refused: stale panel" % cmd); return
            _paused = cur.get("paused") or pause_rs["r"] or (bool(validators) and validators[-1].verdict == "unchanged_paused")
            if cmd == "resume" and not _paused:
                click_events.append({"control": "resume_refused", "reason": "not paused"}); log("control resume refused: not paused"); return
            if radial_post.get("invalidate"): radial_post["invalidate"]()
            click_events.append({"control": cmd, "mode": "replay_full_cascade", "label": cur.get("label")}); GLib.idle_add(lambda: panel.hide_panel() and False); cur["paused"] = None
            hl["replay"](cmd, plan_tok["n"]); return
        with glock:
            if tok is not None and tok != plan_tok["n"]:  # a panel button queued/clicked for an earlier target or pause episode must never act on a newer one
                click_events.append({"control": cmd + "_refused", "reason": "stale panel"}); log("control %s refused: stale panel (belongs to an earlier target/pause)" % cmd); return
            if not cur.get("label") or not (cur.get("armed") or cur.get("paused") == "resolutionFailed"):
                click_events.append({"control": cmd + "_refused", "reason": "no current target"}); log("control %s refused: no current target" % cmd); return
            if cmd == "skip" and hl.get("advance") and (hl.get('last_call') or {}).get("args") and (hl.get('last_call') or {}).get("idx", 0) + 1 < len(hl["last_call"]["args"].get("steps") or []):
                click_events.append({"control": "skip", "mode": "advance"}); GLib.idle_add(lambda: panel.hide_panel() and False); plan_tok["n"] += 1; clicks.disarm(); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire); cur['armed'] = False; cur['paused'] = None; hl["advance"]("skip", plan_tok["n"]); return
            if cmd == "skip":
                plan_tok["n"] += 1; clicks.disarm(); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire); cur['armed'] = False; cur['paused'] = None; (hl.get('last_call') or {}).clear(); PREV_STEP_POINT['p'] = None  # plan ended: a queued/late Retry/Resume must not revive it
                click_events.append({"control": "skip", "label": cur["label"]}); GLib.idle_add(lambda: panel.hide_panel() and False); log("control skip: pointer dismissed, target skipped (%r)" % cur["label"]); return
        v = validators[-1].verdict if validators else None
        if ov['hidden'] and cur.get('paused') != 'app_switch':
            click_events.append({"control": "retry_refused", "reason": "target already dismissed"}); log("control retry refused: target already dismissed"); return
        if v != "unchanged_paused" and cur.get("paused") != "app_switch":
            click_events.append({"control": "retry_refused", "reason": "not paused (verdict %s)" % v}); log("control retry refused: not paused (verdict %s)" % v); return
        def _retry_tail(_app=cur.get("app"), _lab=cur["label"]):
            _c = cur.get("rect"); _pt = (_c[0] + _c[2] / 2, _c[1] + _c[3] / 2) if _c else cur.get("px")
            if cur.get("pin") is None or clicks.pin_state(_pt, cur["pin"]) != "ok":
                click_events.append({"control": "retry_refused", "reason": "target window not in front / focused"}); log("control retry refused: target window not in front / focused"); return
            with glock:
                plan_tok["n"] += 1; cur['paused'] = None
                st = cur["rearm"]()
                if st == "UNAVAILABLE": click_events.append({"control": "retry_refused", "reason": "detector could not arm"}); log("control retry refused: detector could not arm"); return
                ov['hidden'] = False; ov['covered'] = False; GLib.idle_add(lambda: (overlay.show_all(), overlay.move(overlay.tip[0]-overlay.CX, overlay.tip[1]-overlay.CY)) and False)
                click_events.append({"control": "retry", "label": cur["label"]}); GLib.idle_add(lambda: panel.hide_panel() and False); log("control retry: re-armed the same target %r with a fresh baseline" % cur["label"])
        async def _retry_checked(_tok0):  # the AT-SPI validity read (up to 3 x 5s) runs OFF the loop so Skip/new asks are applied meanwhile; a result for a superseded plan is discarded
            _ok = await asyncio.to_thread(_target_valid, cur.get("app"), cur["label"], cur.get("rect"))
            if plan_tok["n"] != _tok0:
                click_events.append({"control": "retry_refused", "reason": "superseded while verifying the target"}); log("control retry refused: superseded while verifying the target"); return
            if not _ok:
                click_events.append({"control": "retry_refused", "reason": "target not verifiable at its place"}); log("control retry refused: target not verifiable at its place"); return
            _retry_tail()
        if hl.get("loop") is not None: asyncio.ensure_future(_retry_checked(plan_tok["n"])); return
        if not _target_valid(cur.get("app"), cur["label"], cur.get("rect")):
            click_events.append({"control": "retry_refused", "reason": "target not verifiable at its place"}); log("control retry refused: target not verifiable at its place"); return
        _retry_tail()
    async def run():
        run_task = asyncio.current_task()
        class _SV(str): arr = 0; sess = 0
        class _TCv(dict): sess = 0
        pipe = {"tok": 0, "task": None}
        voice_cancel = {'future': None}
        def retire_voice_context_writers():
            future = voice_cancel['future']
            if future and not future.done(): future.set_result(None)
        own = [0]  # VOICE OWNERSHIP counter: bumped by every PTT-on edge, OFF edge, abort and replacement start; an attempt may touch the mic/gate/buffer only while its captured value is current
        vg = {"ready": True, "buf": [], "pq": None, "lock": threading.Lock()}  # mic audio gate: while a fresh provider connection for a new PTT session is being made, audio is BUFFERED (in order), then flushed to the NEW client once it is ready
        vs = {"n": 0}  # VOICE SESSION EPOCH: bumped at every PTT on/off edge. Every transcript chunk / turnComplete is stamped with the epoch it arrived in at the single ingress; a voice turn only consumes events of ITS epoch (an old session's prefix/suffix can never join or finish a new utterance)
        ing = {"parts": [], "stopped": 0}
        arr = {"n": 0}
        loop = asyncio.get_running_loop(); q = asyncio.Queue(); hl['loop'] = loop; hl['q'] = asyncio.Queue()
        audio = bytearray(); out_tr = []
        gen = [0]; tainted = [False]
        def _mk_on_event(g):  # events carry the session generation they came from; a replaced (tainted) session can never feed a later turn
            def on_event(k, v):
                _late = (k == "__late" and os.environ.get("TIPTOUR_TEST_MODE") == "1")  # TEST SEAM only: the origin epoch is captured, then an off/replacement edge is queued BEFORE this callback's delivery (the race the delivery-time check closes); the REAL _put below then runs and must reject it
                if _late: k, v = v
                _e = vs["n"]  # the epoch of the ORIGIN at callback time (a delivery that runs after a later toggle/replacement must not take the newer epoch)
                def _put(k=k, v=v, _e=_e):
                    if ing.get("shutdown") or g != gen[0] or _e != vs["n"]: click_events.append({"gate": "late_callback_rejected", "kind": k}); return  # delivery-time checks BEFORE any side effect (arrival number, ingress STOP latch, buffers): a replaced session's or an earlier epoch's callback that executes after a toggle/replacement is rejected. The origin epoch is the one captured at callback time
                    arr["n"] += 1
                    if k != "audio": dlog("evt", k, arr["n"], str(v)[:20] if k == "inputTranscript" else "")
                    if k == "inputTranscript" and hl.get("readonly_worker"): hl["readonly_worker"].cancel_current()
                    if k == "turnComplete": v = _TCv(v if isinstance(v, dict) else {}); v.sess = _e
                    if k in ("turnComplete", "closed", "interrupted"): ing["parts"] = []  # utterance boundary (a closed/interrupted session or turn never concatenates its partial into a later STOP)
                    if k == "inputTranscript":
                        v = _SV(v); v.arr = arr["n"]; v.sess = _e; ing["parts"].append(str(v))
                        if ing.get("ready") and _norm_resp("".join(ing["parts"])) in _STOP and (_goal_live() or prop["state"] in ("pending", "approved")): _stop_work("voice-ingress"); ing["stopped"] = arr["n"]  # SINGLE INGRESS (the only producer of the event queue): the current WHOLE utterance is an exact STOP -> stop at receipt, ahead of any consumer; the ordered consumers are untouched
                    if False: pass  # receipt stamp (loop arrival number) on every user-transcript chunk: voice answers count only chunks that arrived AFTER the proposal was rendered
                    q.put_nowait((k, v))
                if _late: loop.call_soon_threadsafe(lambda: (vs.__setitem__("n", vs["n"] + 1), ing.__setitem__("parts", [])))
                if g == gen[0]: loop.call_soon_threadsafe(_put)
            return on_event
        pool = KeyPool(keys)
        async def _writer(cl, pq, tok, ow):  # the single ordered audio writer of one voice session (one client, one queue): chunks are sent strictly in order, never overtaken
            while True:
                b = await pq.get()
                if b is None or pipe["tok"] != tok: return
                try: await cl.send_audio(b)
                except Exception as _we:
                    log("voice: audio write failed (%s); aborting this voice session (voice OFF; press PTT again)" % type(_we).__name__); click_events.append({"gate": "voice_writer_failed", "err": type(_we).__name__})
                    if pipe["tok"] == tok: _abort_voice("writer failed", ow)  # only the CURRENT session's writer may abort; a stale writer cannot touch a newer owner
                    return
        def _end_pq(pq): loop.call_soon(pq.put_nowait, None)  # the sentinel travels the SAME FIFO path (call_soon) as the mic thread's call_soon_threadsafe puts: a chunk scheduled before the swap can never land after the sentinel
        async def _close_bounded(cl):
            try: await asyncio.wait_for(cl.close(), 3)
            except Exception: pass
        async def _retire(old):  # owned close: the old writer drains its queue to the sentinel (in-flight send awaited, bounded 3 s, else cancelled and logged), THEN the old client is closed
            with vg["lock"]:
                vg["ready"] = False
                if vg.get("pq") is not None: _end_pq(vg["pq"])
                vg["pq"] = None
            _t = pipe.get("task")
            if _t is not None and not _t.done():
                try: await asyncio.wait_for(asyncio.shield(_t), 3)
                except Exception:
                    _t.cancel(); log("voice: the old audio writer did not finish within 3 s; cancelled"); click_events.append({"gate": "old_writer_cancelled"})
            pipe["task"] = None
            await _close_bounded(old)
        def _abort_voice(why, ow=None):  # ONE owner of voice-session failure; ONLY the current owner may abort: an older failed/superseded attempt must not stop a newer mic/buffer
            if ow is not None and own[0] != ow:
                click_events.append({"gate": "abort_skipped_not_owner", "why": why}); log("voice: %s, but a newer edge owns the voice session; nothing of the newer session was touched" % why); return False
            retire_voice_context_writers()
            pending_ready = hover.get('ready')
            if pending_ready and not pending_ready.done(): pending_ready.set_result(False)
            pending_context = hover.get('future')
            if pending_context and not pending_context.done(): pending_context.set_result(None)
            hover.update(context=None, owner=None, defer_mic=False, future=None)
            own[0] += 1; pipe["tok"] += 1; gen[0] += 1; vs["n"] += 1; ing["parts"] = []
            with vg["lock"]:
                vg["ready"] = False; vg["buf"] = []
                if vg.get("pq") is not None: _end_pq(vg["pq"])
                vg["pq"] = None
            try: mic and mic.stop()
            except Exception: pass
            tainted[0] = True; q.put_nowait(("voice_stop", None)); click_events.append({"gate": "voice_aborted", "why": why}); _ret = True; log("voice: ABORTED (%s); mic stopped, queue discarded by an explicit abort, session will be replaced on the next turn" % why); return True
        def _off_edge():  # PTT-OFF edge (loop thread): invalidates the generation, the epoch AND the command edge, ends the audio gate (queued audio is flushed to the closing session, then the sentinel), so late old-provider callbacks and a delayed connect cannot publish after OFF
            retire_voice_context_writers()
            pending_ready = hover.get('ready')
            if pending_ready and not pending_ready.done(): pending_ready.set_result(False)
            pending_context = hover.get('future')
            if pending_context and not pending_context.done(): pending_context.set_result(None)
            hover.update(context=None, owner=None, defer_mic=False, future=None)
            tainted[0] = True  # callbacks on this connection now fail its generation gate; later typed/highlight needs a fresh one
            gen[0] += 1; vs["n"] += 1; edge["n"] += 1; own[0] += 1; ing["parts"] = []
            with vg["lock"]:
                vg["ready"] = False
                if vg.get("pq") is not None: _end_pq(vg["pq"])
                vg["pq"] = None
            q.put_nowait(("voice_stop", None))
        def _install_writer(cl):  # ONE non-await step: a fresh ordered queue gets the buffered audio first, then the gate opens (later chunks go to the same queue, behind it); returns the buffered count
            with vg["lock"]:
                _pq = asyncio.Queue(); _n = len(vg["buf"])
                for _b in vg["buf"]: _pq.put_nowait(_b)
                vg["buf"] = []; vg["pq"] = _pq; pipe["tok"] += 1; _tok = pipe["tok"]; vg["ready"] = True
            pipe["task"] = asyncio.ensure_future(_writer(cl, _pq, _tok, own[0])); return _n
        def _chunk(b):  # mic thread -> the gate: buffered IN ORDER while not ready, else the current session's ordered queue
            with vg["lock"]:  # queue selection AND scheduling happen under the SAME lock the sentinel swap uses, so a chunk is scheduled strictly before (and ordered ahead of) a later sentinel; a chunk after the swap goes to buf
                if ing.get("shutdown"): return
                if not vg["ready"] or vg["pq"] is None: vg["buf"].append(b); return
                loop.call_soon_threadsafe(vg["pq"].put_nowait, b)
        async def _hydrate(cl, seed):  # restore the conversation on a FRESH connection through the provider's documented route (clientContent turns with explicit roles, turnComplete false); a failure is LOUD and aborts, never a silently reduced context
            try:
                if hist and hasattr(cl, "send_history"):
                    await cl.send_history(list(hist)); click_events.append({"gate": "voice_history_rehydrated", "turns": len(hist), "chars": sum(len(_t2) for _r2, _t2 in hist)}); log("voice: rehydrated the fresh connection with %d prior turns (text only: no audio, screenshots, or model audio without transcript)" % len(hist))
                if seed and hover['defer_mic']:
                    native_future = hover.get('future'); native_owner = hover['owner']
                    if native_future is None: raise RuntimeError('missing native context reservation')
                    native_context = await asyncio.wait_for(asyncio.shield(native_future), 3)
                    if not native_context or native_owner != own[0] or hover.get('future') is not native_future:
                        raise RuntimeError('native context reservation retired')
                    hover['context'] = native_context
                with highlight_owner.lock:
                    committed, context_epoch = highlight_owner.context, highlight_owner.epoch
                if seed and committed and not (shared_gestures and pending_shared_context['token'] == context_epoch and pending_shared_context['owner'] == own[0]) and os.environ.get("TIPTOUR_VOICE_CTX", "seed") == "seed":
                    await cl.send_context(_hl.prompt(committed, ack=False))
                    with highlight_owner.lock:
                        if highlight_owner.epoch != context_epoch or highlight_owner.context is not committed:
                            raise RuntimeError('highlight context retired during seed')
                    log("voice: seeded latest highlight context silently (no turn)")
                hc = hover['context']
                if hover['defer_mic'] and (hover.get('epoch') != radial_binding['epoch'] or shared_gestures and radial_gesture['retired']): raise RuntimeError('radial intent replaced')
                if seed and hc:
                    if not hover_context.alive(hc, hover['owner']) or hover['owner'] != own[0]: raise RuntimeError('hover context expired or replaced')
                    await cl.send_context(hover_context.prompt(hc))
                    if hover['context'] is not hc or hover['owner'] != own[0] or shared_gestures and radial_gesture['retired'] or (hover['defer_mic'] and hover.get('epoch') != radial_binding['epoch']): raise RuntimeError('hover context superseded during seed')
                    click_events.append({'gate': 'hover_context_seeded'})
                return True
            except Exception as _hx:
                log("voice: continuity restore FAILED (%s); this fresh connection is discarded, nothing was silently degraded" % type(_hx).__name__); click_events.append({"gate": "voice_history_failed", "err": type(_hx).__name__}); return False
        _conn = [0]
        async def new_session():
            gen[0] += 1; vs["n"] += 1; ing["parts"] = []; oe = _mk_on_event(gen[0]); _conn[0] += 1
            if os.environ.get("TIPTOUR_TEST_MODE") == "1":  # TEST SEAMS only: TIPTOUR_FAKE_CONNECT_DELAY="N:seconds" delays the Nth connection; TIPTOUR_FAKE_CONNECT_FAIL="N" fails it
                _d = os.environ.get("TIPTOUR_FAKE_CONNECT_DELAY", "")
                if _d and int(_d.split(":")[0]) == _conn[0]: await asyncio.sleep(float(_d.split(":")[1]))
                if os.environ.get("TIPTOUR_FAKE_CONNECT_FAIL", "") == str(_conn[0]): raise RuntimeError("test seam: connection %d refused" % _conn[0])  # a replaced session also starts a new voice epoch
            if os.environ.get("TIPTOUR_CLIENT_FACTORY") and os.environ.get("TIPTOUR_TEST_MODE") == "1":  # TEST SEAM (needs TIPTOUR_TEST_MODE=1 too): "module:callable(on_event, loop, log)" returns a stand-in client (see tests/fake_client.py); never set in normal use
                import importlib; _m, _f = os.environ["TIPTOUR_CLIENT_FACTORY"].split(":")
                return getattr(importlib.import_module(_m), _f)(oe, loop, log), 0
            return await connect_with_pool(pool, lambda: LiveClient(oe), log)
        client, key = await new_session()
        full, jpeg, size = await asyncio.to_thread(lambda: grab())
        # grab on GTK thread-safe? PIL uses its own X connection, fine.
        stream_on = [True]
        resolving = {"n": 0}
        stream_state = {"suppressed": False, "hash": None, "sent": 0, "skipped": {"suppressed": 0, "plan_active": 0, "same_scene": 0}}
        def _dhash(jpg):  # Mac ScreenshotPerceptualHash: 9x8 grayscale, left>right bits, same scene = hamming <= 5 (X11 uses PIL resize; CoreGraphics low-interpolation downscale differs slightly: OS adaptation)
            from PIL import Image as _I; import io as _io
            px = list(_I.open(_io.BytesIO(jpg)).convert("L").resize((9, 8), _I.BILINEAR).getdata()); h = 0
            for r in range(8):
                for c in range(8):
                    if px[r * 9 + c] > px[r * 9 + c + 1]: h |= 1 << (r * 8 + c)
            return h
        def _plan_active(): return bool(cur.get("armed") or cur.get("paused") or gate["turn"] or gate["replay"] or resolving["n"] > 0 or (hl.get("obs_task") is not None and not hl["obs_task"].done()))  # Mac: WorkflowRunner.shared.activePlan != nil
        def _goal_live():  # a plan is LIVE (Mac WorkflowRunner.activePlan != nil) only while a target is armed/paused, a resolve is running, or an observe/advance/replay task is pending. NOT gate['turn']/gate['replay'] (those are true for every ask) - a completed plan is not live, so its goal may be submitted again
            _ob = hl.get("obs_task"); _tk = hl.get("task")
            return bool(cur.get("armed") or cur.get("paused") or resolving["n"] > 0 or (_ob is not None and not _ob.done()) or (_tk is not None and not _tk.done()))
        async def stream_frames():  # Mac GeminiLiveSession.captureAndProcessFrameForGemini: 3.0s timer; skip while suppressed-until-user-speaks or a plan is active; perceptual-hash dedup; else send
            while stream_on[0]:
                try:
                    if stream_state["suppressed"]: stream_state["skipped"]["suppressed"] += 1
                    elif shell_busy(): pass  # do not hide an interactive tray/settings for idle streaming
                    elif _plan_active(): stream_state["skipped"]["plan_active"] += 1
                    else:
                        _stream_tok=plan_tok["n"]
                        _, j, _ = await asyncio.to_thread(lambda: capture_clean(fast=True))
                        if _stream_tok != plan_tok["n"] or _plan_active() or shell_busy():continue
                        h = _dhash(j); lh = stream_state["hash"]
                        if lh is not None and bin(lh ^ h).count("1") <= 5: stream_state["skipped"]["same_scene"] += 1
                        else: stream_state["hash"] = h; stream_state["sent"] += 1; await client.send_screenshot(j); log("stream frame sent (idle context)", stream_state["sent"], "bytes", len(j)); (open(os.path.join(a.out, "stream-%d.jpg" % stream_state["sent"]), "wb").write(j) if getattr(a, "out", None) else None)
                except Exception as e: log('stream error', type(e).__name__)
                await asyncio.sleep(float(os.environ.get("TIPTOUR_STREAM_INTERVAL", "3.0")))
        stream_task = asyncio.create_task(stream_frames()) if os.environ.get('TIPTOUR_STREAM', '1') == '1' else None
        await asyncio.sleep(2.0 if stream_task else 0)
        serve_q = asyncio.Queue()
        typed_reply = {"active": False, "rev": None, "hash": None, "boundary": None, "generation": None}
        cmd_ep = {}; cmd_gen = {}; edge = {"n": 0}; shutdown = {"requested": False}
        radial_binding = {"epoch": 0, "worker": None, "context_worker": None, "pending": False}
        hover = {"context": None, "owner": None, "defer_mic": False, "epoch": None, "future": None}
        pending_shared_context = {'token': None, 'owner': None}
        from . import hover_context
        highlight_phase = {'token': None}
        shared_context_tasks = set()
        async def send_shared_highlight(token, session_owner, ready, retired):
            # This is a context writer only. The voice body remains the only
            # provider-event consumer; an unrelated turnComplete is never an ack.
            future = highlight_owner.take(token)
            if not future or not highlight_owner.valid(token): return
            try:
                ctx, ask_chord = await asyncio.wait_for(asyncio.wrap_future(future), 40)
                if not highlight_owner.valid(token) or ctx is None: return
                if ask_chord:
                    log('highlight: ask chord, local only'); return
                if not highlight_owner.commit(token, ctx): return
                log('shared highlight context stored locally; delivery pending')
                if ready is not None and not await asyncio.wait_for(asyncio.shield(ready), 8): return
                if own[0] != session_owner: return
                generation = gen[0]; session_client = client
                accepted_bytes = False
                def owns_session():
                    return own[0] == session_owner and gen[0] == generation and client is session_client
                def live():
                    return highlight_owner.valid(token) and owns_session() and not ing.get('shutdown')
                if not live() or tainted[0]: return
                def hide_current():
                    if highlight_owner.valid(token):
                        highlight_owner.visible = False; hl['trail'].hide()
                on_gtk(hide_current)
                full, jpeg, size = await asyncio.to_thread(capture_clean, True, False, live)
                if not live(): return
                async def send(awaitable):
                    task = asyncio.ensure_future(awaitable)
                    def consume_finished(done):
                        if not done.cancelled(): done.exception()
                    task.add_done_callback(consume_finished)
                    cancelled = asyncio.shield(asyncio.wrap_future(highlight_owner.cancellation(token)))
                    try:
                        session_cancelled = asyncio.shield(retired)
                        done, _ = await asyncio.wait((task, cancelled, session_cancelled), return_when=asyncio.FIRST_COMPLETED)
                        if cancelled in done or session_cancelled in done or not live():
                            task.cancel(); await asyncio.wait((task,), timeout=.2)
                            if owns_session(): tainted[0] = True
                            return False
                        try: task.result()
                        except Exception:
                            if owns_session(): tainted[0] = True
                            raise
                        return True
                    finally:
                        cancelled.cancel()
                        if 'session_cancelled' in locals(): session_cancelled.cancel()
                        if not task.done(): task.cancel()
                if not await send(session_client.send_screenshot(jpeg)): return
                accepted_bytes = True
                if not await send(session_client.send_text(_hl.prompt(ctx, ack=True))): return
                if not live(): return
                results.append({'ask': '@highlight %d' % token, 'highlight': 'sent alongside voice (fresh screenshot + context prompt); acknowledgement requested, not independently correlated', 'rect': ctx['rect'], 'window': ctx.get('window')})
                log('highlight context sent alongside voice; acknowledgement stays on voice event stream')
            except Exception as exc:
                if 'accepted_bytes' in locals() and accepted_bytes and owns_session(): tainted[0] = True
                log('shared highlight context not delivered (%s)' % type(exc).__name__)
                click_events.append({'gate': 'shared_highlight_not_delivered', 'err': type(exc).__name__})
        def _enq(t, preserve_highlight=False):
            if shutdown['requested']: return
            if t == '@voice' and highlight_phase['token'] is not None and highlight_owner.valid(highlight_phase['token']):
                highlight_owner.invalidate(retire_context=False)
                clear_trail_owned()
            if not t.startswith('@') or t == '@voice' and not preserve_highlight:
                highlight_owner.invalidate(retire_context=False)
                clear_trail_owned()
            if t not in ('@voice', '@voice-next') and not t.startswith('@highlight '):
                radial_binding['epoch'] += 1; radial_binding['pending'] = False
                if t != '@voice-next':
                    if hover['defer_mic']: _abort_voice('pending hover request replaced')
                    hover.update(context=None, owner=None, defer_mic=False)
            if t == '@quit':
                shutdown['requested'] = True; ing['shutdown'] = True; shell_windows['closed'] = True
                highlight_owner.invalidate(close=True)
                hl['closed'].set()
                if hl['mon']: hl['mon'].stop()
                if hl['commit_queue']:
                    try: hl['commit_queue'].put_nowait(None)
                    except queue.Full: pass
                if hl['trail']: GLib.idle_add(hl['trail'].close)
                if ptt_monitor: ptt_monitor.stop()
                if shared_gestures:
                    shared_gestures.monitor.closed.set()
                    GLib.idle_add(shared_gestures.retire_all)
                if radial_preview:
                    if radial_preview.monitor: radial_preview.monitor.closed.set()
                    GLib.idle_add(radial_preview.hide)
                if ing.get('ready'): _stop_work('shutdown-ingress')
                if hl.get('readonly_worker'): hl['readonly_worker'].cancel_current()
                _off_edge()
                try: mic and mic.stop()
                except Exception: pass
                # Wake both typed and voice bodies, not only the FIFO reader.
                q.put_nowait(('closed', 'local shutdown'))
                while not serve_q.empty(): serve_q.get_nowait()
                arr['n'] += 1; serve_q.put_nowait((arr['n'], '@quit'))
                click_events.append({'gate': 'shutdown_at_ingress'})
                if stream_task: stream_task.cancel()
                for task in tuple(shared_context_tasks): task.cancel()
                run_task.cancel()  # owned active body: capture/connect/highlight/send waits unwind
                return
            if hl.get("readonly_worker"): hl["readonly_worker"].cancel_current()
            if ing.get("ready") and not t.startswith("@") and _norm_resp(t) in _STOP:  # typed/UI STOP at INGRESS: stops at receipt, ahead of any queued/long voice turn; not enqueued (a late consumer must not stop NEWER work)
                _stop_work("typed-ingress"); click_events.append({"gate": "typed_stop_at_ingress"}); return
            if ing.get('ready') and not t.startswith('@') and _norm_resp(t) not in (_YES | _NO | _STOP):
                request_boundary['n'] += 1  # revoke old voice candidate at meaningful typed ingress, before dequeue
            if ing.get("ready") and not t.startswith("@") and prop["state"] == "approved" and bool(_norm_resp(t)) and _norm_resp(t) not in (_YES | _NO | _STOP):
                _revoke_approved("new typed request at ingress")
            if t in ("@voice", "@voice-next"):
                voice_command_boundaries[arr["n"] + 1] = request_boundary["n"]
            if t == "@voice":
                pending_shared_context.update(token=None, owner=None)
                retire_voice_context_writers()
                voice_cancel['future'] = loop.create_future()
                own[0] += 1
                with vg["lock"]:
                    vg["ready"] = False  # the old session's gate closes AT THE EDGE; the old queue gets its sentinel (it FLUSHES to the closing session first), new chunks buffer (in order) for the new session
                    if vg.get("pq") is not None: _end_pq(vg["pq"])
                    vg["pq"] = None
                gen[0] += 1; vs["n"] += 1;  # the old generation is invalidated AT THE EDGE (before any close/await): its queued or late callbacks fail g==gen
            if t == "@voice":  ing["parts"] = []; cmd_ep[arr["n"] + 1] = vs["n"]; edge["n"] += 1; cmd_gen[arr["n"] + 1] = edge["n"]  # PTT-on edge: a NEW voice session epoch, bound to THIS command (its arrival number), not to whatever is newest at dequeue
            if t.startswith("@highlight ") and shared_gestures and mic and (mic.active or hover["defer_mic"]):
                try: token = int(t.split()[1])
                except (ValueError, IndexError): return
                context_owner = own[0]
                task = asyncio.create_task(send_shared_highlight(token, context_owner, hover.get('ready'), voice_cancel['future']))
                pending_shared_context.update(token=token, owner=context_owner)
                shared_context_tasks.add(task)
                def completed(finished):
                    shared_context_tasks.discard(finished)
                    if pending_shared_context['token'] == token and pending_shared_context['owner'] == context_owner: pending_shared_context.update(token=None, owner=None)
                task.add_done_callback(completed)
                return
            # A typed confirmation can retire ONLY its already-rendered typed proposal reply.
            # No spoken partial/finality path changes; no provider event can mutate the retired record.
            _answer = _norm_resp(t) if not t.startswith('@') else None
            _control = t.split() if t.startswith(('@confirm ', '@confirmseparate ')) else []
            _rv = int(_control[1]) if len(_control) == 2 and _control[1].isdigit() else None
            if (ing.get('ready') and typed_reply['active'] and prop['state'] == 'pending' and
                    prop.get('displayed') and arr['n'] >= prop.get('shown', 10**12) and
                    typed_reply['rev'] == prop['rev'] and typed_reply['hash'] == prop['hash'] and
                    typed_reply['boundary'] == request_boundary['n'] == prop.get('boundary') and
                    typed_reply['generation'] == gen[0] and
                    (_answer in _YES or _rv == prop['rev'])):
                if _answer in _YES:
                    t = ('@confirmseparate ' if _answer in _SEPARATE_YES else '@confirm ') + str(prop['rev'])
                from .confirmation_watch import Watch
                try:
                    _watch = Watch(loop, typed_reply.get('native_owner') or {})
                except Exception:
                    _prop_clear('confirmation ownership watch unavailable'); return
                prop['confirmation_watch'] = _watch
                typed_reply['active'] = False
                gen[0] += 1; tainted[0] = True  # invalidate delivery BEFORE releasing the turn owner
                player and player.flush()
                q.put_nowait(('typed_proposal_reply_retired', {'turn':prop['turn'],'rev':prop['rev'],'hash':prop['hash'],'native_owner':typed_reply.get('native_owner')}))
                click_events.append({'gate':'typed_proposal_reply_retired','rev':prop['rev'],'hash':prop['hash'],'at':time.time()})
                log('confirmation: typed answer retired proposal reply rev %d' % prop['rev'])
            arr["n"] += 1; serve_q.put_nowait((arr["n"], t))  # every serve input gets an ARRIVAL number when it enters the queue (on the loop): approval binds to arrival AFTER the proposal display, never to dequeue order
        hl_post["fn"] = lambda t: loop.call_soon_threadsafe(_enq, t)  # the Confirm/Cancel buttons enter as @confirm/@cancel <rev>: the SAME revision-bound path as the serve control
        if a.serve:
            def _reader():
                import os as _o
                if not _o.path.exists(a.serve): _o.mkfifo(a.serve)
                while True:
                    with open(a.serve) as f:
                        for line in f:
                            line = line.strip()
                            if line in ('@skip', '@retry', '@resume'): _control_post(line[1:]); continue
                            if os.environ.get('TIPTOUR_TEST_MODE') == '1' and line.startswith('@ctl '):  # TEST SEAM (needs TIPTOUR_TEST_MODE=1): "@ctl skip <tok>" posts a control carrying an explicit panel token (a stale-panel press cannot be produced through the real panel button without a physical race)
                                try: _c, _t = line[5:].split(); _control_post(_c, int(_t))
                                except ValueError: log("bad @ctl line")
                                continue
                            if line == '@quit':
                                if mic is not None and os.environ.get('TIPTOUR_TEST_FAKE_MIC') == '1': mic.stop()  # test stub only
                                loop.call_soon_threadsafe(q.put_nowait, ('voice_stop', None))
                            if line == '@voice' and os.environ.get('TIPTOUR_TEST_FAKE_MIC') == '1' and mic is not None:  # test stub mic: the same on-edge reset+start as _ptt
                                with vg["lock"]: vg["ready"] = False; vg["buf"] = []
                                mic.start()  # a live voice turn must not block shutdown
                            if line.startswith('@chunk ') and os.environ.get('TIPTOUR_TEST_MODE') == '1':  # TEST SEAM: "@chunk N START" = N mic chunks (seq START..) delivered from a NON-loop thread, like the real mic thread
                                _a = line.split(); _n0, _s0 = int(_a[1]), int(_a[2])
                                def _feed(n=_n0, s0=_s0):
                                    import time as _tm
                                    for _k in range(n): _chunk((s0 + _k).to_bytes(4, "big") + b"\x00" * 28); _tm.sleep(0.05)
                                threading.Thread(target=_feed, daemon=True).start(); continue
                            if line == '@ptt-off' and os.environ.get('TIPTOUR_TEST_MODE') == '1':  # TEST SEAM only (needs TIPTOUR_TEST_MODE=1): the same effects as the real PTT-off edge in _ptt (epoch bump, ingress buffer reset, voice_stop)
                                (mic and mic.stop()); loop.call_soon_threadsafe(_off_edge); continue
                            if line: loop.call_soon_threadsafe(_enq, line)
            threading.Thread(target=_reader, daemon=True).start()
        player = mic = ptt_monitor = None
        if os.environ.get('TIPTOUR_TEST_MODE') == '1' and os.environ.get('TIPTOUR_TEST_FAKE_MIC') == '1':  # TEST SEAM (needs TIPTOUR_TEST_MODE=1): a stub mic so a voice turn (@voice) runs with a fake model and NO audio capture/STT
            import types as _ty; mic = _ty.SimpleNamespace(active=True); mic.start = lambda: setattr(mic, "active", True); mic.stop = lambda: setattr(mic, "active", False)  # stateful like the real Mic: start/stop toggle .active
        if a.voice:
            from . import voice as _v
            player = _v.Player(); _w = _v.echo_risk()
            if _w: log('voice warning: ' + _w)
            else: log('voice: source/sink names do not form a loopback; speaker-to-mic acoustic echo is NOT checked (use headphones or echo-cancel)')
            def _mic_error(why, generation):
                if ing.get('shutdown'): return
                if generation != mic.generation:
                    click_events.append({'gate': 'old_mic_error_rejected'}); return
                # Provider reconnects can change voice owner without replacing capture.
                # A failure of this native capture still aborts its current session.
                _abort_voice(why)
            mic = _v.Mic(_chunk, on_error=lambda why, generation: loop.call_soon_threadsafe(_mic_error, why, generation))
            def _ptt(preserve_highlight=False):  # Runs on the owned loop, atomically with shutdown ingress.
                if ing.get("shutdown"): return
                if mic.active: mic.stop(); loop.call_soon_threadsafe(_off_edge); log("voice: off")
                else:
                    with vg["lock"]: vg["ready"] = False; vg["buf"] = []
                    _enq("@voice", preserve_highlight=preserve_highlight)  # establish owner before starting the native capture
                    if hover["defer_mic"]:
                        hover["owner"] = own[0]; return
                    try: mic.start()
                    except OSError: _abort_voice('microphone could not start', own[0]); return
                    log("voice: on")
            if not a.radial_input:
                ptt_monitor = _v.PttMonitor(lambda: loop.call_soon_threadsafe(_ptt)); ptt_monitor.start()
            else:
                def invalidate_hover():
                    radial_binding['epoch'] += 1; radial_binding['pending'] = False
                    if hover['defer_mic']: _abort_voice('pending hover control')
                    hover.update(context=None, owner=None, defer_mic=False)
                def invalidate_shared(generation=None):
                    def apply():
                        if not ing.get('shutdown') and (generation is None or shared_gestures and generation == shared_gestures.monitor.generation):
                            invalidate_hover()
                    loop.call_soon_threadsafe(apply)
                radial_post['invalidate'] = invalidate_shared if shared_gestures else lambda generation=None: invalidate_hover()
                def _radial_select(option, point, gesture_key=None):
                    if shared_gestures and (not gesture_key or not shared_gestures.monitor.valid(gesture_key[0])): return
                    if ing.get('shutdown'): return
                    def newer_highlight():
                        return bool(shared_gestures and gesture_key and radial_gesture['highlight'] and radial_gesture['highlight'][0] == gesture_key[0] and radial_gesture['highlight'][1] > gesture_key[1])
                    was_pending = radial_binding['pending']
                    radial_binding['epoch'] += 1; epoch = radial_binding['epoch']; radial_binding['pending'] = False
                    def guarded_status(message):
                        GLib.idle_add(lambda: (radial_status(message), False)[1] if not ing.get('shutdown') and radial_binding['epoch'] == epoch and (not shared_gestures or gesture_key and shared_gestures.monitor.valid(gesture_key[0])) else False)
                    if option != 'speak' and (was_pending or hover['defer_mic']):
                        _abort_voice('pending Speak replaced by radial mode')
                    if option == 'speak':
                        # OFF never needs a target probe. ON refuses a different
                        # hovered/focused app rather than silently changing target.
                        if mic.active:
                            if ing.get('ready'): _stop_work('radial-speak', preserve_highlight=newer_highlight())
                            hover.update(context=None, owner=None, defer_mic=False)
                            _ptt(); guarded_status('Gemini voice stopped. Ctrl+Alt hotkey disabled in radial-input mode.'); return
                        if was_pending or hover['defer_mic']:
                            if ing.get('ready'): _stop_work('radial-speak', preserve_highlight=newer_highlight())
                            _abort_voice('pending radial Speak cancelled'); guarded_status('Pending Speak cancelled. No voice started.'); return
                        if ing.get('ready'): _stop_work('radial-speak', preserve_highlight=newer_highlight())
                        if os.environ.get('TIPTOUR_USE_ATSPI', '1') != '1':
                            hover.update(context=None, owner=None, defer_mic=False)
                            guarded_status('Speak context unavailable: AT-SPI lookup is disabled. No voice started.'); return
                        hover.update(context=None, owner=None, defer_mic=False)
                        if radial_binding['context_worker'] and radial_binding['context_worker'].is_alive():
                            guarded_status('Speak unavailable: context check still running.'); return
                        if radial_binding['worker'] and radial_binding['worker'].is_alive():
                            guarded_status('Speak unavailable: target check still running.'); return
                        from . import radial_target
                        native_future = loop.create_future()
                        hover.update(context=None, owner=None, defer_mic=True, epoch=epoch, future=native_future, ready=loop.create_future())
                        radial_binding['pending'] = True
                        _ptt(preserve_highlight=newer_highlight())
                        reserved_owner = hover['owner']
                        def current(): return not ing.get('shutdown') and hover['owner'] == reserved_owner and own[0] == reserved_owner and radial_binding['epoch'] == epoch and (not shared_gestures or gesture_key and shared_gestures.monitor.valid(gesture_key[0]))
                        def status(message):
                            guarded_status(message)
                        def accept(target, deadline):
                            if not current(): return
                            if not target or time.monotonic() >= deadline:
                                radial_binding['pending'] = False
                                _abort_voice('radial target unavailable', reserved_owner)
                                status('Speak refused: target unavailable or check expired. Focus the app under the cursor and try again. No voice started.'); return
                            def context_accept(ctx, expires):
                                if not current(): return
                                radial_binding['pending'] = False
                                if not ctx or time.monotonic() >= expires:
                                    _abort_voice('radial context unavailable', reserved_owner)
                                    status('Speak refused: native context unavailable or expired. No voice started.'); return
                                ctx['owner'] = reserved_owner
                                if not native_future.done(): native_future.set_result(ctx)
                                status('Gemini context captured. Connecting before microphone starts. Radial Speak cancels pending start.')
                            radial_binding['pending'] = True
                            radial_binding['context_worker'] = hover_context.request(point, target, epoch, current,
                                lambda ctx, expires: loop.call_soon_threadsafe(context_accept, ctx, expires))
                        radial_binding['pending'] = True
                        radial_binding['worker'] = radial_target.request(point, lambda target, deadline: loop.call_soon_threadsafe(accept, target, deadline), current)
                    elif option == 'type':
                        guarded_status('Type unavailable: pinned Mac text mode requires JEV. No provider was changed.')
                    elif option == 'highlight':
                        guarded_status('Radial Highlight target capture is not connected. Ctrl+Shift painting is enabled in this combined mode.' if shared_gestures else 'Highlight unavailable in this configuration: its monitor is disabled. Restart without radial input and enable --highlight to use it.')
                    click_events.append({'gate': 'radial_dispatch', 'option': option})
                radial_post['fn'] = lambda option, point, key=None: loop.call_soon_threadsafe(_radial_select, option, point, key)
                log('radial input: Ctrl+Alt voice hotkey disabled; Speak toggles existing Gemini voice; Type unsupported without JEV; ' + ('shared Ctrl+Shift highlight enabled; radial Highlight target capture not connected' if shared_gestures else 'highlight monitor disabled'))
        async def _asks():
            if not a.serve:
                for t in a.ask: yield t
            else:
                while True:
                    gate['turn'] = False  # consumer asked for the next item => the previous turn body has finished
                    _sq, t = await serve_q.get(); gate['arrival'] = _sq
                    # NEW UTTERANCE IS NOT A TRANSITION (Mac CompanionManager/WorkflowRunner 6e97782): nothing is cancelled here and an in-flight replay/advance is not awaited. The old plan keeps running until a toolCall supersedes it (the accept path above stops it: cancel + disarm + plan_tok bump) or a control (skip/stop/retry/resume) replaces it; stale results are refused by plan_tok / generation checks.
                    gate['turn'] = True
                    if t == "@quit":
                        return
                    yield t
        def _own_rec(r, oc, yolo_, ocr_, mp, pc=None): return {"pin": oc["seq"], "perc": mp, "pair": oc["pair"], "size": r[2], "yolo": yolo_, "ocr": ocr_, "cache": pc}  # cache = this perception pass's PRIVATE LocalPerceptionTargetCache (same class/TTL/update as the global one); never replaced by a later pass
        def _gens(own): return {"own_pin": own["pin"], "own_perc": own["perc"], "applied_pin": _pin_seq["applied"], "applied_perc": _perc_seq["applied"]} if own else None  # LABELS ONLY: a newer global generation does not refuse; this resolve reads ITS OWN snapshot and the real screen-stale guard decides
        def _local_resolve_owned(lab, own): return _local_resolve(lab, own["cache"] if own else None)
        _range_consumed = set()  # (approved revision, canonical saved-range): native pending range is consumed ONCE per plan
        async def _transition_ready(name, token, timeout=8):
            from .app_transition import context_matches
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if token != plan_tok['n'] or prop.get('state') != 'approved': return None
                try:
                    context = await asyncio.to_thread(atspi_resolver.active_context, 1)
                    if token != plan_tok['n'] or prop.get('state') != 'approved': return None
                    if context_matches(context, name): return context
                except Exception: pass
                await asyncio.sleep(.1)
            return None
        async def _execution_app(args, idx, own):
            from .app_transition import destination, context_matches, same_window
            transition, name = destination(args, idx)
            if transition is None: return args.get('app')
            proof = last_call.get('transition_proofs', {}).get(transition)
            token = plan_tok['n']
            if not proof or not atspi_resolver: raise RuntimeError('approved app transition has no verified destination')
            context = await asyncio.to_thread(atspi_resolver.active_context, 2)
            if token != plan_tok['n'] or not _approved_step(args, idx, args['steps'][idx]):
                raise RuntimeError('app transition ownership revoked')
            if not context_matches(context, name, own['pair'][0] if own else None) or not same_window(proof, context):
                raise RuntimeError('destination window changed or does not match approved app')
            last_call.setdefault('execution_contexts', {})[idx] = context
            return context['app']
        async def _pointer_arrival(point, label, token):
            """Visual arrival is an execution barrier, never a new authorization."""
            ready = loop.create_future()
            def drawn():
                if not ready.done():ready.set_result(True)
            def start():
                if token == plan_tok['n']:
                    overlay.point_to(point[0], point[1], label, on_arrived=lambda:loop.call_soon_threadsafe(drawn))
                return False
            GLib.idle_add(start)
            end=time.monotonic()+6
            try:
                while not ready.done():
                    if token != plan_tok['n'] or time.monotonic()>end: return False
                    await asyncio.sleep(.02)
                if token != plan_tok['n']:return False
                click_events.append({'pointer':'arrived_drawn','point':point,'at':time.time(),'token':token})
                return True
            finally:
                if not ready.done():ready.cancel()
        async def _run_action_step(step, args, text, idx, _steps, own=None, execution_app=None):
            """Mac WorkflowRunner executeOpenApplicationStep/executeOpenURLStep/executeKeyboardShortcutStep/executePressKeyStep/executeTypeTextStep/executeSetValueStep/executeScrollStep: NO pointing. Without --act the Mac pauses (actionRequiresAutopilot); here the step is NOT performed and the plan stops there. With --act it runs only as the exact current step of the displayed, user-approved plan; success advances to the next step, failure stops the plan at this step (Mac currentStepResolutionFailureLabel)."""
            from . import actions as _act
            t = step.get("type"); tool_seen = {"label": step.get("label"), "source": "ACTION_STEP", "step_type": t}
            _ev = lambda d: click_events.append(dict(d, step_type=t, step_index=idx))
            if not a.act:
                pause_rs['r'] = 'actionRequiresAutopilot'; cur['paused'] = 'actionRequiresAutopilot'
                _ev({"action": "requires_act", "performed": False}); log("action step %s NOT performed: action mode (--act) is OFF; the plan stops here (Mac: pause actionRequiresAutopilot)" % t)
                return {"ok": False, "status": "action_requires_act", "note": "This step is an action (%s). Action mode is OFF, so nothing was done. Tell the user it was not performed." % t}, tool_seen
            if not _approved_step(args, idx, step):
                _ev({"action": "not_approved", "performed": False}); log("action step %s NOT performed: the current exact step is not approved" % t)
                return {"ok": False, "status": "action_not_approved", "note": "This exact current step has no valid app-owned approval, so nothing was done."}, tool_seen
            tc = step.get("targetContext")
            if (tc in ("currentSelection", "currentHighlight") and not step.get("_native_range")) or (tc == "focusedElement" and t not in ("type", "setValue")):
                _ev({"action": "refused_target_context", "performed": False}); log("action step %s NOT performed: targetContext %s is not implemented for this step type on Linux (no native selection binding); nothing sent" % (t, tc))
                return {"ok": False, "status": "action_target_context_unsupported", "note": "targetContext %s is not supported for this action on Linux; nothing was done." % tc}, tool_seen
            if t not in ("openApp", "openURL") and execution_app and atspi_resolver:  # Mac modal gate: a blocking dialog in the plan's app pauses the plan instead of sending keys into it
                _ms, _mt = await asyncio.to_thread(atspi_resolver.modal_title, execution_app)
                log("modal check (action step): %s" % ("dialog present" if _mt is not None else ("none" if _ms == "ok" else "unavailable (not treated as 'no dialog')")))
                if _ms != "ok":
                    _ev({"action": "modal_unavailable", "performed": False}); pause_rs['r'] = 'modalStateUnavailable'
                    return {"ok": False, "status": "action_modal_unavailable", "note": "Modal state could not be verified; nothing sent."}, tool_seen
                if _mt is not None:
                    _ev({"pause": "modalDialogPresented", "title": _mt, "performed": False}); pause_rs['r'] = 'modalDialogPresented'
                    return {"ok": False, "status": "action_paused_modal", "note": "A dialog appeared%s; nothing was sent. Deal with it, then ask again." % (": " + _mt if _mt else "")}, tool_seen
            # Action steps must not bypass screenshot/window ownership.
            if own: _action_ident = own["pair"][0]
            else:
                with _pin_lk: _action_ident = frame_id.get("v")
            if not _action_ident or ident() != _action_ident:
                _ev({"action": "stale_identity", "performed": False})
                return {"ok": False, "status": "action_stale_identity", "note": "Focused window changed since the plan frame; nothing sent."}, tool_seen
            _exec_step = dict(step)
            _range_key = (last_call.get("rev"), json.dumps(step.get("_native_range"), sort_keys=True)) if step.get("_native_range") else None
            if _range_key in _range_consumed: _exec_step.pop("_native_range", None)
            if not _approved_step(args, idx, step):
                return {"ok": False, "status": "action_not_approved", "note": "Approval changed while checking the target; nothing sent."}, tool_seen
            tok0 = plan_tok["n"]; _cev = threading.Event()
            _destination = last_call.get('execution_contexts', {}).get(idx)
            _expected = (str(_destination['x11_client_id']), _destination['pid']) if _destination else None
            _nav = None
            _nav_existing = last_call.get('navigation_observer')
            if _nav_existing:
                _browser_ui = t == 'type' and idx > 0 and _steps[idx-1].get('type') == 'keyboardShortcut' and _steps[idx-1].get('label','').lower() in ('ctrl+f','control+f','cmd+f','command+f')
                _find_enter = t == 'pressKey' and step.get('label','').lower() in ('enter','return') and bool(last_call.get('browser_find_recipient'))
                if not await _nav_existing.check(browser_ui=_browser_ui or _find_enter) or not _approved_step(args, idx, step):
                    _ev({'action':'navigation_owner_refused','performed':False})
                    return {'ok':False,'status':'navigation_partial','error':'Owned browser tab/document changed; no action sent.'}, tool_seen
                _expected = _nav_existing.owner
                if t == 'keyboardShortcut' and step.get('label','').lower() in ('ctrl+f','control+f','cmd+f','command+f'): _nav_existing.allow_find_blur = True
                if _find_enter: _exec_step['_expected_focus'] = last_call['browser_find_recipient']
                if _browser_ui:
                    _find = last_call.get('browser_find_recipient')
                    if not _find: return {'ok':False,'status':'find_partial','error':'Find field was not bound after approved shortcut.'}, tool_seen
                    _exec_step['_browser_find'] = _find
            if t == 'pressKey' and step.get('label','').lower() in ('enter','return') and not last_call.get('browser_find_recipient'):
                from .navigation import prepare
                try: _nav = await prepare()
                except Exception: _nav = None
                if _nav:
                    _navigation_observers.append(_nav)
                    _expected = _nav.owner
                    _return_focus = await asyncio.to_thread(_act.focus_info, execution_app, False)
                    if not _return_focus.get('ok'):
                        await _nav.close(); return {'ok':False,'status':'navigation_partial','error':'Original Enter recipient unavailable.'}, tool_seen
                    _exec_step['_expected_focus'] = _return_focus['identity']
                    async def _pre_dispatch(_observer=_nav):
                        try:return bool(tok0 == plan_tok['n'] and _approved_step(args,idx,step) and await _observer.preflight())
                        except Exception:return False
                    def _form_guard():
                        try:return asyncio.run_coroutine_threadsafe(_pre_dispatch(),loop).result(timeout=4)
                        except Exception:return False
                    _exec_step['_navigation_guard'] = _form_guard
                if not _approved_step(args, idx, step):
                    if _nav: await _nav.close()
                    return {'ok':False,'status':'not_approved'}, tool_seen
            if t in ('type','setValue'):
                _field = await asyncio.to_thread(_act.focus_info, execution_app, False)
                _rect = _field.get('element_rect') if _field.get('ok') else None
                if not _rect or _field.get('password'):
                    return {'ok':False,'status':'pointer_recipient_unavailable','error':'Verified field geometry unavailable; no text sent.'}, tool_seen
                _exec_step['_expected_focus'] = _field['identity']
                _point = (_rect[0]+_rect[2]/2, _rect[1]+_rect[3]/2)
                if not await _pointer_arrival(_point, step.get('label') or 'Text field', tok0):
                    return {'ok':False,'status':'pointer_arrival_revoked'}, tool_seen
                _fresh = await asyncio.to_thread(_act.focus_info, execution_app, False)
                if (tok0 != plan_tok['n'] or not _approved_step(args,idx,step) or ident()!=_action_ident or
                        not _fresh.get('ok') or _fresh.get('identity')!=_field['identity'] or _fresh.get('element_rect')!=_rect):
                    return {'ok':False,'status':'pointer_recipient_changed','error':'Field changed while pointer moved; no text sent.'}, tool_seen
            try: resp = await asyncio.to_thread(_act.execute, _exec_step, None, execution_app, None, _cev, None, _expected)
            except BaseException: _cev.set(); log("action step %s cancelled (stop/supersede): worker told to stop before its next OS call" % t); raise  # STOP/supersede cancels the await; the worker checks this event before EVERY OS side effect
            log("action executed (%s), ok=%s" % (t, resp.get("ok"))); dlog("action", json.dumps(resp)); _ev({"action": "performed" if resp.get("ok") else "failed", "performed": bool(resp.get("ok")), "detail": resp.get("detail") or resp.get("error")})
            if resp.get('ok') and _nav_existing and t == 'keyboardShortcut' and step.get('label','').lower() in ('ctrl+f','control+f','cmd+f','command+f'):
                _find = await asyncio.to_thread(_act.focus_info, execution_app, False)
                if (tok0 != plan_tok['n'] or not _approved_step(args, idx, step) or not await _nav_existing.check(browser_ui=True) or
                        not _find.get('ok') or _find.get('name') != 'Find' or _find.get('role') != 'entry' or
                        not _find.get('editable_state') or _find.get('password') or _find.get('document_rect') is not None):
                    return {'ok':False,'status':'find_partial','error':'Find shortcut performed but exact field not verified.'}, tool_seen
                last_call['browser_find_recipient'] = _find['identity']
            if _nav:
                if resp.get('ok'):
                    try:
                        _proof = await _nav.settle(lambda: tok0 == plan_tok['n'] and _approved_step(args, idx, step))
                        last_call['navigation_observer'] = _nav
                        _ev({'action':'navigation_verified','proof':_proof})
                    except Exception as exc:
                        await _nav.close()
                        _ev({'action':'navigation_partial','performed':True,'error':str(exc)})
                        log('Approved Enter performed, navigation not verified: PARTIAL, not complete; ' + str(exc))
                        return {'ok':False,'status':'navigation_partial','error':str(exc)}, tool_seen
                else: await _nav.close()
            if resp.get("ok") and t == 'openApp':
                destination_context = await _transition_ready(step.get('label'), tok0)
                if destination_context is None:
                    pause_rs['r'] = 'destinationUnavailable'; cur['paused'] = 'destinationUnavailable'
                    _ev({'action': 'transition_partial', 'performed': True})
                    log('App launch requested, but destination not verified; original task is PARTIAL, not complete')
                    return {'ok': False, 'status': 'transition_partial', 'error': 'Destination not verified; no following action sent.'}, tool_seen
                if plan_tok['n'] != tok0 or not _approved_step(args, idx, step):
                    return {'ok': False, 'status': 'transition_revoked'}, tool_seen
                last_call.setdefault('transition_proofs', {})[idx] = destination_context
                _ev({'action': 'transition_verified', 'app': destination_context['app'], 'pid': destination_context['pid'], 'x11_client_id': destination_context['x11_client_id']})
            if resp.get("ok") and plan_tok["n"] == tok0:
                if _range_key: _range_consumed.add(_range_key)
                last_call["idx"] = idx
                hl["obs_task"] = asyncio.ensure_future(_advance_step("observe", tok0))  # Mac advanceUsingCachedHandlers after a successful action (no pointer, no 650 ms hold)
            return resp, tool_seen
        class _ResolutionDeadline(BaseException): pass
        async def _resolve_step(v, args, text, idx=0, own=None, post_click=False):  # counts in-progress resolves so an observe auto-advance (650ms) never overlaps one, without waiting for the whole live turn (Mac has no such wait: @MainActor + token)
            resolving["n"] += 1
            try:
                steps = args.get("steps") or [{}]
                step = steps[idx] if idx < len(steps) else {}
                no_hint = bool(step.get("label")) and not any(step.get(k) for k in ("point_2d", "box_2d", "target_id", "targetID")) and step.get("target_mark") is None and step.get("targetMark") is None
                retryable = no_hint and (step.get("type") or "click") in ("click", "rightClick", "doubleClick", "observe")
                deadline = time.monotonic() + 3.5
                attempts = 0
                operation = {"token": plan_tok["n"]}
                def eligible(): return operation["token"] == plan_tok["n"]
                click_events.append({"resolution_budget_start": time.monotonic(), "budget_s": 3.5, "no_hint": retryable, "post_click": post_click})
                async def read(fn, *a, **kw):
                    if not eligible(): raise asyncio.CancelledError()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0: raise _ResolutionDeadline()
                    if fn is atspi_resolver.resolve:
                        kw["timeout"] = min(float(kw.get("timeout", remaining)), remaining)
                    try:
                        value = await asyncio.wait_for(asyncio.to_thread(fn, *a, **kw), remaining)
                        if not eligible(): raise asyncio.CancelledError()
                        return value
                    except asyncio.TimeoutError: raise _ResolutionDeadline()
                while True:
                    attempts += 1
                    try:
                        result = await _resolve_step_inner(v, args, text, idx, own, defer_missing=retryable, read=read if retryable else asyncio.to_thread, operation=operation)
                        if result[0].get("status") != "unresolved_no_hint": return result
                    except _ResolutionDeadline:
                        pass
                    if not eligible():
                        return {"ok": False, "status": "not_pointed", "error": "superseded resolution"}, {"source": "REFUSED"}
                    if time.monotonic() >= deadline:
                        label = step.get("label") or "target"
                        plan_tok["n"] += 1  # revoke timed-out read/capture callbacks before publishing this pause episode
                        operation["token"] = plan_tok["n"]
                        pause_rs["r"] = "resolutionFailed"
                        cur.update(label=label, armed=False, paused="resolutionFailed")
                        ov["hidden"] = True; clicks.disarm(); GLib.idle_add(overlay.retire)
                        token = plan_tok["n"]
                        GLib.idle_add(lambda: (panel.show_at(100, 100, 'Could not find "' + label + '". Retry or skip?', token) if token == plan_tok["n"] else None) and False)
                        click_events.append({"resolution_failed": label, "attempts": attempts, "budget_s": 3.5, "elapsed_s": round(3.5 + time.monotonic() - deadline, 4)})
                        log("resolution failed: could not find %r within 3.5s (%d attempts); Retry or Skip" % (label, attempts))
                        return {"ok": False, "status": "resolution_failed", "error": "Target not found within the resolution budget"}, {"source": "REFUSED", "refused": "resolution budget exhausted"}
                    token = plan_tok["n"]
                    await asyncio.sleep(0.2)
                    if token != plan_tok["n"]: return {"ok": False, "status": "not_pointed", "error": "superseded during resolution retry"}, {"source": "REFUSED"}
                    try:
                        cap, oc = await read(capture_pinned)
                        yy, oo, mp, pc = await read(_perceive, cap[0], True)
                        own = _own_rec(cap, oc, yy, oo, mp, pc)
                    except _ResolutionDeadline:
                        continue
                    if token != plan_tok["n"]: return {"ok": False, "status": "not_pointed", "error": "superseded during resolution capture"}, {"source": "REFUSED"}
            finally: resolving["n"] -= 1
        async def _resolve_step_inner(v, args, text, idx=0, own=None, defer_missing=False, read=asyncio.to_thread, operation=None):
            _size = own["size"] if own else size; _yolo = own["yolo"] if own else yolo; _ocr = own["ocr"] if own else ocr_el  # this resolve's OWN capture/perception (not the shared nonlocals another capture may have replaced)
            tool_seen = None; resp = None
            _steps = args.get("steps") or [{}]
            while idx < len(_steps) and _steps[idx].get("type") == "waitForState":  # Mac WorkflowRunner.swift:680-681: .waitForState is "not yet implemented, skipping" -> advance, never resolved or pointed
                log('[Workflow] step "%s" is .waitForState - not yet implemented, skipping' % (_steps[idx].get("label") or _steps[idx].get("hint") or "")); idx += 1
                if last_call: last_call["idx"] = idx
            if idx >= len(_steps):  # nothing left after the skipped step(s): the plan is complete, no pointer is placed
                with glock:
                    plan_tok["n"] += 1; clicks.disarm(); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire); cur['armed'] = False; cur['paused'] = None; pause_rs['r'] = None; _clear_last(); PREV_STEP_POINT['p'] = None
                click_events.append({"wait_for_state": "skipped", "plan_complete": True})
                return {"ok": True, "status": "wait_for_state_skipped", "note": "waitForState is not implemented (skipped, as on the Mac); no pointer was placed"}, None
            step = _steps[idx]
            if not _approved_step(args, idx, step):
                click_events.append({"gate": "step_approval_refused", "step_index": idx})
                return {"ok": False, "status": "not_executed", "error": "Exact current plan step is no longer approved"}, {"source": "REFUSED"}
            _owned_navigation = last_call.get('navigation_observer')
            if _owned_navigation and (step.get('type') or 'click') not in __import__('tiptour_linux.actions',fromlist=['x']).ACTION_TYPES:
                if not await _owned_navigation.check() or not _approved_step(args,idx,step):
                    return {'ok':False,'status':'navigation_partial','error':'Owned browser document changed; no target resolved.'}, {'source':'REFUSED'}
            try: execution_app = await _execution_app(args, idx, own)
            except Exception as exc:
                pause_rs['r'] = 'destinationUnavailable'; cur['paused'] = 'destinationUnavailable'
                click_events.append({'gate': 'destination_context_refused', 'step_index': idx, 'error': str(exc)})
                return {'ok': False, 'status': 'transition_partial', 'error': str(exc)}, {'source': 'REFUSED'}
            if (step.get("type") or "click") in __import__("tiptour_linux.actions", fromlist=["x"]).ACTION_TYPES: return await _run_action_step(step, args, text, idx, _steps, own, execution_app)
            from .app_transition import destination
            _destination_step = destination(args, idx)[0] is not None
            pt = None if _destination_step else step.get("point_2d")
            if not _destination_step and not pt and step.get("box_2d"):
                y1, x1, y2, x2 = step["box_2d"]; pt = [(y1 + y2) // 2, (x1 + x2) // 2]
            nohint = False
            if not pt and (step.get("label") or "").strip(): pt = [500, 500]; nohint = True  # Mac resolves a step WITHOUT a spatial hint label-only (AX -> CDP -> local cache tier 3); the placeholder point is never used: unresolved + nohint = refuse
            if pt:
                px = norm_to_px(pt, _size); model_px = px; src = "model_box"
                lab = step.get("label", ""); done = False; ambiguous = 0; refuse = None; bound_rect = None; arm_rect = None; arm_app = None
                if step.get("targetContext") in ("currentSelection", "focusedElement"): refuse = "targetContext %s is not implemented on Linux yet (native selection / focused-element binding is a known gap vs the Mac); not pointing" % step.get("targetContext")  # explicit, never silently ignored
                clicks.disarm(); plan_tok["n"] += 1; _gen0 = plan_tok["n"]
                if operation is not None: operation["token"] = _gen0  # a skip/cancel/new ask/new target bumps plan_tok: anything resolved under an older generation must not arm or render
                if own: _fv, _fi = own["pair"]  # the frame THIS request/replay actually captured (the model saw this one)
                else:
                    with _pin_lk: _fv, _fi = frame_id.get('v'), frame_id.get('img')  # ONE consistent (identity, image) pair: the capture worker writes both under _pin_lk
                now_id = ident(); dlog('identity pinned=%r now=%r' % (_fv, now_id))
                if own and (_pin_seq["applied"] != own["pin"] or _perc_seq["applied"] != own["perc"]):  # evidence only (no refusal): this resolve proceeds on its OWN frame pair + own cache snapshot
                    click_events.append(dict({"gate": "own_generation_resolve", "identity_changed": bool(_fv and now_id != _fv)}, **_gens(own))); log("resolve on OWN generation (pin/perc %s/%s; shared latest %s/%s)" % (own["pin"], own["perc"], _pin_seq["applied"], _perc_seq["applied"]))
                if _fv and now_id != _fv:
                    refuse = "focused window, title or geometry changed since the screenshot (%s -> %s); ask again" % (_fv[2], now_id[2]); done = True
                if not done and _fi is not None and os.environ.get("TIPTOUR_STALE_FRAME_GUARD", "1") == "1":  # same window can still show different content (voice turns: frame is taken at turn start, speech can come much later)
                    try:
                        _now = await read(lambda: capture_clean()[0]); _fr = changed_fraction(_fi, _now); _tf = (0.0 if nohint else target_changed_fraction(_fi, _now, px))
                        log("stale-frame check: %.1f%% of frame pixels, %.1f%% around the target changed since the pinned frame (heuristic, not proof of freshness)" % (_fr * 100, _tf * 100))
                        if _fr > float(os.environ.get("TIPTOUR_STALE_FRAME_MAX", "0.03")) or _tf > float(os.environ.get("TIPTOUR_STALE_TARGET_MAX", "0.06")): refuse = "the screen content changed since the screenshot this answer was based on (frame %.0f%%, around target %.0f%%); ask again" % (_fr * 100, _tf * 100); done = True
                    except Exception as _e: log("stale-frame check unavailable: %s" % type(_e).__name__)
                # Mac modal gate (WorkflowRunner :586): if the plan's target app currently shows a blocking dialog, pause instead of resolving (pause reason modalDialogPresented, text "dialog appeared: <title>")
                if not done and not refuse and execution_app and atspi_resolver:
                    _ms, _mt = await read(atspi_resolver.modal_title, execution_app)
                    log("modal check: %s" % ("dialog present" if _mt is not None else ("none" if _ms == "ok" else "unavailable (not treated as 'no dialog')")))
                    if _ms != "ok": refuse = "modal state unavailable; not pointing or clicking"; done = True; pause_rs['r'] = 'modalStateUnavailable'
                    if _mt is not None: refuse = "dialog appeared" + (": " + _mt if _mt else "") + " (paused; deal with it, then ask again)"; done = True; click_events.append({"pause": "modalDialogPresented", "title": _mt}); pause_rs['r'] = 'modalDialogPresented'
                if not done and not refuse and atspi_resolver:
                    _cs,_cm=await read(atspi_resolver.coordinate_status,execution_app or now_id[1])
                    dlog("native coordinate mapping",json.dumps({"status":_cs,"mapping":_cm}))
                    if _cs!="ok":refuse="unsupported or unavailable native/X11 coordinate mapping; no pointer or click";done=True
                # Mac ElementResolver.exactLocalTargetResolution (:95): an explicit target_id / target_mark in the plan step binds to the cache entry first
                _tid = step.get("target_id") or step.get("targetID"); _tmk = step.get("target_mark") if step.get("target_mark") is not None else step.get("targetMark")
                if not done and (_tid or _tmk is not None):
                    _tt = (own["cache"] if own and own.get("cache") else TARGET_CACHE).current_targets(); _m = next((t for t in _tt if (t["id"] == str(_tid).strip() if _tid and str(_tid).strip() else t["mark"] == _tmk)), None)
                    if _m: px = (_half_up(_m["global_center"][0]), _half_up(_m["global_center"][1])); src = "target_cache:exact(%s)" % _m["source"]; done = True; arm_rect = (_m["global_box"][0], _m["global_box"][1], _m["global_box"][2] - _m["global_box"][0], _m["global_box"][3] - _m["global_box"][1])
                    else: log("target_id/target_mark not in the fresh target list; falling through to label resolution")
                # Mac ElementResolver.resolve:218 preferLocalHintBeforeAccessibility: a step that carries a spatial hint (point_2d/box_2d) tries the LOCAL perception cache (label only, anchor = previous step point or cursor) BEFORE AX/CDP
                if not done and pt and not nohint and lab:
                    _lr = _local_resolve_owned(lab, own)
                    if _lr: px = (_half_up(_lr["global_point"][0]), _half_up(_lr["global_point"][1])); src = "target_cache(hint-first):" + _lr["source"]; done = True; arm_rect = tuple(_lr["global_rect"])
                # Mac order: AX (here AT-SPI) -> local YOLO+OCR refinement -> raw Gemini coordinate
                if atspi_resolver and os.environ.get("TIPTOUR_USE_ATSPI", "1") == "1":
                    try:
                        poll_until = time.monotonic() + 0.9
                        hits = await read(atspi_resolver.resolve, lab, execution_app or now_id[1], **({"timeout": 0.9} if nohint else {}))
                        if nohint and not hits:
                            while not hits and time.monotonic() < poll_until:
                                await asyncio.sleep(min(0.08, max(0, poll_until - time.monotonic())))
                                hits = await read(atspi_resolver.resolve, lab, execution_app or now_id[1], timeout=max(0.01, poll_until-time.monotonic()))
                        # off the event loop: a hung AT-SPI read (child killed at its own timeout) must not delay Skip/new-ask handling; the plan_tok check after the await discards a stale result
                        dist = []
                        for t in hits:
                            c = (t["rect"][0] + t["rect"][2] / 2, t["rect"][1] + t["rect"][3] / 2)
                            if not any(abs(c[0] - d[0]) < 30 and abs(c[1] - d[1]) < 30 for d, _ in dist): dist.append((c, t))
                        if len(dist) == 1:
                            rx, ry, rw, rh = dist[0][1]["rect"]; px = (rx + rw // 2, ry + rh // 2); src = "atspi(1 match)"; done = True; arm_rect = (rx, ry, rw, rh); arm_app = dist[0][1].get("app")
                        elif len(dist) > 1:
                            refuse = "ambiguous: %d distinct AT-SPI controls match the label" % len(dist); done = True
                    except atspi_resolver.CoordinateError as e:
                        refuse="native/X11 coordinate mapping changed or unavailable; no fallback pointer";done=True;log("atspi coordinate mapping refused",str(e))
                    except Exception as e: log("atspi resolver error", type(e).__name__)
                if not done and os.environ.get("TIPTOUR_USE_CDP", "1") == "1":
                    try:
                        from . import cdp_resolver
                        st, hits = await read(cdp_resolver.resolve_ex, lab, _size)  # off the loop (blocking CDP I/O); token checked after the await
                        if st == "ok":
                            hh = hits[0]; bound_rect = tuple(hh["rect"]); arm_rect = bound_rect; rx, ry, rw, rh = hh["rect"]; px = (round(rx + rw / 2), round(ry + rh / 2)); src = "cdp_dom(1 match,%s)" % hh["role"]; done = True
                            ok2, why = await read(cdp_resolver.revalidate, lab, hh["rect"], _size)  # render-time recheck of focus/window/element
                            if not ok2: refuse = "browser state changed before pointing (%s)" % why
                        elif st == "ambiguous": refuse = "ambiguous: %d distinct on-screen DOM matches for the label" % len(hits)
                        elif st == "offscreen": refuse = "target exists in the page but is scrolled out of view; scroll first"
                        elif st == "gated":
                            log("cdp gated (reason in debug log)"); dlog("cdp gated:", cdp_resolver.GATE["reason"])
                            if any(r[0] <= model_px[0] <= r[0] + r[2] and r[1] <= model_px[1] <= r[1] + r[3] for r in cdp_resolver.GATE["browser_rects"]):
                                refuse = "the browser is not the foreground app; bring it to the front before pointing into it"
                        log("cdp stage:", st)
                    except Exception as e: log("cdp resolver error", type(e).__name__)
                if not refuse and plan_tok["n"] != _gen0: refuse = "superseded by a skip, cancel or newer request while resolving"
                if refuse: done = True
                if not done and not refuse and detector:
                    _tr = _local_resolve_owned(lab, own)  # Mac tier 3 (after AX and CDP): label-only cache resolve, anchor = previous step point or cursor, NOT the model point
                    if _tr: px = (_half_up(_tr["global_point"][0]), _half_up(_tr["global_point"][1])); src = "target_cache:" + _tr["source"]; arm_rect = tuple(_tr["global_rect"])
                    ref = None if (_tr or nohint) else perception.refine_coordinate(model_px, lab, _yolo, _ocr)  # nohint: refine would anchor on the placeholder; Mac: no hint + miss -> unresolved  # Linux-only fallback (not Mac semantics)
                    if ref: px = (round(ref["center"][0]), round(ref["center"][1])); src = "yolo_ocr:" + ref["rule"]
                if nohint and not refuse and src == "model_box" and defer_missing:
                    return {"ok": False, "status": "unresolved_no_hint"}, {"source": "UNRESOLVED", "label": lab}
                if nohint and not refuse and src == "model_box": refuse = "could not resolve \"%s\": no matching control and no spatial hint (Mac: resolve returns nothing); not pointing" % lab
                if not refuse and not (0 <= px[0] < _size[0] and 0 <= px[1] < _size[1]): refuse = "the model's coordinate (%d,%d) is outside the %dx%d screen; not pointing" % (px[0], px[1], size[0], size[1])
                with highlight_owner.lock:
                    _request_scope = (prop.get('request') or {})
                    _committed = _request_scope.get('context')
                    _context_epoch = highlight_owner.epoch
                    if _committed and id(highlight_owner.context) != _request_scope.get('context_identity'):
                        refuse = 'original request highlight context retired; not pointing' 
                if not refuse and src == "model_box" and _committed and any(w in lab.lower() for w in ("highlight", "this", "area", "region")):
                    try:
                        from . import cdp_resolver as _c
                        rx0, ry0, rw0, rh0 = _committed["rect"]
                        inter = [t for t in _c.all_targets() if not t.get("off") and t["rect"][0] < rx0 + rw0 and t["rect"][0] + t["rect"][2] > rx0 and t["rect"][1] < ry0 + rh0 and t["rect"][1] + t["rect"][3] > ry0 and t["role"] in ("a", "button", "input", "select", "textarea", "summary")]
                        if len(inter) == 1: rr = inter[0]["rect"]; px = (round(rr[0] + rr[2] / 2), round(rr[1] + rr[3] / 2)); src = "highlight_dom(1 control in region)"
                        elif len(inter) > 1: refuse = "the highlighted region contains %d controls (%s); say which one" % (len(inter), ", ".join(sorted({t["label"][:20] for t in inter})[:5]))
                    except Exception as e: log("highlight resolve error", type(e).__name__)
                # Generic scope guard (all sources): if the USER's request refers to the highlight ("highlighted", "this area", "here"...),
                # the final point must lie inside that region. A specific label does not widen the scope. Unrelated requests are unaffected.
                from . import highlight as _hlm
                if not refuse and _committed and _hlm.outside_scope(text, _committed["rect"], px) and src.startswith("cdp_dom(1 match") and bound_rect and _hlm.point_authorized(text):
                    _ip = _hlm.inside_intersection_point(_committed["rect"], bound_rect)  # ONE uniquely bound element overlaps the user's region and the user asked to be shown: point INSIDE the overlap, never at an outside centre
                    if _ip: px = _ip; src += "+inside_highlight_overlap"; log("moved point inside highlight overlap")
                if not refuse and _committed and _hlm.outside_scope(text, _committed["rect"], px):
                    refuse = "the request refers to the highlighted region, but the resolved target (%s, via %s) is outside it; not pointing" % (step.get("label", "")[:40], src)
                if not refuse and _committed and _hlm.outside_window(text, _committed, px):
                    refuse = "the request refers to the highlighted region in window %r, but the resolved target is outside that window; not pointing" % ((_committed.get("window") or {}).get("title", "")[:50],)
                with highlight_owner.lock:
                    if _committed and highlight_owner.epoch != _context_epoch:
                        refuse = 'highlight context changed during resolution; not pointing'
                unconf = (not refuse) and src == "model_box"
                if defer_missing:
                    await read(lambda: None)  # deadline check before any render/arm/OS action
                _cd_status = None
                def _arm_block(step, px, arm_rect, arm_app, src, refuse=None, _cd_status=None):
                    if not refuse and (step.get("type") or "click") != "observe" and os.environ.get("TIPTOUR_CLICK_DETECT", "1") == "1":  # Mac Teaching mode (a .observe step DISARMS the click detector instead: WorkflowRunner.swift:913-914): arm the listen-only click detector BEFORE the cursor lands; a click on the target completes the one-step plan (Mac WorkflowRunner.stop())
                        _tok = plan_tok["n"]
                        _val = None
                        cur["click_validator"] = None
                        if os.environ.get("TIPTOUR_CLICK_VALIDATE", "1") == "1" and atspi_resolver and not workflow.bypass_validator(step, _steps[idx + 1] if idx + 1 < len(_steps) else None):  # Mac shouldBypassPostClickValidator (rightClick, or the next step is keyboardShortcut/pressKey/type/setValue/scroll)
                            _val = workflow.ClickValidator(lambda: atspi_resolver.all_targets(timeout=8.0), lambda _n: atspi_resolver.fingerprint(_n, timeout=6.0), px if arm_rect is None else (arm_rect[0] + arm_rect[2] / 2, arm_rect[1] + arm_rect[3] / 2), app_hint=arm_app)
                            cur["click_validator"] = _val
                            validators.append(_val); _val.start_baseline(); threading.Thread(target=lambda _v=_val: (_v.ready.wait(60), log("validator baseline ready: scope_set=%s stable=%d noise=%d err=%s" % (bool(_v.scope), len(_v.stable), len(_v.noise), _v.baseline_error))), daemon=True).start()  # baseline runs in the background; arming and drawing never wait for it
                        def _valid(_src=src, _tok=_tok, _val=_val):
                            if _val is None:
                                log("target click detected; pointer dismissed; validator: not run (right-click or disabled) - effect UNVERIFIED"); click_events.append({"target_clicked": True, "src": _src, "validator": "unavailable:not_run", "effect": "unverified"}); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire); loop.call_soon_threadsafe(lambda: hl.get("advance") and hl["advance"]("click", _tok)); return
                            _val.on_click()
                            def _watch():
                                _val.done.wait(60)
                                if _tok != plan_tok["n"]: click_events.append({"validator_stale_ignored": True, "verdict": _val.verdict}); return
                                v = _val.verdict
                                ev_ = {"target_clicked": True, "src": _src, "validator": v, "effect": "confirmed" if v == "changed" else "unverified", **_val.detail}
                                click_events.append(ev_)
                                if _val.sample: dlog("validator diff removed=%r added=%r" % _val.sample)
                                if v == "unchanged_paused": GLib.idle_add(lambda: (panel.show_at(px[0], px[1], "No visible change after the click.", _tok) if _tok == plan_tok["n"] else None) and False)
                                if v == "unchanged_paused": log("post-click validator: AT-SPI state unchanged after the settle window; paused (pointer kept; on-screen Retry/Skip panel shown)"); return
                                log("target click detected; pointer dismissed; validator: %s" % ("changed (effect confirmed in the target app's AT-SPI state)" if v == "changed" else "%s - the click was on the target but its effect is UNVERIFIED" % v)); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire)
                                if v == "changed": loop.call_soon_threadsafe(lambda: hl.get("advance") and hl["advance"]("click", _tok))
                            threading.Thread(target=_watch, daemon=True).start()
                        def _stale(): log("click on stale armed target ignored (token mismatch)"); click_events.append({"stale_ignored": True})
                        _clicked = guarded_callback(plan_tok, _tok, _valid, _stale)
                        _ok = clicks.arm(px if arm_rect is None else (arm_rect[0] + arm_rect[2] / 2, arm_rect[1] + arm_rect[3] / 2), arm_rect, _clicked)
                        _cd_status = clicks.backend if _ok else "UNAVAILABLE"
                        if _ok:  # while the target is still pending/paused: hide the pointer when a window covers it or another app takes focus (misleading guidance), show it again when restored
                            def _guard(_tok=_tok, _pt=(px if arm_rect is None else (arm_rect[0] + arm_rect[2] / 2, arm_rect[1] + arm_rect[3] / 2)), _pin=clicks._pin, _lab=step.get("label"), _rect=arm_rect, _app=arm_app, _plan_app=execution_app):
                                last = "ok"; _matcher = PlanTargetMatcher(_plan_app, step.get("type"), step.get("label"), (clicks.app_identity_of_window(_pin[0])[1] if _pin else None))
                                def _live(): return _tok == plan_tok["n"] and not ov['hidden']  # hidden = terminal (dismissed/refused/skipped/paused); covered is separate and reversible
                                def _show():
                                    with glock:
                                        if _live(): overlay.show_all(); overlay.move(overlay.tip[0]-overlay.CX, overlay.tip[1]-overlay.CY)
                                    return False
                                while True:
                                    time.sleep(0.4)
                                    with glock:
                                        if not _live(): break
                                    st = clicks.pin_state(_pt, _pin)
                                    if st == "unknown" or st == last: continue
                                    click_events.append({"pointer_guard": st, "was": last}); log("pointer guard: target window state %s (was %s)" % (st, last))
                                    if st == "focus_other":  # Mac activationMatchesCurrentPlanTarget: switching to the plan's own target app is tolerated; only an UNRELATED app pauses
                                        _foc = clicks.window_identity_at(_pt)[1]; _fn, _fi = clicks.app_identity_of_window(_foc) if _foc else (None, None)
                                        if _matcher.matches(_fn, _fi): log("pointer guard: focus moved within the plan's target app (%s); not paused (Mac activationMatchesCurrentPlanTarget)" % _fi); last = st; continue
                                    if st == "focus_other":  # another app took focus: explicit pause; like the Mac, NO auto-resume on focus return (user must @retry or ask again)
                                        def _pause_app_switch():  # runs ON the asyncio loop: every plan_tok write is loop-owned; re-validate liveness here
                                            with glock:
                                                if not _live(): return
                                                ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.hide); clicks.disarm(); plan_tok["n"] += 1; cur['paused'] = 'app_switch'
                                                click_events.append({"pointer_guard": "paused_app_switch", "label": _lab}); GLib.idle_add(lambda _t=plan_tok["n"]: (panel.show_at(_pt[0], _pt[1], "Another app took focus.", _t) if _t == plan_tok["n"] else None) and False); log("pointer guard: another app took focus; target paused, pointer hidden, no auto-resume (use retry or ask again)")
                                        _on_loop(_pause_app_switch)
                                        break
                                    if st == "ok":
                                        valid = _target_valid(_app, _lab, _rect)  # cover removed is not enough: the same control (label+rect) must still exist in the same app
                                        if valid:
                                            with glock:
                                                if not _live(): break
                                                ov['covered'] = False; GLib.idle_add(_show)
                                        else:
                                            def _target_changed():  # runs ON the asyncio loop
                                                with glock:
                                                    if not _live(): return
                                                    ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.hide); clicks.disarm(); plan_tok["n"] += 1
                                                    click_events.append({"pointer_guard": "target_changed_not_resumed", "label": _lab}); log("pointer guard: target no longer verifiable at its place; pointer stays hidden, detector disarmed (ask again)")
                                            _on_loop(_target_changed)
                                            break
                                    else:
                                        with glock:
                                            if _live(): ov['covered'] = True; GLib.idle_add(overlay.hide)
                                    last = st

                            if clicks._pin is not None: threading.Thread(target=_guard, daemon=True).start()
                    return _cd_status
                if plan_tok["n"] != _gen0:
                    return {"ok": False, "status": "not_pointed", "error": "superseded before arming"}, {"source": "REFUSED"}
                _cd_status = _arm_block(step, px, arm_rect, arm_app, src, refuse, None)
                cur.update(label=step.get("label"), step=step, px=px, rect=arm_rect, app=arm_app, src=src, armed=not refuse, pin=clicks._pin, rearm=(lambda s=step, p=px, r=arm_rect, ap=arm_app, sc=src: _arm_block(s, p, r, ap, sc, None, None)))
                with glock:  # atomic with the control thread/guard threads: final generation check + commit of hidden state + render post
                    if not refuse and plan_tok["n"] != _gen0:
                        refuse = "superseded by a skip, cancel or newer request while resolving"  # no disarm here: the superseding transition already disarmed, and this must never disarm a NEWER plan's detector
                    ov['hidden'] = bool(refuse); ov['covered'] = False; GLib.idle_add(lambda: panel.hide_panel() and False)
                    if refuse: GLib.idle_add(overlay.retire)  # a refusal must not leave the previous answer's cursor on screen
                    if not refuse: PREV_STEP_POINT['p'] = (px[0], px[1]); stream_state['suppressed'] = True; log('render cursor at', px, 'src', src); (None if a.act and step.get('type','click') in ('click','rightClick','doubleClick') else GLib.idle_add(overlay.point_to, px[0], px[1], ("? " if unconf else "") + step.get("label", "")))
                    if not refuse and (step.get("type") or "click") == "observe":  # Mac WorkflowRunner.swift:913-921: .observe = ClickDetector.disarm(), point, then after 650ms advance (never waits for a click) if the operation token is unchanged
                        clicks.disarm(); _otok = plan_tok["n"]; _ot = asyncio.ensure_future(_observe_advance(_otok)); hl["obs_task"] = _ot; click_events.append({"observe": "pointed_no_arm", "auto_advance_ms": 650})
                if ambiguous and src == "model_box": src = "model_box(UNCONFIRMED:%d DOM candidates)" % ambiguous
                tool_seen = {"label": step.get("label"), "point_2d": (None if nohint else pt), "no_hint": nohint, "px": px, "model_px": (None if nohint else model_px), "source": src}
                if _cd_status: tool_seen["click_detector"] = _cd_status
                if refuse: tool_seen["source"] = "REFUSED"; tool_seen["refused"] = refuse; log("refused to point (reason in debug log only)"); dlog("refused to point:", refuse)
                if refuse: resp = {"ok": False, "status": "not_pointed", "error": refuse}
                elif a.act and (step.get("type") or "click") in ("click", "doubleClick", "rightClick") and not _approved_step(args, idx, step):
                    log("action NOT executed: no exact approved step for %s" % (step.get("type") or "click"))
                    resp = {"ok": False, "status": "not_executed", "error": "The exact current step is not approved; no action was sent."}
                elif a.act and (step.get("type") or "click") in ("click", "doubleClick", "rightClick"):
                    from . import actions
                    # Mac WorkflowRunner130 starts a 0.28s autopilot delay after arming.
                    # Binding the same native object is independent read work inside
                    # that delay, not an additional delay before the clock starts.
                    _armed_at=time.monotonic()
                    _baseline=cur.get("click_validator");_baseline_token=_gen0
                    # Bind the actual native object before dispatch, never label+rect alone.
                    _click_pin = clicks._pin
                    _click_native = None
                    if atspi_resolver and arm_app and arm_rect:
                        _native_targets = await asyncio.to_thread(atspi_resolver.app_targets, arm_app)
                        _native_matches = [nt for nt in _native_targets if (nt.get("label") or "").strip().lower() == (step.get("label") or "").strip().lower() and nt.get("rect") and all(abs(nt["rect"][j]-arm_rect[j]) <= 8 for j in range(4))]
                        if len(_native_matches) == 1: _click_native = _native_matches[0].get("native_identity")
                    if not _click_native: return {"ok": False, "status": "not_executed", "error": "stable native click object unavailable"}, tool_seen
                    dlog("stable native click bound", json.dumps(_click_native, sort_keys=True))
                    # Keep the loop responsive while the pointer lands. STOP/supersede must win before dispatch.
                    _click_cancel = threading.Event()
                    try:
                        if not await _pointer_arrival(px, step.get('label') or 'Click target', _gen0):
                            return {'ok':False,'status':'pointer_arrival_revoked'},tool_seen
                        await asyncio.sleep(max(0.0, 0.28-(time.monotonic()-_armed_at)))
                        if plan_tok["n"] != _baseline_token or cur.get("click_validator") is not _baseline:
                            return {"ok":False,"status":"not_executed","error":"click baseline superseded"},tool_seen
                        if _baseline is not None:
                            _wait_end=time.monotonic()+8.0
                            while not _baseline.ready.is_set():
                                if plan_tok["n"] != _gen0:raise asyncio.CancelledError()
                                if time.monotonic()>=_wait_end:
                                    return {"ok":False,"status":"not_executed","error":"click baseline unavailable before dispatch"},tool_seen
                                await asyncio.sleep(.02)
                            if _baseline.baseline_error:
                                return {"ok":False,"status":"not_executed","error":"click baseline failed before dispatch"},tool_seen
                        if plan_tok["n"] != _gen0: return {"ok": False, "status": "not_executed", "error": "click superseded before dispatch"}, tool_seen
                        _click_ident = ident()
                        if _click_ident != now_id: return {"ok": False, "status": "not_executed", "error": "focused window changed while pointer landed"}, tool_seen
                        _click_valid = await asyncio.to_thread(_target_valid, arm_app, step.get("label"), arm_rect, _click_native)
                        _click_ms, _click_mt = await asyncio.to_thread(atspi_resolver.modal_title, execution_app or arm_app) if atspi_resolver else ("unavailable", None)
                        if plan_tok["n"] != _gen0 or ident() != _click_ident or not _click_valid or _click_ms != "ok" or _click_mt is not None:
                            resp = {"ok": False, "status": "not_executed", "error": "click target/window changed or unavailable before dispatch"}
                        else:
                            resp = await asyncio.to_thread(actions.execute, step, px, arm_app, None, _click_cancel, lambda: plan_tok["n"] == _gen0 and _approved_step(args, idx, step) and _click_pin is not None and clicks.pin_state(px, _click_pin) == "ok")
                    except BaseException:
                        _click_cancel.set(); log("click cancelled before next OS dispatch (an already dispatched event cannot be undone)"); raise
                    log("action executed, ok=%s" % resp.get("ok")); dlog("action", json.dumps(resp))
                    if resp.get("ok") and step.get("type") == "rightClick":
                        # Listener currently handles left presses only. Successful owned right-button dispatch follows Mac's explicit validator bypass.
                        clicks.disarm(); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire)
                        loop.call_soon(lambda: hl.get("advance") and hl["advance"]("click", _gen0))
                elif unconf: resp = {"ok": False, "status": "pointed_unconfirmed", "note": "The cursor was placed from the vision estimate only; no UI element or page element confirmed it. Do not claim it is on the target. Tell the user it is a guess and ask them to confirm."}
                else: resp = {"ok": True, "status": "pointed", "note": "point-only mode; user must click"}
            else:
                resp = {"ok": False, "error": "no coordinates"}
            return resp, tool_seen

        _perc_lk = threading.Lock(); _perc_seq = {"started": 0, "applied": 0}
        def _perceive(full, owned=False, publish=True):
            with _perc_lk:
                if publish: _perc_seq["started"] += 1
                _my_p = _perc_seq["started"] if publish else 0  # newest-STARTED perception owns TARGET_CACHE (older/cancelled worker-thread results must not overwrite it)
            yolo = detector.detect(full) if detector else []
            ocr_el = perception.ocr(full.resize((full.width*2, full.height*2))) if detector else []
            for e in ocr_el: e['bbox']=[v/2 for v in e['bbox']]; e['center']=[v/2 for v in e['center']]
            log('perception: %d yolo boxes, %d ocr lines' % (len(yolo), len(ocr_el)))
            _els = [{'bbox': [b['bbox'][0], b['bbox'][1], b['bbox'][0] + b['bbox'][2], b['bbox'][1] + b['bbox'][3]], 'label': b.get('label') or '', 'source': 'yolo', 'conf': b.get('conf', 0)} for b in yolo] + [{'bbox': [e['bbox'][0], e['bbox'][1], e['bbox'][0] + e['bbox'][2], e['bbox'][1] + e['bbox'][3]], 'label': e.get('label') or '', 'source': 'ocr', 'conf': e.get('conf', 0)} for e in ocr_el]; _sz = tuple(full.size); _dfr = (0, 0, _sz[0], _sz[1])  # from THIS pass's own image, not the shared nonlocal size
            _pc = LocalPerceptionTargetCache(); _pc.update(_els, _sz, _dfr)  # PRIVATE snapshot owned by this pass (immutable after this line)
            with _perc_lk:
                if publish and _my_p >= _perc_seq['applied']:
                    _perc_seq['applied'] = _my_p
                    TARGET_CACHE.update(_els, _sz, _dfr)  # Mac: LocalPerceptionTargetCache.update after each perception pass (newest-started wins the SHARED cache)
            return (yolo, ocr_el, _my_p, _pc) if owned else (yolo, ocr_el)
        readonly_harness = None
        if a.readonly_harness:
            from .engine import ReadOnlyEngine
            from .harness import ReadOnlyHarness
            def _active_app():
                from Xlib import display as _xd
                _display = _xd.Display()
                try:
                    _root = _display.screen().root
                    _prop = _root.get_full_property(_display.intern_atom('_NET_ACTIVE_WINDOW'), 0)
                    if not _prop or not len(_prop.value): return {}
                    _window = _display.create_resource_object('window', int(_prop.value[0]))
                    _wm = _window.get_wm_class() or ()
                    return dict(name=_wm[-1] if _wm else None, desktop_id=None)
                finally: _display.close()
            _readonly_cache = LocalPerceptionTargetCache()
            from .read_worker import ReadWorker
            _read_worker = ReadWorker(loop.call_soon_threadsafe)
            hl['readonly_worker'] = _read_worker
            _read_eligible = _read_worker.check
            def _refresh_targets(reason):
                _read_eligible()
                _token = plan_tok["n"]
                _captured = capture_clean()  # NEVER overwrites the approved/utterance pin.
                _read_eligible()
                _, _, _, _private = _perceive(_captured[0], True, publish=False)
                _read_eligible()
                if _token != plan_tok["n"]: raise RuntimeError('read superseded')
                # Read-only cache is private; no TARGET_CACHE/frame_id/own_cap publication.
                def _publish_private():
                    if _token != plan_tok["n"]: raise RuntimeError("read superseded")
                    with _readonly_cache._lock: _readonly_cache._snap = _private._snap
                _read_worker.publish(_publish_private)
            _engine = ReadOnlyEngine(_active_app,
                lambda: dict(autopilot=a.act, action_driver=a.act,
                             screenshots=os.environ.get('TIPTOUR_STREAM','1')=='1', accurate_grounding=detector is not None),
                lambda: hl.get('active_goal'), _readonly_cache, _refresh_targets, capture_clean, detection_count=TARGET_CACHE.fresh_target_count)
            def _invoke_readonly(method):
                def eligible():
                    return method not in ('targets','screenshots') or not (_goal_live() or gate['turn'] or gate['replay'] or resolving['n'])
                return _read_worker.invoke(lambda: getattr(_engine,method)(True) if method == 'targets' else getattr(_engine,method)(), eligible)
            readonly_harness = ReadOnlyHarness(_invoke_readonly)
            readonly_harness.start(); log('read-only harness listening on 127.0.0.1:%d (no action endpoints)' % readonly_harness.port)
        _navigation_observers = []
        last_call = {}; hl['last_call'] = last_call
        def _clear_last():
            for _observer in _navigation_observers[:]:
                _observer.retire()
                asyncio.create_task(_observer.close())
            _navigation_observers.clear()
            last_call.clear()

        def _cancel_task(keep_obs=False):
            """Mac cancels the in-flight resolution task BEFORE every transition (skip/advance/start/stop/resume/retry). Loop-thread only. keep_obs=True (used at ASK DEQUEUE only): a new UTTERANCE is not a transition on the Mac - the active plan (incl. a pending observe auto-advance) keeps running until a toolCall supersedes it or a control (skip/stop) cancels it."""
            _ob = hl.get('obs_task')
            if not keep_obs:
                if _ob is not None and not _ob.done(): _ob.cancel(); log("pending observe auto-advance cancelled by a newer transition")
                hl['obs_task'] = None
            t = hl.get('task')
            if t is not None and not t.done(): t.cancel(); click_events.append({"control": "inflight_cancelled", "reason": "superseded by a newer transition"}); log("in-flight replay/advance cancelled by a newer transition")
            hl['task'] = None
        def _spawn(coro):
            _cancel_task(); hl['task'] = asyncio.ensure_future(coro)
        hl['cancel_task'] = _cancel_task
        async def _replay_step(kind, tok0=None):
            """Mac WorkflowRunner.retryCurrentStep() / resume(): re-capture the screen and rerun the FULL resolver cascade for the active step. No model round-trip, no tool_response."""
            nonlocal full, jpeg, size, yolo, ocr_el
            c = dict(last_call)
            if kind == "approved_plan" and not (prop["state"] == "approved" and c.get("hash") == prop["hash"] and c.get("rev") == prop["rev"]): click_events.append({"gate": "approved_replay_refused", "reason": "record no longer approved"}); prop["started"] = True; log("approved plan replay refused: record not approved/bound"); return
            while gate['turn'] or gate['replay']:  # never overlaps a live turn's capture/resolve; waits UNBOUNDED (a transition is never silently dropped): ends by the turn finishing, or by a newer transition cancelling this task
                if tok0 is not None and tok0 != plan_tok['n']: break
                await asyncio.sleep(0.1)
            if not c: click_events.append({"control": kind + "_refused", "reason": "no active step"}); log("control %s refused: no active step" % kind); return
            if tok0 is not None and tok0 != plan_tok['n']: click_events.append({"control": kind + "_refused", "reason": "superseded"}); log("control %s refused: superseded by a skip or a newer target while waiting" % kind); return
            gate['replay'] = True
            if kind == "approved_plan": prop["started"] = True
            try:
                pause_rs['r'] = None
                (full, jpeg, size), _oc = await asyncio.to_thread(capture_pinned)
                yolo, ocr_el, _mp, _pcn = await asyncio.to_thread(_perceive, full, True); _own = _own_rec((full, jpeg, size), _oc, yolo, ocr_el, _mp, _pcn)
                if tok0 is not None and tok0 != plan_tok['n']: click_events.append({"control": kind + "_refused", "reason": "superseded after capture"}); log("control %s refused: superseded by a skip or a newer target during capture" % kind); return
                resp, ts = await _resolve_step(c["v"], c["args"], c["text"], c.get("idx", 0), own=_own)
            finally: gate['replay'] = False
            click_events.append({"control": kind + "_replay", "status": (resp or {}).get("status"), "source": (ts or {}).get("source"), "refused": (ts or {}).get("refused")}); log("control %s: re-resolved the active step from a fresh capture -> %s" % (kind, (ts or {}).get("source")))
        async def _observe_advance(tok0):
            await asyncio.sleep(0.65)
            if tok0 != plan_tok["n"]: click_events.append({"observe": "advance_refused", "reason": "superseded"}); log("observe auto-advance refused: superseded"); return
            log("observe step pointed; advancing after 650ms (no click awaited)")
            await _advance_step("observe", tok0)
        async def _advance_step(kind, tok0=None):
            """Mac WorkflowRunner advance (skipCurrentStep / a successful click): next step of the SAME plan, fresh capture + perception, previous-step point as the cache anchor. No model round-trip. Past the last step the plan is complete."""
            nonlocal full, jpeg, size, yolo, ocr_el
            _busy = (lambda: gate['replay'] or resolving['n'] > 0) if kind == "observe" else (lambda: gate['turn'] or gate['replay'])  # observe auto-advance: only a resolve/replay in progress blocks it (650ms semantics); skip/click advances keep the turn gate
            if _busy(): log("advance (%s): waiting for the in-progress resolve/replay/turn to finish (not dropped)" % kind)
            while _busy():  # unbounded wait: Skip is never silently dropped; superseded -> explicit refusal below, newer transition -> task cancelled
                if tok0 is not None and tok0 != plan_tok['n']: break
                await asyncio.sleep(0.1)
            c = dict(last_call)
            if not c: click_events.append({"control": kind + "_refused", "reason": "no active step"}); return
            if tok0 is not None and tok0 != plan_tok['n']: click_events.append({"advance": kind, "refused": "superseded"}); log("advance (%s) refused: superseded by a skip or a newer target while waiting" % kind); return
            n = len(c["args"].get("steps") or [])
            gate['replay'] = True
            try:
                if c["idx"] + 1 >= n:
                    with glock:
                        plan_tok["n"] += 1; clicks.disarm(); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire); cur['armed'] = False; cur['paused'] = None; pause_rs['r'] = None; _clear_last(); PREV_STEP_POINT['p'] = None
                    click_events.append({"advance": kind, "plan_complete": True}); log("advance (%s): no next step, plan complete" % kind); return
                last_call["idx"] = c["idx"] + 1; pause_rs['r'] = None
                if kind == "click":
                    await asyncio.sleep(0.08)
                    if tok0 is not None and tok0 != plan_tok["n"]: return
                (full, jpeg, size), _oc = await asyncio.to_thread(capture_pinned)
                yolo, ocr_el, _mp, _pcn = await asyncio.to_thread(_perceive, full, True); _own = _own_rec((full, jpeg, size), _oc, yolo, ocr_el, _mp, _pcn)
                if tok0 is not None and tok0 != plan_tok['n']: last_call["idx"] = c["idx"]; click_events.append({"advance": kind, "refused": "superseded after capture"}); log("advance (%s) refused: superseded during capture" % kind); return
                resp, ts = await _resolve_step(c["v"], c["args"], c["text"], c["idx"] + 1, own=_own, post_click=kind == "click")
                click_events.append({"advance": kind, "to_step": c["idx"] + 1, "of": n, "source": (ts or {}).get("source"), "refused": (ts or {}).get("refused")}); log("advance (%s): step %d of %d resolved -> %s" % (kind, c["idx"] + 2, n, (ts or {}).get("source")))
            finally: gate['replay'] = False
        def _advance_spawn(kind, tok0=None):
            if kind == "click" and (gate['turn'] or gate['replay']):
                # A listen-only button event can arrive while our own click OS call is still returning.
                # Do not cancel that executor just to advance its successful click.
                async def _after_dispatch():
                    while gate['turn'] or gate['replay']:
                        if tok0 != plan_tok['n']: return
                        await asyncio.sleep(0.03)
                    if tok0 == plan_tok['n']: _spawn(_advance_step(kind, tok0))
                asyncio.create_task(_after_dispatch()); return
            _spawn(_advance_step(kind, tok0))
            if kind == "skip": hl['skip_adv'] = (hl['task'], tok0)
        hl['advance'] = _advance_spawn
        hl['replay'] = lambda kind, tok0=None: _spawn(_replay_step(kind, tok0))
        if os.environ.get('TIPTOUR_TEST_MODE') == '1' and os.environ.get('TIPTOUR_TEST_NO_REPLAY') == '1': hl.pop('replay', None)  # TEST SEAM (needs TIPTOUR_TEST_MODE=1): exercise the legacy re-arm fallback of _control retry; never set in production
        # ---- USER-REQUIRED CONFIRMATION GATE (Ishit, voice notes 19:30/19:31 IST 26 Oct): NO plan (one step or several) runs until the user says yes to THAT plan. App-owned record; the model can neither approve nor execute. Not a Mac gate.
        import hashlib as _hashlib, re as _re2
        from .request_chain import Requests
        requests = Requests()
        request_turn = {"key": None}
        request_boundary = {"n": 0}
        voice_command_boundaries = {}
        request_context_refs = {}  # strong references held until Stop; no recycled object identity
        prop = {"rev": 0, "hash": None, "args": None, "text": None, "state": None, "turn": -1, "id": None}
        _YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed", "go ahead", "do it", "proceed", "yes please", "yes do it", "yes go ahead", "go for it"}
        _SEPARATE_YES = {"start separate task and run", "start the separate task and run"}
        _YES |= _SEPARATE_YES
        _NO = {"no", "nope", "dont", "do not", "don't", "never mind", "nevermind", "no thanks"}  # DECLINES the pending proposal only; an already-approved/running plan is left alone (new ask is not a transition)
        _STOP = {"stop", "cancel", "abort", "stop it", "stop that", "cancel it", "cancel that", "stop please", "no stop", "no cancel"}  # explicit STOP: clears any pending proposal AND stops approved/running work
        def _norm_resp(t): return _re2.sub(r"\s+", " ", _re2.sub(r"[.,!?]", "", (t or "").lower().replace("\u2019", "'"))).strip()  # WHOLE response, only sentence punctuation removed: digits/other words are kept, so "yes 2" or "ok but change it" is NOT a yes
        def _plan_canon(args): return json.dumps(args, sort_keys=True, ensure_ascii=False)  # EVERY field the model sent is part of the approved record
        def _approved_step(args, idx, step):
            from .plan_authority import approved_step
            from .highlight import no_action_requested
            from .request_limits import forbidden_plan
            _rq = prop.get('request') or {}
            with highlight_owner.lock:
                if _rq.get('context') is not None and id(highlight_owner.context) != _rq.get('context_identity'):
                    return False
            return (prop.get("request") is not None and
                    _plan_canon(prop.get("request")) == _plan_canon(requests.snapshot()) == _plan_canon(last_call.get("request")) and
                    not no_action_requested(prop.get("text")) and not forbidden_plan(prop.get("text"), args) and
                    approved_step(prop, last_call, args, idx, step))
        def _kv(d, skip): return "".join(" %s=%s" % (k, json.dumps(v, ensure_ascii=False)) for k, v in d.items() if k not in skip and not k.startswith("_") and v not in (None, ""))
        def _plan_text(args):
            lines = ["Plan%s%s (%d step%s):" % ((" '%s'" % args.get("goal")) if args.get("goal") else "", (" in %s" % args.get("app")) if args.get("app") else "", len(args.get("steps") or []), "" if len(args.get("steps") or []) == 1 else "s")]
            _pl = _kv(args, ("goal", "app", "steps"))
            if _pl: lines.append("  plan fields:" + _pl)
            for n, st in enumerate(args.get("steps") or [], 1): lines.append("  %d. %s %s%s" % (n, st.get("type", "click"), st.get("label", "") or "", _kv(st, ("type", "label"))))  # every execution-bearing field (value, app, targetContext, direction/amount/by, shortcut, coordinates, scope...) is shown
            return "\n".join(lines)
        def _plain_text(args):  # human-readable ORDERED proposal. HONEST about the engine: point-only (--act OFF), the app moves the cursor to each target; it never clicks, types, presses keys, scrolls or opens anything. Raw fields stay in Details.
            _st = args.get("steps") or []
            _l = ["Goal: %s%s" % (args.get("goal") or "(none given)", (" - app: %s" % args.get("app")) if args.get("app") else ""),
                  "Action mode ON: I will perform the steps below after your yes." if a.act else "Action mode OFF: I only point at click/observe targets. Other actions pause without a pointer."]
            _shown_ranges = set()
            for _n, _s2 in enumerate(_st, 1):
                _t = str(_s2.get("type") or "click"); _lab = _s2.get("label") or (args.get("app") if str(_s2.get("type")) == "openApp" else None) or "(no label)"; _v = _s2.get("value")
                _w = {"click": ('Click "%s" (I perform this approved step, action mode ON)' if a.act else 'Point at "%s" for you to click'), "rightClick": ('Right-click "%s" (I perform it, action mode ON)' if a.act else 'Point at "%s" for you to right-click'), "doubleClick": ('Double-click "%s" (I perform it, action mode ON)' if a.act else 'Point at "%s" for you to double-click'), "openApp": 'Point at the app "%s" for you to open', "openURL": 'Point at where "%s" would be opened', "keyboardShortcut": 'Point at the target for the shortcut "%s" (you press the keys)', "pressKey": 'Point at the target for the key "%s" (you press it)', "type": 'Point at the field "%s" (you type the text yourself)', "setValue": 'Point at the field "%s" (you set the value yourself)', "scroll": 'Point at "%s" for you to scroll', "waitForState": 'SKIPPED: "%s" (waiting for a state is not implemented; no waiting happens and no pointer is placed)', "observe": 'Point at "%s" (no click)'}.get(_t, 'Step of type "' + _t + '" on "%s"') % _lab
                if a.act and _t in ("openApp", "openURL", "keyboardShortcut", "pressKey", "type", "scroll"): _w = {"openApp": 'Open the app "%s" (approved plan step)', "openURL": 'Open "%s" (approved plan step)', "keyboardShortcut": 'Press the shortcut "%s" in the plan\'s app (Cmd means Ctrl; approved plan step)', "pressKey": 'Press the key "%s" in the plan\'s app (approved plan step)', "type": 'Replace the selected text or insert at the caret in verified field "%s" (native plain-text whole-value write; caret/readback checked)', "scroll": 'Scroll the plan\'s app with the keyboard ("%s"; approved plan step)'}[_t] % _lab
                if (not a.act) and _t in ("openApp", "openURL", "keyboardShortcut", "pressKey", "type", "scroll", "setValue"): _w = 'ACTION step (%s "%s"): action mode is OFF, so I will PAUSE the plan here, place no pointer and do nothing' % (_t, _lab)
                if a.act and _t == "setValue": _w = 'Replace the entire verified editable field "%s" with the supplied value (native whole-value write; exact readback required)' % _lab
                if a.act and _s2.get("_native_range") and _t in ("type", "setValue", "pressKey"):
                    _rk = json.dumps(_s2["_native_range"], sort_keys=True)
                    if _rk not in _shown_ranges: _w = 'Replace the SAVED selected range in "%s" (surrounding text preserved; stale field/range refuses)' % _lab; _shown_ranges.add(_rk)
                    elif _t == "type": _w = 'Insert/replace at the CURRENT caret/selection in "%s" (saved range already used)' % _lab
                    elif _t == "setValue": _w = 'Replace the WHOLE current field "%s" (saved range already used)' % _lab
                    elif _t == "pressKey": _w = 'Press the deletion key in the CURRENT field "%s" (saved range already used)' % _lab
                from .app_transition import destination
                _transition, _app = destination(args, _n - 1)
                _x = ['execution app after approved transition: ' + _app] if _transition is not None else []
                if _v not in (None, ""): _x.append('value "%s"' % _v)
                if _t == "scroll": _x.append("scroll args direction=%s amount=%s by=%s (%s)" % (_s2.get("direction", "not given"), _s2.get("amount", "not given"), _s2.get("by", "not given"), "applied as keys, amount clamped 1..50, default 3" if a.act else "NOT applied: point-only"))
                if _s2.get("targetContext"): _x.append("target context: %s" % _s2["targetContext"])
                if _s2.get("hint"): _x.append('hint: "%s"' % _s2["hint"])
                _l.append("  %d. [%s] %s%s" % (_n, _t, _w, (" - " + "; ".join(_x)) if _x else ""))
            if a.act and any(st.get("type") in ("pressKey", "keyboardShortcut", "scroll") for st in _st): _l.append("Keys go to the verified focused window; X11 has a small non-atomic check/input gap. Cmd means Ctrl.")
            if a.act and any(st.get("targetContext") in ("currentHighlight", "currentSelection") for st in _st):
                _l.append("The saved native range is used ONCE. Later edits use the current selection/caret. A stale first range refuses." if all(st.get("_native_range") for st in _st if st.get("targetContext") in ("currentHighlight", "currentSelection")) else "Native highlighted range is unavailable; the action will be refused.")
            _l.append("Say yes / Confirm to run, no / Cancel to decline. Say stop to stop.")
            return "\n".join(_l)
        def _prop_clear(why):
            if prop["state"] == "pending": _note("the proposed plan rev %d was cleared without running (%s)" % (prop["rev"], why)); log("confirmation: pending plan rev %d cleared (%s)" % (prop["rev"], why)); click_events.append({"gate": "proposal_cleared", "rev": prop["rev"], "why": why})
            _watch = prop.pop('confirmation_watch', None)
            if _watch: _watch.close()
            prop["state"] = None; GLib.idle_add(lambda: pprop.hide_panel() and False)
        def _approve_pending(src, turn_i):
            """Execute the STORED plan of the pending proposal (never a model resubmit). Returns True if started."""
            if prop["state"] != "pending": return False
            _watch = prop.get('confirmation_watch')
            if _watch and not _watch.valid():
                _prop_clear('confirmation native ownership changed'); return False
            if prop.get("boundary") != request_boundary["n"]:
                _prop_clear("request boundary revoked"); return False
            if prop.get('task_boundary'):
                if prop.get('relation') == 'separate' and src not in ('separate-control', 'separate-voice', 'separate-text'):
                    click_events.append({'gate': 'separate_task_explicit_approval_required'})
                    log('confirmation: use Start separate task and run to approve the displayed task change; ordinary yes does not discard the old task')
                    return False
                if _plan_canon(requests.boundary()) != _plan_canon(prop['task_boundary']):
                    _prop_clear('task boundary changed'); return False
                with highlight_owner.lock:
                    _scope = prop['request'].get('context')
                    if _scope is not None and (prop['request'].get('context_identity') != id(highlight_owner.context) or _plan_canon(_scope) != _plan_canon(highlight_owner.context)):
                        _prop_clear('task scope changed before boundary approval'); return False
                    if _scope is not None:
                        request_context_refs[id(highlight_owner.context)] = highlight_owner.context
                requests.record = json.loads(json.dumps(prop['request']))
                requests.revision = requests.record['id']; requests.blocked = False
                requests.pending_text = None
            if _plan_canon(prop.get('request')) != _plan_canon(requests.snapshot()):
                _prop_clear('original request binding changed'); return False
            _watch = prop.pop('confirmation_watch', None)
            if _watch: _watch.close()  # drained above, no await before immutable approval
            _a = prop["args"]; _g2 = str(_a.get("goal") or "").strip()
            _note("the user APPROVED plan rev %d (%s); the app is executing the stored plan" % (prop["rev"], src)); prop["state"] = "approved"; prop["started"] = False; prop["appr"] = arr["n"]; prop["kick"] = (src in ("voice", "separate-voice")); GLib.idle_add(lambda: pprop.hide_panel() and False); click_events.append({"gate": "proposal_approved", "rev": prop["rev"], "hash": prop["hash"], "via": src, "turn": turn_i}); log("confirmation: user approved plan rev %d (%s) via %s; executing the stored plan" % (prop["rev"], prop["hash"][:12], src))
            if _goal_live(): log("tool: superseding active plan %r with approved plan %r" % (hl.get("active_goal"), _g2)); click_events.append({"gate": "supersede_active_plan", "id": prop["id"]}); (hl.get('cancel_task') or (lambda *_: None))(); clicks.disarm(); plan_tok["n"] += 1
            hl["active_goal"] = _g2; _clear_last(); last_call.update(v={"id": prop["id"], "name": "submit_workflow_plan"}, args=_a, text=prop["text"], idx=0, rev=prop["rev"], hash=prop["hash"], request=json.loads(json.dumps(prop["request"])))
            plan_tok["n"] += 1; hl["replay"]("approved_plan", plan_tok["n"]); return True  # token-bound: a cancel/stop/new plan before the replay actually starts revokes it
        def _shown(rv):  # runs on the loop when the panel has ACTUALLY been drawn: only input arriving after this point can answer the proposal
            if prop["rev"] == rv and prop["state"] == "pending": prop["shown"] = arr["n"]; prop["displayed"] = True; click_events.append({"gate": "proposal_displayed", "rev": rv, "arrival_epoch": arr["n"]}); log("confirmation: proposal rev %d displayed (arrival epoch %d)" % (rv, arr["n"]))
        def _stop_work(src, preserve_highlight=False):
            if shared_gestures and src not in ('radial-speak', 'shutdown-ingress'):
                shared_gestures.stop()
            if not preserve_highlight:
                highlight_owner.invalidate(retire_context=src != 'radial-speak')
                clear_trail_owned()
            if src != 'radial-speak':
                radial_binding['epoch'] += 1; radial_binding['pending'] = False
                if hover['defer_mic']: _abort_voice('pending hover stopped')
                hover.update(context=None, owner=None, defer_mic=False)
            """Explicit STOP: clear a pending proposal, revoke an approved record and stop whatever plan is running/queued (cursor retired, no later step renders)."""
            request_boundary["n"] += 1
            requests.clear(); request_context_refs.clear()
            _live0 = _goal_live(); _had = prop["state"]
            _prop_clear("stop (%s)" % src)
            if _had == "approved": prop["state"] = "revoked"  # honest record state (pending was already cleared above)
            hl["active_goal"] = None; plan_tok["n"] += 1; clicks.disarm(); _clear_last(); (hl.get('cancel_task') or (lambda *_: None))(); GLib.idle_add(overlay.retire); ov['hidden'] = True; ov['covered'] = False; cur['armed'] = False; cur['paused'] = None; PREV_STEP_POINT['p'] = None
            _note("the user said STOP (%s): any pending/approved/running plan was stopped" % src); click_events.append({"gate": "stop_work", "via": src, "record_state": _had, "was_live": bool(_live0)}); log("confirmation: STOP (%s): pending cleared, approved/queued/running work stopped (record %s, live %s)" % (src, _had, _live0))
        def _revoke_approved(src):
            if prop["state"] != "approved": return False
            prop["state"] = "revoked"; hl["active_goal"] = None; plan_tok["n"] += 1; clicks.disarm(); _clear_last(); (hl.get('cancel_task') or (lambda *_: None))(); GLib.idle_add(overlay.retire)
            click_events.append({"gate": "approved_plan_revoked", "rev": prop["rev"], "hash": prop["hash"], "via": src}); log("confirmation: approved plan rev %d revoked (%s); queued/active execution stopped" % (prop["rev"], src)); return True
        if text_ui: GLib.idle_add(text_ui.show_command)
        async def sync_text_tracking():
            while True:
                frozen = bool(prop['state'] == 'pending' or _goal_live() or gate['turn'] or gate['replay'] or resolving['n'])
                GLib.idle_add(text_ui.set_tracking_frozen, frozen)
                await asyncio.sleep(.016)
        text_tracking_task = asyncio.create_task(sync_text_tracking()) if text_ui else None
        ing["ready"] = True  # every name the ingress latch uses (prop, _STOP, _norm_resp, _stop_work, _goal_live) exists from here on; before this nothing can be live, pending or approved
        i = -1; pend_store = []; cur_vs = [0]; hist = []
        def _note(t): hist.append(("user", "[TipTour app record, not spoken by the user] " + t))  # app-side events the model must not forget across a fresh connection: proposal held/approved/declined/stopped (text only)
          # prior conversation text (role, text), rehydrated into a fresh per-PTT provider connection so model context is not lost  # events a voice turn dequeued but did not consume (e.g. transcript chunks after the turnComplete that ended it) belong to the NEXT utterance of the same voice session: kept here so they are never discarded between turns
        try:
            async for text in _asks():
                typed_reply['active'] = False
                highlight_phase['token'] = None
                i += 1; pause_rs['r'] = None; PREV_STEP_POINT['p'] = None; stream_state['suppressed'] = False  # Mac: user speech / PTT clears the post-tool-call suppression
                _arrv0 = gate.get("arrival", 0); voice_turn = text in ("@voice", "@voice-next"); in_tr = []; seg_pos = [None]; _h0 = len(hist)
                voice_request_boundary = voice_command_boundaries.pop(_arrv0, None) if voice_turn else None
                def voice_request_live():
                    return (voice_request_boundary is not None and voice_request_boundary == request_boundary['n']
                            and cur_vs[0] == vs['n'] and not shutdown['requested'])
                if text == "@voice": pend_store.clear(); cur_vs[0] = cmd_ep.pop(_arrv0, vs["n"])
                def _stale(_k, _v): return voice_turn and _k in ("inputTranscript", "turnComplete") and getattr(_v, "sess", cur_vs[0]) != cur_vs[0]  # a NEW voice session starts clean. A typed/other ask must NOT clear it: the voice stream keeps its chunk chronology (a typed control cannot erase a pre-display prefix while its suffix is still queued)
                pending = pend_store if voice_turn else []
                if not voice_turn: ing["parts"] = []
                _arrv = gate.get("arrival", 0); _m = _re2.fullmatch(r"@(confirm|confirmseparate|cancel) (\d+)", text)
                if text.startswith("@confirm") or text.startswith("@cancel"):  # EXACT "@confirm <rev>" / "@cancel <rev>" only
                    if not _m: log("confirmation: malformed control %r ignored" % text[:40]); click_events.append({"gate": "confirm_malformed"}); results.append({"ask": text, "confirmation": "malformed control ignored"}); continue
                    _kind, _rv = _m.group(1), int(_m.group(2))
                    if prop["state"] not in ("pending", "approved") or _rv != prop["rev"] or _arrv <= (prop.get("shown") or 0) or (prop["state"] == "pending" and not prop.get("displayed")):
                        log("confirmation: %s refused: stale/unbound (pending rev %s, state %s)" % (text, prop["rev"], prop["state"])); click_events.append({"gate": "confirm_refused_stale", "given": str(_rv), "pending": prop["rev"]}); results.append({"ask": text, "confirmation": "refused stale"}); continue
                    if _kind in ("confirm", "confirmseparate") and prop["state"] == "pending":
                        _accepted = _approve_pending("separate-control" if _kind == "confirmseparate" else "control", i)
                        results.append({"ask": text, "confirmation": ("approved rev %d" % prop["rev"]) if _accepted else "not approved"})
                    elif _kind == "cancel" and prop["state"] == "pending": _prop_clear("user declined"); results.append({"ask": text, "confirmation": "declined, nothing executed"})
                    elif _kind == "cancel" and prop["state"] == "approved": _stop_work("control"); results.append({"ask": text, "confirmation": "approved plan revoked"})
                    else: results.append({"ask": text, "confirmation": "no change"})
                    continue
                if not voice_turn and not text.startswith("@") and _norm_resp(text) in _STOP and prop["state"] not in ("pending", "approved") and _goal_live(): _stop_work("text"); results.append({"ask": text, "confirmation": "stopped running work"}); continue  # no record but work is live: STOP still stops it
                if not voice_turn and not text.startswith("@") and prop["state"] in ("pending", "approved"):
                    _r = _norm_resp(text)
                    if _r in _STOP: _stop_work("text"); results.append({"ask": text, "confirmation": "stopped: pending cleared, approved/running work stopped"}); continue
                    if prop["state"] == "approved": pass
                    elif _r in _YES or _r in _NO:
                        if _arrv <= (prop.get("shown") or 0) or not prop.get("displayed"): log("confirmation: %r arrived BEFORE the proposal was displayed; ignored, plan stays pending" % _r); click_events.append({"gate": "answer_before_display_ignored", "rev": prop["rev"]}); results.append({"ask": text, "confirmation": "ignored: arrived before the proposal was displayed"}); continue
                        if _r in _YES:
                            _accepted = _approve_pending("separate-text" if _r in _SEPARATE_YES else "text", i)
                            results.append({"ask": text, "confirmation": ("approved rev %d" % prop["rev"]) if _accepted else "not approved"})
                        else: _prop_clear("user declined"); results.append({"ask": text, "confirmation": "declined, nothing executed"})
                        continue
                    else: _prop_clear("new unrelated request")  # any other user request invalidates the pending plan; it then goes to the model as usual
                if not voice_turn and not text.startswith("@"):
                    with highlight_owner.lock:
                        _rq_status = requests.accept(text, highlight_owner.context, highlight_owner.epoch)
                        request_context_refs[id(highlight_owner.context)] = highlight_owner.context
                    request_turn['key'] = (i, 'typed')
                    click_events.append({"gate": "request_record", "status": _rq_status, "request_id": (requests.snapshot() or {}).get('id')})
                _had_state = prop["state"] if (voice_turn and prop["state"] in ("pending", "approved") and prop["turn"] < i) else None; _had_rev = prop["rev"]  # the record this voice turn may answer
                if voice_turn:
                    if not (mic and (mic.active or hover["defer_mic"])): continue  # toggled off before this turn started
                    _keep = []
                    while not q.empty(): _keep.append(q.get_nowait())
                    for _it in _keep:
                        if _it[0] != "voice_stop": q.put_nowait(_it)  # a stop signal from an earlier session must not end this one
                    if text == "@voice":  # PER-PTT-SESSION FRESH PROVIDER CONNECTION. OWNERSHIP: this attempt owns the voice gate/mic/buffer only while own[0] is unchanged (any newer PTT edge, OFF edge or abort bumps it); cleanup of a failed/superseded attempt NEVER touches a newer owner's state
                        _tc0 = time.time(); _g0 = cmd_gen.pop(_arrv0, edge["n"])
                        if edge["n"] != _g0: click_events.append({"gate": "voice_command_superseded", "at": "dequeue"}); log("voice: this PTT-on was superseded by a newer edge before it started; skipped"); continue
                        _o = own[0]; _pre = gen[0]
                        await _retire(client)  # end the old writer (queued audio is flushed, in-flight send awaited within 3 s, else cancelled and logged) THEN close the old client
                        if own[0] != _o: click_events.append({"gate": "voice_command_superseded", "at": "close"}); continue
                        _pre = gen[0]; _nc = None
                        try: _nc, _nk = await new_session()
                        except Exception as _ex:
                            log("voice: could not open a fresh provider connection (%s); voice is OFF for this press - press PTT again" % type(_ex).__name__); click_events.append({"gate": "voice_fresh_conn_failed", "err": type(_ex).__name__})
                            _abort_voice("fresh connection failed", _o); continue
                        if gen[0] != _pre + 1 or own[0] != _o:
                            click_events.append({"gate": "voice_command_superseded", "at": "connect"}); log("voice: a newer PTT edge superseded this connection; closing it")
                            await _close_bounded(_nc); continue
                        client, key = _nc, _nk; tainted[0] = False; pend_store.clear(); cur_vs[0] = vs["n"]
                        if not await _hydrate(client, True):
                            await _close_bounded(client); _abort_voice("continuity restore failed", _o); continue
                        if gen[0] != _pre + 1 or own[0] != _o:
                            click_events.append({"gate": "voice_command_superseded", "at": "seed"}); log("voice: a newer PTT edge superseded this connection during restore; closing it")
                            await _close_bounded(client); tainted[0] = True; continue
                        if hover['defer_mic']:
                            if shared_gestures and radial_gesture['retired'] or hover['owner'] != own[0] or hover.get('epoch') != radial_binding['epoch'] or not hover_context.alive(hover['context'], own[0]):
                                await _close_bounded(client); _abort_voice('hover context no longer owned', _o); continue
                            try: mic.start()
                            except OSError:
                                await _close_bounded(client); _abort_voice('microphone could not start', _o); continue
                            hover['defer_mic'] = False
                        if hover.get('ready') and not hover['ready'].done(): hover['ready'].set_result(True)
                        _n = _install_writer(client)  # no await between the last ownership check and the install
                        _ms = int((time.time() - _tc0) * 1000); log("voice: fresh provider connection ready in %d ms (%d buffered audio chunks queued in order)" % (_ms, _n)); click_events.append({"gate": "voice_fresh_conn", "ms": _ms, "buffered": _n})
                    text = ""
                if tainted[0]:  # a previous turn never reached a definitive completion: late events could be misattributed, so start a FRESH session explicitly (no silent drain). The OLD generation/gate is invalidated BEFORE any await.
                    log("previous turn did not complete definitively; replacing the session before this request")
                    old = client; gen[0] += 1; vs["n"] += 1; ing["parts"] = []; own[0] += 1; _o = own[0]
                    with vg["lock"]:
                        vg["ready"] = False
                        if vg.get("pq") is not None: _end_pq(vg["pq"])
                        vg["pq"] = None
                    await _retire(old)
                    if voice_turn and own[0] != _o:  # an OFF/newer ON arrived while the old session was being retired: this stale attempt makes NO new connection and changes NO generation/epoch
                        click_events.append({"gate": "voice_command_superseded", "at": "tainted_retire"}); log("voice/session: superseded while retiring the old session; no replacement made (the newer edge owns it)"); tainted[0] = True; continue
                    _pre_t = gen[0]; _fail = None; _nc = None
                    try: _nc, _nk = await new_session()
                    except Exception as _ex: _fail = "could not open a replacement connection (%s)" % type(_ex).__name__
                    if _fail is None and (gen[0] != _pre_t + 1 or (voice_turn and own[0] != _o)):
                        _fail = "a PTT/OFF edge arrived during the replacement"; click_events.append({"gate": "voice_command_superseded", "at": "tainted_replace"})
                        await _close_bounded(_nc)
                    if _fail is None:
                        client, key = _nc, _nk; pend_store.clear(); cur_vs[0] = vs["n"]  # the replaced session's buffered events are stale
                        while not q.empty(): q.get_nowait()
                        if not await _hydrate(client, voice_turn): _fail = "continuity restore failed"; await _close_bounded(client)
                        elif gen[0] != _pre_t + 1 or (voice_turn and own[0] != _o): _fail = "a PTT/OFF edge arrived during the restore"; click_events.append({"gate": "voice_command_superseded", "at": "tainted_restore"}); await _close_bounded(client)
                    if _fail is not None:
                        log("voice/session: %s; this request was NOT sent; the session stays marked for replacement" % _fail); click_events.append({"gate": "tainted_replace_failed", "why": _fail}); tainted[0] = True
                        if voice_turn: _abort_voice(_fail, _o)
                        results.append({"ask": text, "error": _fail + "; the request was NOT sent; try again"}); continue
                    tainted[0] = False
                    if mic and mic.active and voice_turn: _install_writer(client); click_events.append({"gate": "tainted_replace_writer_rebound"})
                with highlight_owner.lock:
                    committed, context_epoch = highlight_owner.context, highlight_owner.epoch
                if a.serve and not voice_turn and not text.startswith("@") and committed:
                    resend_client, resend_generation = client, gen[0]
                    try: await resend_client.send_text(_hl.prompt(committed, ack=False))
                    except Exception as exc:
                        if client is resend_client and gen[0] == resend_generation: tainted[0] = True
                        log('highlight context resend failed (%s); request not sent' % type(exc).__name__)
                        results.append({'ask': text, 'error': 'highlight context resend failed; request not sent'})
                        continue
                    with highlight_owner.lock:
                        if highlight_owner.epoch != context_epoch or highlight_owner.context is not committed or client is not resend_client or gen[0] != resend_generation:
                            if client is resend_client and gen[0] == resend_generation: tainted[0] = True
                            log('highlight context retired during typed resend; request not sent')
                            continue
                    log("serve: re-sent latest highlight context before utterance")
                if text.startswith("@highlight"):
                    try: token = int(text.split()[1])
                    except (ValueError, IndexError):
                        results.append({'ask': text, 'highlight': 'no owned gesture token; nothing sent'}); continue
                    highlight_phase['token'] = token
                    future = highlight_owner.take(token)
                    if not future or not highlight_owner.valid(token): continue
                    try: ctx, ask_chord = await asyncio.wait_for(asyncio.wrap_future(future), 40)
                    except asyncio.TimeoutError: results.append({"ask": text, "highlight": "owned context exceeded 40s"}); continue
                    if not highlight_owner.valid(token): continue
                    if ctx is None: results.append({"ask": text, "highlight": "trail too short (<2 points or <=4px); no context, nothing sent"}); log("highlight: no context"); continue
                    if ask_chord:
                        results.append({"ask": text, "highlight": "ask-chord (Option at release): trail kept LOCAL, nothing sent to the provider", "rect": ctx["rect"]}); log("highlight: ask chord, local only"); continue
                    def hide_current():
                        if highlight_owner.valid(token):
                            highlight_owner.visible = False; hl['trail'].hide()
                    on_gtk(hide_current)
                    try: full, jpeg, size = await asyncio.to_thread(capture_clean, True, False, lambda: highlight_owner.valid(token))
                    except RuntimeError as exc:
                        if str(exc) != 'stale capture discarded': raise
                        log('stale highlight capture discarded; newer gesture retained'); continue  # off the event loop (Skip/Retry/new-ask handling stays responsive during the ~0.3s+ grab); FRESH screenshot, pinned as this request's frame identity
                    full.save(os.path.join(a.out, "highlight-screen-%d.png" % i))
                    if not highlight_owner.valid(token):log("stale highlight capture discarded before provider delivery");continue
                    async def owned(awaitable):
                        if not highlight_owner.valid(token):
                            if hasattr(awaitable, 'close'): awaitable.close()
                            tainted[0] = True
                            return False, None
                        task = asyncio.ensure_future(awaitable)
                        cancelled = asyncio.shield(asyncio.wrap_future(highlight_owner.cancellation(token)))
                        try:
                            done, _ = await asyncio.wait((task, cancelled), return_when=asyncio.FIRST_COMPLETED)
                            if cancelled in done or not highlight_owner.valid(token):
                                task.cancel()
                                await asyncio.wait((task,), timeout=.2)
                                # Already accepted provider bytes cannot be recalled. Replace the
                                # session before another turn; old callbacks cannot enter that turn.
                                tainted[0] = True
                                return False, None
                            return True, task.result()
                        finally:
                            cancelled.cancel()
                            if not task.done(): task.cancel()
                    ok, _ = await owned(client.send_screenshot(jpeg))
                    if not ok: continue
                    ptxt = _hl.prompt(ctx, ack=True); open(os.path.join(a.out, "highlight-prompt-%d.txt" % i), "w").write(ptxt)
                    ok, _ = await owned(client.send_text(ptxt))
                    if not ok: continue
                    out_tr.clear(); t0 = time.time()
                    while time.time() - t0 < 45:
                        try:
                            ok, event = await owned(asyncio.wait_for(q.get(), 5))
                            if not ok: break
                            k, v = event
                        except asyncio.TimeoutError: continue
                        if not highlight_owner.valid(token): break
                        if k == "outputTranscript": out_tr.append(v)
                        elif k == "audio":
                            with highlight_owner.lock:
                                if highlight_owner.valid(token):
                                    (log("voice: reply playback unavailable or backlog exceeded") if player and not player.write(v) else None)
                        elif k == "interrupted":
                            with highlight_owner.lock:
                                if highlight_owner.valid(token): player and player.flush()
                        elif k == "toolCall":
                            ok, _ = await owned(client.tool_response(v["id"], v["name"], {"ok": False, "status": "not_executed", "error": "acknowledgement only; no action yet"}))
                            if not ok: break
                        elif k in ("turnComplete", "closed"): break
                    if not highlight_owner.valid(token): continue
                    if not highlight_owner.commit(token, ctx): continue
                    highlight_phase['token'] = None
                    results.append({"ask": text, "highlight": "sent (fresh screenshot + context prompt)", "rect": ctx["rect"], "window": ctx.get("window"), "reply": "".join(out_tr).strip()}); log("highlight result recorded"); dlog("highlight result", json.dumps(results[-1])[:400]); out_tr.clear()
                    continue
                try:
                    (full, jpeg, size), _oc = await asyncio.to_thread(capture_pinned)
                except RuntimeError as e:
                    if str(e) != "stale capture discarded":raise
                    log("stale ask capture discarded; newer transition retained");continue
                full.save(os.path.join(a.out, "screen-%d.png" % i))
                yolo, ocr_el, _mp, _pcn = await asyncio.to_thread(_perceive, full, True); ask_own = _own_rec((full, jpeg, size), _oc, yolo, ocr_el, _mp, _pcn)  # this ask's OWN capture/perception record: its toolCall resolves bind to it
                if _oc.get("token") != plan_tok["n"]:
                    log("stale ask capture discarded before provider delivery");continue
                if voice_turn and not voice_request_live():
                    click_events.append({'gate': 'voice_startup_owner_refused', 'at': 'before screenshot'}); continue
                native_context = None
                if atspi_resolver:
                    try:
                        native_context = await asyncio.to_thread(atspi_resolver.active_context)
                        if (str(native_context['x11_client_id']) != _oc['pair'][0][0] or
                            native_context['window_name'] != _oc['pair'][0][1] or ident() != _oc['pair'][0]):
                            raise RuntimeError('active native context does not match captured window')
                    except Exception as exc:
                        native_context = None
                        click_events.append({'gate': 'native_context_unavailable', 'error': type(exc).__name__})
                if voice_turn and not voice_request_live(): continue
                _boundary_context = requests.boundary()
                if voice_turn and not _boundary_context and requests.record:
                    await client.send_context('[TipTour prior task provenance, not approval] ' + json.dumps(requests.record) +
                        '\nFor the next complete spoken request, propose requestRelation=continue for modifiers/restatements, separate for independent goals, ambiguous if uncertain. The app preserves old limits and reviews any separate boundary explicitly; do not treat this context as an action request.')
                if _boundary_context:
                    await client.send_context('[TipTour task provenance, not approval] ' + json.dumps(_boundary_context) + '\nInterpret the latest incoming words against the original task. Set requestRelation=continue for a modifier or restatement, separate for an independent goal, ambiguous if unclear. Never discard old limits by assertion. The app alone asks for any task-change approval.')
                if voice_turn and not voice_request_live(): continue
                if native_context:
                    await client.send_context('[TipTour native current-screen facts, not a user request] ' + json.dumps(native_context) +
                        '\nFor actions in this current window use this exact native app name. Do not guess a browser or generic editor name. A non-secret editable focused field shown here is already focused, so typing needs no prerequisite focus click. These facts grant no action or approval.')
                if voice_turn and not voice_request_live(): continue
                if _oc.get('token') != plan_tok['n'] or ident() != _oc['pair'][0]:
                    click_events.append({'gate': 'native_context_capture_retired'}); continue
                await client.send_screenshot(jpeg)
                if voice_turn and not voice_request_live():
                    click_events.append({'gate': 'voice_startup_owner_refused', 'at': 'after screenshot'}); continue
                from PIL import Image as _I; import io as _io; jw,jh=_I.open(_io.BytesIO(jpeg)).size; log("sent JPEG %dx%d (%d bytes) of %dx%d screen" % (jw,jh,len(jpeg), size[0], size[1])); dlog("ask:", repr(text))
                open(os.path.join(a.out,"sent-%d.jpg"%i),"wb").write(jpeg)
                if os.environ.get('FRAME_SETTLE'): await asyncio.sleep(float(os.environ['FRAME_SETTLE']))  # diagnostic only, off by default
                if not voice_turn: await client.send_text(text)
                tool_seen = None; t0 = time.time(); gate_ids = {"handled": set(), "accepted": None}  # Mac CompanionManager handledToolCallIDsThisUtterance / acceptedToolCallIDThisUtterance, reset per utterance (here: per ask/turn)
                tr_state = {"prev": 0, "base": 0}  # base = index into in_tr where the CURRENT Mac "full input transcript" starts (a turnComplete that does not end this loop starts a new transcript; in_tr itself is kept for the turn's recorded text)
                def _cur_tr(): return "".join(in_tr[tr_state["base"]:]).strip()  # the CURRENT full transcript (after the last turnComplete that did not end this loop); every intent/approval consumer reads this, never earlier turns
                def _ingest_tr(_v, boundary=True):  # Mac onInputTranscriptUpdate (CompanionManager 297-314): reset the per-utterance tool-call ids iff the (trimmed) transcript is non-empty AND the previous transcript length was 0 (raw length); then prev = current raw length. turnComplete sets prev = 0 (:317). EVERY inputTranscript append path goes through here.
                    if seg_pos[0] is None and str(_v).strip(): seg_pos[0] = len(hist)  # where this utterance BEGAN in the conversation: its history entry is inserted here so app records made later keep their real place after it
                    in_tr.append(_v); _full = "".join(in_tr[tr_state["base"]:])
                    if boundary and _full.strip() and tr_state["prev"] == 0:
                        gate_ids["handled"].clear(); gate_ids["accepted"] = None; log("utterance boundary: input transcript empty->nonempty, tool-call gate ids reset"); click_events.append({"gate": "utterance_boundary_reset", "transcript_len": len(_full)})
                    tr_state["prev"] = len(_full)
                def _voice_utt(chunks):  # called ONLY when an utterance is FINAL (a turnComplete closed it; a model call is not finality). The WHOLE utterance must be fresh: any chunk that arrived at/before the display (pending) / approval (approved) makes the entire utterance ineligible - never a suffix of it.
                    if not voice_request_live():
                        click_events.append({"gate": "voice_confirmation_owner_refused"}); return None
                    if not chunks or not _had_state or not (prop["state"] == _had_state and prop["rev"] == _had_rev): return None
                    if _had_state == "pending" and not prop.get("displayed"): return None
                    _mark = prop["shown"] if _had_state == "pending" else prop["appr"]
                    _t = "".join(chunks).strip(); _vr = _norm_resp(_t)
                    if not _t: return None
                    if any(getattr(c, "arr", 0) <= _mark for c in chunks): click_events.append({"gate": "utterance_straddles_display_ignored", "text_len": len(_t), "rev": prop["rev"]}); log("confirmation: utterance began at/before the display/approval epoch; the whole utterance is ignored as an answer"); return None
                    dlog("voice_utt: %r state=%s rev=%s" % (_t, _had_state, prop["rev"]))
                    if _vr in _STOP: _stop_work("voice"); return "stopped"
                    if _had_state == "approved":
                        if _vr not in (_YES | _NO):_revoke_approved("new completed voice request")
                        return None
                    if _vr in _YES: return "approved" if _approve_pending("separate-voice" if _vr in _SEPARATE_YES else "voice", i) else "not approved"
                    if _vr in _NO: _prop_clear("user declined (voice)"); return "declined"
                    _prop_clear("new unrelated request (voice)"); return "cleared"
                async def offer_plan(v, args, text, send_reply=True, voice_hover=None):
                    nonlocal tool_seen
                    from . import highlight as _hlg
                    async def reply(payload):
                        if send_reply:
                            await client.tool_response(v["id"], v["name"], payload)
                    _request = requests.snapshot()
                    _task_boundary = None
                    if _request is None and requests.boundary():
                        _candidate_boundary = requests.boundary()
                        _relation = args.get('requestRelation')
                        if _relation in ('continue', 'separate'):
                            import copy as _copy
                            _preview = _copy.deepcopy(requests)
                            with highlight_owner.lock:
                                if _preview.choose_boundary(_candidate_boundary['request_id'], _candidate_boundary['incoming'], _relation == 'separate', highlight_owner.context, highlight_owner.epoch):
                                    _request = _preview.snapshot()
                                    _task_boundary = _candidate_boundary
                    if _request is None:
                        await reply({"ok": False, "status": "not_executed", "error": "No unambiguous original task is bound. Ask the user to restate the complete task and limits; no plan proposed."})
                        click_events.append({"gate": "request_continuity_refused"})
                        return
                    _request_text = _request['text']
                    if native_context:

                        if (args.get('app') or '').strip().casefold() != native_context['app'].strip().casefold():
                            click_events.append({'gate': 'proposal_native_app_mismatch'})
                            await reply({'ok': False, 'status': 'not_executed', 'error': 'The proposed app does not match the native current-window identity. Use the supplied exact app name for this window; nothing proposed or executed.'})
                            return
                    if _hlg.no_action_requested(_request_text):  # original request constraints survive proposal-only continuation; USER intent gate: answer-only request -> no cursor, click, right-click or workflow, whatever the model calls
                        GLib.idle_add(overlay.retire); tool_seen = {"source": "NO_ACTION_REQUESTED", "refused": "user asked for an answer only"}
                        log("tool call suppressed: the request is answer-only (no pointing or action)")
                        _aw = float(os.environ.get('TIPTOUR_ANSWER_WAIT_S', '20')); answer_wait.update(need=True, got=False, until=time.time() + _aw)
                        _resp = _hlg.suppressed_payload(_request_text, _request.get("context"))
                        await reply(_resp)
                        return
                    from .request_limits import forbidden_plan
                    _forbidden = forbidden_plan(_request_text, args)
                    if _forbidden:
                        click_events.append({'gate': 'original_limit_refused', 'reason': _forbidden})
                        await reply({'ok': False, 'status': 'not_executed', 'error': _forbidden})
                        return
                    # Pinned Mac semantic key normalization occurs before displaying/hashing the approval.
                    from .app_skills import normalize_semantic_keyboard_steps
                    from .app_transition import destination
                    _raw_steps = args.get('steps') or []
                    args = dict(args, steps=[normalize_semantic_keyboard_steps([st], destination(args, n)[1] or args.get('app', ''))[0] for n, st in enumerate(_raw_steps)])
                    # Native context is app-owned, deep-copied before immutable approval.
                    hc = voice_hover if voice_turn else None
                    if _hlg.refers_to_highlight(_request_text):
                        with highlight_owner.lock:
                            _scope_live = _request.get('context') is not None and _request.get('context_identity') == id(highlight_owner.context)
                        if not _scope_live:
                            await reply({"ok": False, "status": "not_executed", "error": "The original task's highlight scope is unavailable or changed; restate the task with a fresh highlight."})
                            click_events.append({"gate": "request_scope_retired"})
                            return
                    args = hover_context.bind(args, _request.get('context'), hc)
                    _canon = _plan_canon(args); _ph = _hashlib.sha256(_canon.encode()).hexdigest()  # CONFIRMATION GATE (after the voice transcript wait and the answer-only gate): hold EVERY plan. Nothing resolves, arms, points or clicks before the user approves THIS record.
                    if prop["state"] == "pending" and prop["hash"] == _ph:  # identical plan re-submitted while the user is answering: SAME record, no new revision, the displayed proposal and any valid answer stay bound to it
                        click_events.append({"gate": "same_hash_resubmit_ignored", "id": v["id"], "rev": prop["rev"]}); log("confirmation: identical plan re-submitted (call %s); same record rev %d kept pending" % (v["id"], prop["rev"]))
                        await reply({"ok": False, "reason": "awaiting_user_confirmation", "status": "not_executed", "message": "This exact plan is already proposed and waiting for the user's answer. Do not call any tool again."}); return
                    if prop["state"] == "approved":_revoke_approved("replacement proposal before display")
                    if prop["state"] == "pending": _prop_clear("replaced by a newer proposal")
                    prop.update(rev=prop["rev"] + 1, hash=_ph, args=json.loads(json.dumps(args)), text=_request_text, request=_request, task_boundary=_task_boundary, relation=args.get('requestRelation') if _task_boundary else None, boundary=request_boundary["n"], state="pending", turn=i, id=v["id"], shown=10**12, displayed=False, appr=0)  # shown stays unreachable until the render ack
                    _change_notice = ("TASK CHANGE REQUIRES EXPLICIT REVIEW\nPrevious task and limits: " + _task_boundary['original']['text'] + "\nProposed SEPARATE task: " + _task_boundary['incoming'] + "\nPrevious task limits/scope do not carry to this separate task. Ordinary yes cannot approve this change.\n\n") if _task_boundary and args.get('requestRelation') == 'separate' else ''
                    _pt = _change_notice + "Original request #%s: %s\n" % (_request["id"], _request_text) + _plan_text(args); _note("plan rev %d was PROPOSED and is waiting for the user's yes (nothing executed): %s" % (prop["rev"], _pt.replace("\n", " | ")[:1500])); log("confirmation: plan HELD, rev %d hash %s: %s" % (prop["rev"], _ph[:12], _pt.replace("\n", " | "))); print("PLAN PROPOSAL rev %d:\n%s\n%s" % (prop["rev"], _pt, "Use Start separate task and run to approve this task change, or Cancel." if _task_boundary and args.get('requestRelation') == 'separate' else "Say yes to run it, or no to cancel."), flush=True); GLib.idle_add(lambda _r=prop["rev"], _sep=bool(_task_boundary and args.get('requestRelation') == 'separate'), _pl=_change_notice + "Original request #%s: %s\n\n" % (_request["id"], _request_text) + _plain_text(json.loads(json.dumps(args))).replace("Say yes / Confirm to run, no / Cancel to decline. Say stop to stop.", "Say start separate task and run or use that button to approve the task change and plan. Cancel declines. Stop stops all work." if _task_boundary and args.get('requestRelation') == 'separate' else "Say yes / Confirm to run, no / Cancel to decline. Say stop to stop.").replace("Action mode ON: I will perform the steps below after your yes.", "Action mode ON: I will perform these steps only after explicit separate-task approval." if _task_boundary and args.get('requestRelation') == 'separate' else "Action mode ON: I will perform the steps below after your yes."), _t=_pt: pprop.show_plan(_r, _pl, _t, lambda rv: loop.call_soon_threadsafe(_shown, rv), separate=_sep) and False)  # rev, plain text and raw details are bound IMMUTABLY at scheduling
                    click_events.append({"gate": "plan_held_for_confirmation", "id": v["id"], "rev": prop["rev"], "hash": _ph, "steps": len(args.get("steps") or []), "text_len": len(text or "")})
                    if not voice_turn:
                        typed_reply.update(active=True, rev=prop['rev'], hash=prop['hash'], boundary=request_boundary['n'], generation=gen[0], native_owner=json.loads(json.dumps(native_context)) if native_context else None)
                    await reply({"ok": False, "reason": "awaiting_user_confirmation", "status": "not_executed", "message": "Nothing was done. The app is holding this plan until the USER says yes to it. Tell the user the plan in plain words (what you will do, in what order) and ask them to confirm. Do not call any tool again for this request.\n" + _pt})
                correction = {'error': None, 'attempts': 0, 'boundary': request_boundary['n'], 'request': None, 'voice_text': None}
                voice_candidate = {"call": None}
                turn_audio = [0]; audio_mark = len(audio); answer_wait = {"need": False, "got": False, "until": 0}; saw_event = False; voice_stopped = False
                while time.time() - t0 < 60:
                    try: k, v = pending.pop(0) if pending else await asyncio.wait_for(q.get(), 5)
                    except asyncio.TimeoutError:
                        if voice_turn and not saw_event and not answer_wait["need"]: continue  # idle listening is not a stuck turn
                        if answer_wait["need"] and time.time() > answer_wait["until"]: log("no answer after the suppressed tool call within the wait window"); tainted[0] = True; break
                        continue
                    if shutdown['requested']: break
                    if k == 'typed_proposal_reply_retired' and not voice_turn and all(v.get(key) == value for key,value in {'turn':i,'rev':prop['rev'],'hash':prop['hash']}.items()):
                        try:
                            _watch = prop.get('confirmation_watch')
                            if not _watch or not _watch.valid():raise RuntimeError('confirmation owner changed before native read')
                            _fresh_owner = await asyncio.to_thread(atspi_resolver.active_context, 2) if atspi_resolver else None
                            _fields = ('pid','x11_client_id','window_path','window_name')
                            if not _fresh_owner or any(_fresh_owner.get(key) != (v.get('native_owner') or {}).get(key) for key in _fields) or not _watch.valid():
                                raise RuntimeError('confirmation native owner unavailable at ingress')
                            _retired_client = client
                            _close_task = asyncio.create_task(_retired_client.close())
                            _close_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
                            _done, _pending = await asyncio.wait((_close_task,), timeout=3)
                            if not _done:
                                _close_task.cancel()  # do not await cancellation-resistant transport code
                                raise TimeoutError('provider close deadline')
                            _close_task.result()
                            _owner = v.get('native_owner')
                            _now_owner = await asyncio.to_thread(atspi_resolver.active_context, 2) if atspi_resolver else None
                            _fields = ('pid','x11_client_id','window_path','window_name')
                            if not _owner or not _now_owner or any(_owner.get(key) != _now_owner.get(key) for key in _fields) or not _watch.valid():
                                raise RuntimeError('confirmation native owner changed during provider close')
                        except Exception as exc:
                            # Generation was retired at ingress; failed close never licenses execution.
                            if prop.get('turn') == v['turn'] and prop.get('rev') == v['rev'] and prop.get('hash') == v['hash']:
                                _prop_clear('typed proposal provider retirement failed')
                            click_events.append({'gate':'typed_proposal_retirement_failed','error':type(exc).__name__})
                            log('confirmation: typed proposal provider retirement failed; approval withheld (%s: %s)' % (type(exc).__name__, str(exc))); dlog('confirmation watch trace', getattr(_watch,'events',None))
                        else:
                            log('confirmation: retired typed proposal provider closed')
                        break
                    if _stale(k, v): dlog("stale-epoch event dropped:", k, getattr(v, "sess", None), "turn epoch", cur_vs[0]); click_events.append({"gate": "stale_voice_epoch_dropped", "kind": k}); continue
                    if k in ("audio", "outputTranscript", "inputTranscript", "toolCall"): saw_event = True
                    if k == "audio": audio.extend(v); answer_wait["got"] = True; (log("voice: reply playback unavailable or backlog exceeded") if player and not player.write(v) else None)
                    elif k == "interrupted":
                        player and player.flush()
                        if voice_turn:
                            request_boundary['n'] += 1
                            voice_candidate['call'] = None
                            in_tr.clear(); tr_state.update(prev=0, base=0); seg_pos[0] = None
                            gate_ids['handled'].clear(); gate_ids['accepted'] = None
                            click_events.append({'gate': 'voice_utterance_interrupted', 'candidate_retired': True})
                    elif k == "inputTranscript":
                        _ingest_tr(v)
                    elif k == "voice_stop":
                        if voice_turn: voice_stopped = True; break
                    elif k == "outputTranscript": out_tr.append(v); answer_wait["got"] = True
                    elif k == "toolCall":
                        if correction['error'] and (correction['boundary'] != request_boundary['n'] or
                                (voice_turn and (not voice_request_live() or (correction['voice_text'] and _cur_tr()))) or
                                (correction['request'] is not None and correction['request'] != _plan_canon(requests.snapshot() or requests.boundary()))):
                            click_events.append({'gate':'invalid_plan_correction_retired','reason':'original request owner changed'})
                            break
                        from .plan_validation import structure, semantics
                        _invalid = structure(v)
                        if not _invalid:
                            from .app_transition import destination
                            from .app_skills import normalize_semantic_keyboard_steps
                            _original_args = v['args']
                            _normalized_args = dict(_original_args, steps=[normalize_semantic_keyboard_steps([st], destination(_original_args,n)[1] or _original_args['app'])[0] for n,st in enumerate(_original_args['steps'])])
                            _invalid = semantics(_normalized_args)
                        if _invalid:
                            click_events.append({'gate':'malformed_plan_refused','error':_invalid})
                            log('Invalid plan rejected before proposal: ' + _invalid)
                            correction['error'] = _invalid
                            # Invalid input consumes no accepted tool slot and cannot replace an approved record.
                            if isinstance(v,dict) and isinstance(v.get('id'),str) and isinstance(v.get('name'),str):
                                await client.tool_response(v['id'],v['name'],{'ok':False,'status':'not_executed','reason':'invalid_plan','error':_invalid,'message':'Nothing proposed or executed. Correct and resubmit the full plan for the SAME original user goal and limits. No approval exists for this invalid plan.'})
                            continue
                        args = v.get("args", {}); log("toolCall", v.get("name")); dlog("toolCall args", json.dumps(args))
                        _tid = v.get("id")  # Mac CompanionManager.rejectIfToolCallShouldNotRun (6e97782 lines 611-632), then the same-goal / supersede check of handleToolSubmitWorkflowPlan (674-721)
                        if _tid in gate_ids["handled"]:
                            log("tool: ignoring duplicate %s id=%s" % (v.get("name"), _tid)); click_events.append({"gate": "duplicate", "id": _tid})
                            await client.tool_response(v["id"], v["name"], {"ok": True, "duplicate": True}); continue
                        if gate_ids["accepted"] is not None:
                            gate_ids["handled"].add(_tid); log("tool: rejecting %s id=%s - already accepted tool id=%s for this utterance" % (v.get("name"), _tid, gate_ids["accepted"])); click_events.append({"gate": "tool_already_handled_this_utterance", "id": _tid}); stream_state["hash"] = None  # Mac voiceBackend.invalidateScreenshotHashCache() on this reject (CompanionManager 6e97782:622-623)
                            await client.tool_response(v["id"], v["name"], {"ok": False, "reason": "tool_already_handled_this_utterance", "message": "A tool call has already been accepted for this spoken request. Do not call another tool until the user speaks again."}); continue
                        if v.get("name") != "submit_workflow_plan": log("tool: unsupported tool %r refused (fail closed)" % v.get("name")); click_events.append({"gate": "unknown_tool_refused", "name": str(v.get("name"))}); await client.tool_response(v["id"], v["name"], {"ok": False, "status": "not_executed", "error": "unsupported tool"}); continue
                        _corrected_voice_text = correction["voice_text"]
                        correction["error"] = None
                        gate_ids["handled"].add(_tid); gate_ids["accepted"] = _tid
                        _g = str(args.get("goal") or "").strip()
                        _live = _goal_live()
                        if _g and hl.get("active_goal") and _live and hl["active_goal"].casefold() == _g.casefold():  # Mac: same-goal re-submit while the plan is active (goal arrives via the verbatim Mac schema; a model may paraphrase goals, so this is a heuristic, as on the Mac)
                            log("tool: rejecting submit_workflow_plan - same-goal re-submit of %r" % hl["active_goal"]); click_events.append({"gate": "plan_already_running", "id": _tid})
                            await client.tool_response(v["id"], v["name"], {"ok": False, "reason": "plan_already_running", "message": "This exact plan is already executing on the user's machine. The user reads at human speed; an unchanged screenshot is normal. Do not re-submit this plan. Stay silent and wait for the user to speak again."}); continue
                        # A replacement proposal must not leave old delayed effects running behind pending UI.
                        from . import highlight as _hlg
                        if voice_turn:
                            if not voice_request_live():
                                click_events.append({'gate': 'voice_candidate_refused', 'reason': 'request owner revoked before candidate'})
                                await client.tool_response(v['id'], v['name'], {'ok': False, 'status': 'not_executed', 'error': 'The user stopped or replaced this request.'})
                                continue
                            if _corrected_voice_text:
                                # The original utterance already reached finality before app-owned correction.
                                # No new user utterance or authority is fabricated by the provider continuation.
                                text = _corrected_voice_text
                                await offer_plan(v, args, _corrected_voice_text, voice_hover=hover['context'] if hover_context.alive(hover['context'], own[0]) else None)
                                continue
                            voice_candidate['call'] = json.loads(json.dumps(v))
                            click_events.append({"gate": "voice_candidate_held_until_complete", "id": _tid})
                            await client.tool_response(v["id"], v["name"], {"ok": False, "status": "not_executed", "reason": "awaiting_complete_user_utterance", "message": "This is a nonexecuting candidate only. Finish transcribing the entire current user utterance, including restrictions. No proposal is displayed and nothing may execute before the enclosing turnComplete. Do not resubmit."})
                            continue
                        await offer_plan(v, args, text)
                    elif k == "turnComplete":
                        if voice_turn and voice_request_live() and _cur_tr() and _norm_resp(_cur_tr()) not in (_YES | _NO | _STOP):
                            with highlight_owner.lock:
                                requests.accept(_cur_tr(), highlight_owner.context, highlight_owner.epoch)
                                request_context_refs[id(highlight_owner.context)] = highlight_owner.context
                            request_turn['key'] = (i, tr_state['base'])
                        candidate = voice_candidate.pop('call', None) if voice_turn else None
                        if candidate is not None:
                            if not voice_request_live():
                                click_events.append({'gate': 'voice_candidate_refused', 'reason': 'request owner revoked before finality'})
                            elif not _cur_tr():
                                click_events.append({"gate": "voice_candidate_refused", "reason": "complete utterance missing transcript"})
                            elif _norm_resp(_cur_tr()) not in (_YES | _NO | _STOP):
                                text = _cur_tr()
                                click_events.append({"gate": "voice_candidate_finalized", "id": candidate['id'], "text_len": len(text)})
                                await offer_plan(candidate, candidate.get('args', {}), text, send_reply=False,
                                                 voice_hover=hover['context'] if hover_context.alive(hover['context'], own[0]) else None)
                        if voice_turn: _voice_utt(in_tr[tr_state["base"]:])
                        if voice_turn:
                            _sg = "".join(str(_x) for _x in in_tr[tr_state["base"]:]).strip()
                            if _sg: hist.insert(min(seg_pos[0] if seg_pos[0] is not None else len(hist), len(hist)), ("user", _sg))  # one entry per turnComplete-delimited utterance, at the position where it began
                            seg_pos[0] = None
                        tr_state["prev"] = 0; tr_state["base"] = len(in_tr)  # Mac onTurnComplete: previousInputTranscriptLength = 0; the next transcript is a NEW full transcript
                        if correction['error'] and gate_ids['accepted'] is None and correction['attempts'] < 2:
                            _correction_request = requests.snapshot() or requests.boundary()
                            if (correction['boundary'] == request_boundary['n'] and _correction_request and
                                    (not voice_turn or voice_request_live()) and not shutdown['requested']):
                                correction['attempts'] += 1
                                correction['request'] = _plan_canon(_correction_request)
                                if voice_turn and not correction['voice_text']: correction['voice_text'] = _sg or None
                                _fix = ('[TipTour invalid-plan correction, NOT user approval] The prior plan was rejected before review: ' + correction['error'] +
                                        '\nOriginal complete user task and limits: ' + json.dumps(_correction_request) +
                                        '\nAny unresolved continue/separate relation must remain unresolved until the normal full-plan review; do not drop previous limits. Submit the FULL corrected submit_workflow_plan now for app review. Do not ask for conversational approval first. Correct only invalid structure/key encoding, preserve the original goal, action order, literal values and limits. This is not execution approval; the user must review and confirm the resulting plan.')
                                await client.send_text(_fix)
                                if correction['boundary'] != request_boundary['n'] or (voice_turn and not voice_request_live()):
                                    break
                                click_events.append({'gate':'invalid_plan_correction_requested','attempt':correction['attempts']})
                                continue
                        if correction['error'] and gate_ids['accepted'] is None:
                            log('Invalid plan correction ended without a valid proposal; nothing executed.')
                            click_events.append({'gate':'invalid_plan_correction_unresolved','attempts':correction['attempts']})
                        if answer_wait["need"] and not answer_wait["got"] and time.time() < answer_wait["until"]:  # answer-only request: a turnComplete seen before any spoken answer is not the answer; keep listening (bounded)
                            log("turnComplete before any answer after the suppressed tool call; still waiting (bounded)"); continue
                        break
                    elif k == "closed": log("socket closed"); dlog("socket closed", v); tainted[0] = True; break
                else:
                    if saw_event or not voice_turn: log("turn hit the 60s ceiling without a definitive completion"); tainted[0] = True
                typed_reply['active'] = False  # reply consumer ended: no sentinel can be consumed during tail bookkeeping
                if prop["state"] == "approved" and prop.get("kick"):  # voice approval: this turn body is finished, but the next listening turn would hold gate["turn"] open and the (unbounded-wait) approved replay would never start; release the gate and wait for the replay's real START (not a fixed delay)
                    prop["kick"] = False; gate["turn"] = False
                    while prop["state"] == "approved" and not prop.get("started"): await asyncio.sleep(0.05)
                if k != 'typed_proposal_reply_retired': await asyncio.sleep(1.0 + 0.6)  # let glide finish
                if tool_seen:
                    await asyncio.sleep(a.hold)
                    snap, _, _ = await asyncio.to_thread(grab); snap.save(os.path.join(a.out, "pointed-%d.png" % i))
                if voice_turn and voice_stopped and not _cur_tr() and not saw_event and not tool_seen and not out_tr:
                    log("idle voice listening ended by toggle-off; nothing was said, not recorded as a turn"); continue  # bookkeeping only: an open @voice-next listener that never heard anything
                if voice_turn and not text: text = _cur_tr() or "(voice turn, no transcript)"
                _mt = "".join(out_tr).strip()
                if voice_turn:
                    if _cur_tr(): hist.insert(min(seg_pos[0] if seg_pos[0] is not None else len(hist), len(hist)), ("user", _cur_tr()))  # words after the last turnComplete (normally none)
                elif text and not text.startswith("@"): hist.insert(min(_h0, len(hist)), ("user", text))  # typed text arrives before this turn's app records
                if _mt: hist.append(("model", _mt))
                results.append({"ask": text, "tool": tool_seen, "reply": "".join(out_tr).strip(), "audio_bytes": len(audio) - audio_mark, "audio_bytes_cumulative": len(audio)})
                out_tr.clear()
                if not shutdown['requested'] and voice_turn and mic and mic.active and not voice_stopped: _enq("@voice-next")  # the live voice session stays open until the next Ctrl+Alt press
                log("result recorded (turn %d, tool source %s)" % (i, ((results[-1].get("tool") or {}).get("source", "-")))); dlog("result", json.dumps(results[-1]))
        except asyncio.CancelledError:
            if not shutdown['requested']: raise
            log('shutdown: active body cancelled')
        for _observer in _navigation_observers:
            try: await _observer.close()
            except Exception: pass
        voice_cleanup = {}
        highlight_owner.invalidate(close=True); hl['closed'].set()
        if hl['mon']: voice_cleanup['highlight_monitor'] = await asyncio.to_thread(hl['mon'].close)
        if hl['commit_queue']:
            try: hl['commit_queue'].put_nowait(None)
            except queue.Full: pass
        if hl['commit_worker']:
            await asyncio.to_thread(hl['commit_worker'].join, .5)
            voice_cleanup['highlight_worker'] = not hl['commit_worker'].is_alive()
        if shared_gestures:
            # UI cancellation was posted at shutdown ingress; join only the one
            # native worker here. No GTK cleanup from this asyncio worker thread.
            voice_cleanup['shared_monitor'] = await asyncio.to_thread(shared_gestures.monitor.close)
        elif radial_preview: voice_cleanup['radial_monitor'] = await asyncio.to_thread(radial_preview.monitor.close)
        if ptt_monitor: voice_cleanup['monitor'] = await asyncio.to_thread(ptt_monitor.close)
        if mic:
            if hasattr(mic, 'close'): voice_cleanup['mic'] = await asyncio.to_thread(mic.close)
            else: mic.stop()
        if player: voice_cleanup['player'] = await asyncio.to_thread(player.close)
        if voice_cleanup: click_events.append({'gate': 'voice_cleanup', **voice_cleanup})
        from .shutdown import retire
        cleanup_result = await retire(pipe.get('task'), client)
        click_events.append({'gate': 'shutdown_cleanup', **cleanup_result})
        log('shutdown cleanup:', cleanup_result)
        if text_tracking_task: text_tracking_task.cancel()
        stream_on[0] = False
        if os.environ.get("TIPTOUR_TEST_MODE") == "1":
            try: open(os.path.join(a.out, "overlay_events.json"), "w").write(json.dumps({"events": list(overlay.events), "final": {"mode": overlay.mode, "show_label": bool(overlay.show_label), "retired": bool(getattr(overlay, "retired", False)), "label": overlay.label}}))
            except Exception as e: log("overlay events dump failed", type(e).__name__)
        if audio:
            with wave.open(os.path.join(a.out, "reply.wav"), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(bytes(audio))
        json.dump(results, open(os.path.join(a.out, "results.json"), "w"), indent=1)
        clicks.stop()
        for _v in validators:  # bounded join so a late verdict is not lost; otherwise recorded as pending
            _r = _v.join(10.0)
            if _r == 'pending_at_shutdown': click_events.append({'validator': 'pending_at_shutdown'})
        time.sleep(0.3)  # let the watcher threads append their events
        try: json.dump({"note": "count/ms only; no labels", "inprocess_worker_calls": (atspi_resolver._W.stats if atspi_resolver and atspi_resolver._W else []), "isolated_native_children": (atspi_resolver.sub_stats() if atspi_resolver else [])}, open(os.path.join(a.out, "atspi_worker_stats.json"), "w"), indent=0)
        except Exception: pass
        try: json.dump({"SENSITIVE": "control labels from the owned test page / user's apps; evidence-only, not for logs", "validators": [{"verdict": v_.verdict, "stable": len(v_.stable), "noise": len(v_.noise), "reads": v_.reads} for v_ in validators]}, open(os.path.join(a.out, "validator_reads.json"), "w"), indent=1)
        except Exception: pass
        try: json.dump({"events": click_events, "presses": clicks.presses, "errors": clicks.errors, "thread_starts": clicks.thread_starts, "backend": clicks.backend}, open(os.path.join(a.out, "click_events.json"), "w"))
        except Exception: pass
        if stream_task: stream_task.cancel()
        if pipe.get("task"): pipe["task"].cancel()
        if readonly_harness: await asyncio.to_thread(readonly_harness.stop)
        GLib.idle_add(Gtk.main_quit)

    def runner():
        try: asyncio.run(run())
        except Exception as e:
            log("FATAL", type(e).__name__); dlog("FATAL detail", str(e)[:300]); GLib.idle_add(Gtk.main_quit)
    threading.Thread(target=runner, daemon=True).start()
    Gtk.main()
    if hl["trail"]: hl["trail"].close()
    if status_item: status_item.close()
    if shell_windows['settings']: shell_windows['settings'].destroy()
    if text_ui: text_ui.close()
    if radial_preview: radial_preview.close()
    t = threading.Timer(3.0, lambda: (sys.stderr.write('WATCHDOG: forced exit after 3s (clean shutdown did not finish)\n'), sys.stderr.flush(), os._exit(0))); t.daemon = True; t.start()  # bounded shutdown: a stuck non-daemon thread or in-flight D-Bus call must not hang the process after @quit

if __name__ == "__main__": main()
