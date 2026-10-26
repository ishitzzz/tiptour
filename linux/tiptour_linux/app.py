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
def _local_resolve(lab):
    anchor = PREV_STEP_POINT["p"] or _mouse_location()
    return TARGET_CACHE.resolve(lab, prefer_near_global_point=anchor)
try:
    from . import atspi_resolver
except Exception as _e:
    print('AT-SPI stage unavailable:', type(_e).__name__, str(_e)[:100]); atspi_resolver = None

def main():
    if os.environ.get('TIPTOUR_HANG_DUMP'):  # diagnostic: dump all thread stacks to stderr after N seconds if still running
        import faulthandler; faulthandler.dump_traceback_later(int(os.environ['TIPTOUR_HANG_DUMP']), repeat=False, file=sys.stderr)
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
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    keys = [open(p).read().strip() for p in sorted(glob.glob(a.keys_glob))]
    keys += [k for k in os.environ.get("GEMINI_API_KEYS", "").split(",") if k]
    keys = [k for k in os.environ.get("GEMINI_API_KEYS_FIRST", "").split(",") if k] + keys  # test hook: put (invalid) keys first to exercise real failover
    log_f = open(os.path.join(a.out, "trace.log"), "w")
    def log(*x):
        s = (time.strftime("%H:%M:%S") + (".%03d" % int((time.time() % 1) * 1000) if _os.environ.get("TIPTOUR_LOG_MS") == "1" else "") + " ") + " ".join(map(str, x)); print(s, flush=True); log_f.write(s + "\n"); log_f.flush()
    def dlog(*x):  # detailed lines (window titles, element labels, utterances, replies): only with TIPTOUR_DEBUG_LOG=1; default logs carry no page/user text
        if os.environ.get("TIPTOUR_DEBUG_LOG") == "1": log(*x)
    overlay = PointerOverlay(); overlay.show_all()
    from .overlay import PausePanel
    panel = PausePanel(lambda: (lambda t: _control_post('retry', t))(panel.tok), lambda: (lambda t: _control_post('skip', t))(panel.tok))
    hl = {"loop": None, "q": None, "mon": None, "trail": None}
    if a.highlight:
        from . import highlight as _hl
        from .trail_overlay import TrailOverlay
        _scr = Gdk.Screen.get_default(); hl["trail"] = TrailOverlay(_scr.get_width(), _scr.get_height())
        _commit_q = queue.Queue()
        def _commit_worker():  # context building (incl. the bounded AT-SPI probe) runs OFF the 60Hz sampler thread; commits stay in order
            while True:
                pts, ask_chord = _commit_q.get()
                _t0 = time.time()
                ctx = _hl.build_context(pts, _hl.xdotool_window_at, _hl.atspi_probe if os.environ.get('TIPTOUR_USE_ATSPI', '1') == '1' else None, selection_probe=(__import__('tiptour_linux.cdp_resolver', fromlist=['x']).selection if os.environ.get('TIPTOUR_USE_CDP', '1') == '1' else None))
                print(time.strftime('%H:%M:%S'), 'commit: context built in %.2fs; atspi=%s element=%s selection=%s src=%s dom=%s' % (time.time() - _t0, (ctx or {}).get('atspi_status'), bool(ctx and ctx.get('element')), bool(ctx and ctx.get('text_selection')), ((ctx or {}).get('text_selection') or {}).get('source', 'atspi' if ctx and ctx.get('text_selection') else '-'), (ctx or {}).get('dom_selection_status')), flush=True)
                if hl["loop"]: hl["loop"].call_soon_threadsafe(hl["q"].put_nowait, (ctx, ask_chord))
        threading.Thread(target=_commit_worker, daemon=True, name="commit-worker").start()
        def _commit(pts, ask_chord): _commit_q.put((pts, ask_chord))
        def _warm():  # Chrome builds its AT-SPI tree lazily; poll until an app tree is non-empty (max 40s), serialized with probes by the resolver lock
            from . import atspi_resolver as _ar
            t_end = time.time() + 60
            while time.time() < t_end:  # SHORT slices (3s wall each) so a real request is never stuck behind a long warm walk; Chrome keeps its progress between slices
                try: _ar.probe((0, 0, 1, 1), timeout=3.5, max_nodes=4000, low=True)
                except Exception: pass
                if _ar.ready_bounded(2): break
                time.sleep(1)
        if os.environ.get('TIPTOUR_USE_ATSPI', '1') == '1' and atspi_resolver and os.environ.get('TIPTOUR_NO_WARM') != '1': threading.Thread(target=_warm, daemon=True).start()
        hl["mon"] = _hl.HighlightMonitor(on_begin=lambda p: GLib.idle_add(hl["trail"].set_points, [p]), on_move=lambda p: GLib.idle_add(hl["trail"].set_points, hl["mon"].points), on_commit=_commit); hl["mon"].start()
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
    def _target_valid(app, label, rect):
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
                if (t.get('label') or '').strip().lower() == (label or '').strip().lower() and r and all(abs(r[i] - rect[i]) <= 8 for i in range(4)): return True
        except Exception as e:
            dlog("target_valid error %s" % type(e).__name__); return False
        return False
    from .clickdetect import ClickDetector, guarded_callback
    clicks = ClickDetector(); plan_tok = {"n": 0}; click_events = []; validators = []
    def capture_clean(pin=False, fast=False):
        # own overlay must not appear in frames sent to the model
        _was = [False]; on_gtk(lambda: (_was.__setitem__(0, overlay.get_visible()), overlay.hide()))  # remember whether the follower was shown: it comes back after the grab (persistent buddy), instead of depending on ov['hidden']
        time.sleep(0.05 if fast else 0.25)  # fast = the 1fps context stream: a ~50ms blink instead of the 0.25s per-ask hide (X11 has no ScreenCaptureKit-style window exclusion; the Mac excludes its overlay from capture)
        r = grab()
        if pin: frame_id['v'] = ident(); frame_id['img'] = r[0]  # ask-specific identity: only the per-ask capture pins it; the 1fps stream must not overwrite it
        if _was[0] and not ov.get('covered'): on_gtk(lambda: overlay.show_all())
        return r

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
        if cmd == 'skip' and hl.get('cancel_task'): hl['cancel_task']()  # cancel queued/in-flight Retry/Resume/advance before the Skip takes effect
        """Pause controls for a target whose click was seen but whose effect is unverified/unchanged. Not routed through the model."""
        if cmd in ("retry", "resume") and hl.get("replay"):  # Mac retryCurrentStep()/resume(): re-capture + rerun the full cascade for the active step (resume only while paused, like `guard pausedReason != nil`)
            if tok is not None and tok != plan_tok["n"]:
                click_events.append({"control": cmd + "_refused", "reason": "stale panel"}); log("control %s refused: stale panel" % cmd); return
            _paused = cur.get("paused") or pause_rs["r"] or (bool(validators) and validators[-1].verdict == "unchanged_paused")
            if cmd == "resume" and not _paused:
                click_events.append({"control": "resume_refused", "reason": "not paused"}); log("control resume refused: not paused"); return
            click_events.append({"control": cmd, "mode": "replay_full_cascade", "label": cur.get("label")}); GLib.idle_add(lambda: panel.hide_panel() and False); cur["paused"] = None
            hl["replay"](cmd, plan_tok["n"]); return
        with glock:
            if tok is not None and tok != plan_tok["n"]:  # a panel button queued/clicked for an earlier target or pause episode must never act on a newer one
                click_events.append({"control": cmd + "_refused", "reason": "stale panel"}); log("control %s refused: stale panel (belongs to an earlier target/pause)" % cmd); return
            if not cur.get("label") or not cur.get("armed"):
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
        loop = asyncio.get_running_loop(); q = asyncio.Queue(); hl['loop'] = loop; hl['q'] = asyncio.Queue()
        audio = bytearray(); out_tr = []
        gen = [0]; tainted = [False]
        def _mk_on_event(g):  # events carry the session generation they came from; a replaced (tainted) session can never feed a later turn
            def on_event(k, v):
                if g == gen[0]: loop.call_soon_threadsafe(q.put_nowait, (k, v))
            return on_event
        pool = KeyPool(keys)
        async def new_session():
            gen[0] += 1; oe = _mk_on_event(gen[0])
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
        async def stream_frames():  # Mac GeminiLiveSession.captureAndProcessFrameForGemini: 3.0s timer; skip while suppressed-until-user-speaks or a plan is active; perceptual-hash dedup; else send
            while stream_on[0]:
                try:
                    if stream_state["suppressed"]: stream_state["skipped"]["suppressed"] += 1
                    elif _plan_active(): stream_state["skipped"]["plan_active"] += 1
                    else:
                        _, j, _ = await asyncio.to_thread(lambda: capture_clean(fast=True)); h = _dhash(j); lh = stream_state["hash"]
                        if lh is not None and bin(lh ^ h).count("1") <= 5: stream_state["skipped"]["same_scene"] += 1
                        else: stream_state["hash"] = h; stream_state["sent"] += 1; await client.send_screenshot(j); log("stream frame sent (idle context)", stream_state["sent"], "bytes", len(j)); (open(os.path.join(a.out, "stream-%d.jpg" % stream_state["sent"]), "wb").write(j) if getattr(a, "out", None) else None)
                except Exception as e: log('stream error', type(e).__name__)
                await asyncio.sleep(float(os.environ.get("TIPTOUR_STREAM_INTERVAL", "3.0")))
        stream_task = asyncio.create_task(stream_frames()) if os.environ.get('TIPTOUR_STREAM', '1') == '1' else None
        await asyncio.sleep(2.0 if stream_task else 0)
        serve_q = asyncio.Queue()
        if a.serve:
            def _reader():
                import os as _o
                if not _o.path.exists(a.serve): _o.mkfifo(a.serve)
                while True:
                    with open(a.serve) as f:
                        for line in f:
                            line = line.strip()
                            if line in ('@skip', '@retry', '@resume'): _control_post(line[1:]); continue
                            if line == '@quit': loop.call_soon_threadsafe(q.put_nowait, ('voice_stop', None))  # a live voice turn must not block shutdown
                            if line: loop.call_soon_threadsafe(serve_q.put_nowait, line)
            threading.Thread(target=_reader, daemon=True).start()
            if hl['mon']:
                _orig = hl['mon'].on_commit
                def _both(pts, chord): loop.call_soon_threadsafe(serve_q.put_nowait, "@highlight"); _orig(pts, chord)  # queue the highlight turn FIRST (FIFO) so a following utterance cannot overtake the still-building context
                hl['mon'].on_commit = _both
        player = mic = None
        if a.voice:
            from . import voice as _v
            player = _v.Player(); _w = _v.echo_risk()
            if _w: log('voice warning: ' + _w)
            else: log('voice: source/sink names do not form a loopback; speaker-to-mic acoustic echo is NOT checked (use headphones or echo-cancel)')
            def _chunk(b): asyncio.run_coroutine_threadsafe(client.send_audio(b), loop)
            mic = _v.Mic(_chunk)
            def _ptt():  # Mac: the Control+Option press edge TOGGLES the live voice session
                if mic.active: mic.stop(); loop.call_soon_threadsafe(q.put_nowait, ("voice_stop", None)); log("voice: off")
                else: mic.start(); loop.call_soon_threadsafe(serve_q.put_nowait, "@voice"); log("voice: on")
            _v.PttMonitor(_ptt).start()
        async def _asks():
            if not a.serve:
                for t in a.ask: yield t
            else:
                while True:
                    gate['turn'] = False  # consumer asked for the next item => the previous turn body has finished
                    t = await serve_q.get()
                    (hl.get('cancel_task') or (lambda: None))()  # a new ask cancels an in-flight replay/advance (Mac: start cancels the in-flight resolution)
                    while gate['replay']:  # unbounded: a fresh ask never proceeds while an old replay may still commit (the cancel above ends it as soon as it unwinds)
                        await asyncio.sleep(0.05)
                    gate['turn'] = True
                    if t == "@quit":
                        if mic: mic.stop()
                        if player: player.close()
                        return
                    yield t
        async def _resolve_step(v, args, text, idx=0):  # counts in-progress resolves so an observe auto-advance (650ms) never overlaps one, without waiting for the whole live turn (Mac has no such wait: @MainActor + token)
            resolving["n"] += 1
            try: return await _resolve_step_inner(v, args, text, idx)
            finally: resolving["n"] -= 1
        async def _resolve_step_inner(v, args, text, idx=0):
            tool_seen = None; resp = None
            _steps = args.get("steps") or [{}]
            while idx < len(_steps) and _steps[idx].get("type") == "waitForState":  # Mac WorkflowRunner.swift:680-681: .waitForState is "not yet implemented, skipping" -> advance, never resolved or pointed
                log('[Workflow] step "%s" is .waitForState - not yet implemented, skipping' % (_steps[idx].get("label") or _steps[idx].get("hint") or "")); idx += 1
                if last_call: last_call["idx"] = idx
            if idx >= len(_steps):  # nothing left after the skipped step(s): the plan is complete, no pointer is placed
                with glock:
                    plan_tok["n"] += 1; clicks.disarm(); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire); cur['armed'] = False; cur['paused'] = None; pause_rs['r'] = None; last_call.clear(); PREV_STEP_POINT['p'] = None
                click_events.append({"wait_for_state": "skipped", "plan_complete": True})
                return {"ok": True, "status": "wait_for_state_skipped", "note": "waitForState is not implemented (skipped, as on the Mac); no pointer was placed"}, None
            step = _steps[idx]
            pt = step.get("point_2d")
            if not pt and step.get("box_2d"):
                y1, x1, y2, x2 = step["box_2d"]; pt = [(y1 + y2) // 2, (x1 + x2) // 2]
            nohint = False
            if not pt and (step.get("label") or "").strip(): pt = [500, 500]; nohint = True  # Mac resolves a step WITHOUT a spatial hint label-only (AX -> CDP -> local cache tier 3); the placeholder point is never used: unresolved + nohint = refuse
            if pt:
                px = norm_to_px(pt, size); model_px = px; src = "model_box"
                lab = step.get("label", ""); done = False; ambiguous = 0; refuse = None; bound_rect = None; arm_rect = None; arm_app = None
                if step.get("targetContext") in ("currentSelection", "focusedElement"): refuse = "targetContext %s is not implemented on Linux yet (native selection / focused-element binding is a known gap vs the Mac); not pointing" % step.get("targetContext")  # explicit, never silently ignored
                clicks.disarm(); plan_tok["n"] += 1; _gen0 = plan_tok["n"]  # a skip/cancel/new ask/new target bumps plan_tok: anything resolved under an older generation must not arm or render
                now_id = ident(); dlog('identity pinned=%r now=%r' % (frame_id['v'], now_id))
                if frame_id["v"] and now_id != frame_id["v"]:
                    refuse = "focused window, title or geometry changed since the screenshot (%s -> %s); ask again" % (frame_id["v"][2], now_id[2]); done = True
                if not done and frame_id.get("img") is not None and os.environ.get("TIPTOUR_STALE_FRAME_GUARD", "1") == "1":  # same window can still show different content (voice turns: frame is taken at turn start, speech can come much later)
                    try:
                        _now = await asyncio.to_thread(lambda: capture_clean()[0]); _fr = changed_fraction(frame_id["img"], _now); _tf = (0.0 if nohint else target_changed_fraction(frame_id["img"], _now, px))
                        log("stale-frame check: %.1f%% of frame pixels, %.1f%% around the target changed since the pinned frame (heuristic, not proof of freshness)" % (_fr * 100, _tf * 100))
                        if _fr > float(os.environ.get("TIPTOUR_STALE_FRAME_MAX", "0.03")) or _tf > float(os.environ.get("TIPTOUR_STALE_TARGET_MAX", "0.06")): refuse = "the screen content changed since the screenshot this answer was based on (frame %.0f%%, around target %.0f%%); ask again" % (_fr * 100, _tf * 100); done = True
                    except Exception as _e: log("stale-frame check unavailable: %s" % type(_e).__name__)
                # Mac modal gate (WorkflowRunner :586): if the plan's target app currently shows a blocking dialog, pause instead of resolving (pause reason modalDialogPresented, text "dialog appeared: <title>")
                if not done and not refuse and args.get("app") and atspi_resolver:
                    _ms, _mt = await asyncio.to_thread(atspi_resolver.modal_title, args.get("app"))
                    log("modal check: %s" % ("dialog present" if _mt is not None else ("none" if _ms == "ok" else "unavailable (not treated as 'no dialog')")))
                    if _mt is not None: refuse = "dialog appeared" + (": " + _mt if _mt else "") + " (paused; deal with it, then ask again)"; done = True; click_events.append({"pause": "modalDialogPresented", "title": _mt}); pause_rs['r'] = 'modalDialogPresented'
                # Mac ElementResolver.exactLocalTargetResolution (:95): an explicit target_id / target_mark in the plan step binds to the cache entry first
                _tid = step.get("target_id") or step.get("targetID"); _tmk = step.get("target_mark") if step.get("target_mark") is not None else step.get("targetMark")
                if not done and (_tid or _tmk is not None):
                    _tt = TARGET_CACHE.current_targets(); _m = next((t for t in _tt if (t["id"] == str(_tid).strip() if _tid and str(_tid).strip() else t["mark"] == _tmk)), None)
                    if _m: px = (_half_up(_m["global_center"][0]), _half_up(_m["global_center"][1])); src = "target_cache:exact(%s)" % _m["source"]; done = True; arm_rect = (_m["global_box"][0], _m["global_box"][1], _m["global_box"][2] - _m["global_box"][0], _m["global_box"][3] - _m["global_box"][1])
                    else: log("target_id/target_mark not in the fresh target list; falling through to label resolution")
                # Mac ElementResolver.resolve:218 preferLocalHintBeforeAccessibility: a step that carries a spatial hint (point_2d/box_2d) tries the LOCAL perception cache (label only, anchor = previous step point or cursor) BEFORE AX/CDP
                if not done and pt and not nohint and lab:
                    _lr = _local_resolve(lab)
                    if _lr: px = (_half_up(_lr["global_point"][0]), _half_up(_lr["global_point"][1])); src = "target_cache(hint-first):" + _lr["source"]; done = True; arm_rect = tuple(_lr["global_rect"])
                # Mac order: AX (here AT-SPI) -> local YOLO+OCR refinement -> raw Gemini coordinate
                if atspi_resolver and os.environ.get("TIPTOUR_USE_ATSPI", "1") == "1":
                    try:
                        hits = await asyncio.to_thread(atspi_resolver.resolve, lab)  # off the event loop: a hung AT-SPI read (child killed at its own timeout) must not delay Skip/new-ask handling; the plan_tok check after the await discards a stale result
                        dist = []
                        for t in hits:
                            c = (t["rect"][0] + t["rect"][2] / 2, t["rect"][1] + t["rect"][3] / 2)
                            if not any(abs(c[0] - d[0]) < 30 and abs(c[1] - d[1]) < 30 for d, _ in dist): dist.append((c, t))
                        if len(dist) == 1:
                            rx, ry, rw, rh = dist[0][1]["rect"]; px = (rx + rw // 2, ry + rh // 2); src = "atspi(1 match)"; done = True; arm_rect = (rx, ry, rw, rh); arm_app = dist[0][1].get("app")
                        elif len(dist) > 1:
                            refuse = "ambiguous: %d distinct AT-SPI controls match the label" % len(dist); done = True
                    except Exception as e: log("atspi resolver error", type(e).__name__)
                if not done and os.environ.get("TIPTOUR_USE_CDP", "1") == "1":
                    try:
                        from . import cdp_resolver
                        st, hits = await asyncio.to_thread(cdp_resolver.resolve_ex, lab, size)  # off the loop (blocking CDP I/O); token checked after the await
                        if st == "ok":
                            hh = hits[0]; bound_rect = tuple(hh["rect"]); arm_rect = bound_rect; rx, ry, rw, rh = hh["rect"]; px = (round(rx + rw / 2), round(ry + rh / 2)); src = "cdp_dom(1 match,%s)" % hh["role"]; done = True
                            ok2, why = await asyncio.to_thread(cdp_resolver.revalidate, lab, hh["rect"], size)  # render-time recheck of focus/window/element
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
                    _tr = _local_resolve(lab)  # Mac tier 3 (after AX and CDP): label-only cache resolve, anchor = previous step point or cursor, NOT the model point
                    if _tr: px = (_half_up(_tr["global_point"][0]), _half_up(_tr["global_point"][1])); src = "target_cache:" + _tr["source"]; arm_rect = tuple(_tr["global_rect"])
                    ref = None if (_tr or nohint) else perception.refine_coordinate(model_px, lab, yolo, ocr_el)  # nohint: refine would anchor on the placeholder; Mac: no hint + miss -> unresolved  # Linux-only fallback (not Mac semantics)
                    if ref: px = (round(ref["center"][0]), round(ref["center"][1])); src = "yolo_ocr:" + ref["rule"]
                if nohint and not refuse and src == "model_box": refuse = "could not resolve \"%s\": no matching control and no spatial hint (Mac: resolve returns nothing); not pointing" % lab
                if not refuse and not (0 <= px[0] < size[0] and 0 <= px[1] < size[1]): refuse = "the model's coordinate (%d,%d) is outside the %dx%d screen; not pointing" % (px[0], px[1], size[0], size[1])
                if not refuse and src == "model_box" and hl.get("last_ctx") and any(w in lab.lower() for w in ("highlight", "this", "area", "region")):
                    try:
                        from . import cdp_resolver as _c
                        rx0, ry0, rw0, rh0 = hl["last_ctx"]["rect"]
                        inter = [t for t in _c.all_targets() if not t.get("off") and t["rect"][0] < rx0 + rw0 and t["rect"][0] + t["rect"][2] > rx0 and t["rect"][1] < ry0 + rh0 and t["rect"][1] + t["rect"][3] > ry0 and t["role"] in ("a", "button", "input", "select", "textarea", "summary")]
                        if len(inter) == 1: rr = inter[0]["rect"]; px = (round(rr[0] + rr[2] / 2), round(rr[1] + rr[3] / 2)); src = "highlight_dom(1 control in region)"
                        elif len(inter) > 1: refuse = "the highlighted region contains %d controls (%s); say which one" % (len(inter), ", ".join(sorted({t["label"][:20] for t in inter})[:5]))
                    except Exception as e: log("highlight resolve error", type(e).__name__)
                # Generic scope guard (all sources): if the USER's request refers to the highlight ("highlighted", "this area", "here"...),
                # the final point must lie inside that region. A specific label does not widen the scope. Unrelated requests are unaffected.
                from . import highlight as _hlm
                if not refuse and hl.get("last_ctx") and _hlm.outside_scope(text, hl["last_ctx"]["rect"], px) and src.startswith("cdp_dom(1 match") and bound_rect and _hlm.point_authorized(text):
                    _ip = _hlm.inside_intersection_point(hl["last_ctx"]["rect"], bound_rect)  # ONE uniquely bound element overlaps the user's region and the user asked to be shown: point INSIDE the overlap, never at an outside centre
                    if _ip: px = _ip; src += "+inside_highlight_overlap"; log("moved point inside highlight overlap")
                if not refuse and hl.get("last_ctx") and _hlm.outside_scope(text, hl["last_ctx"]["rect"], px):
                    refuse = "the request refers to the highlighted region, but the resolved target (%s, via %s) is outside it; not pointing" % (step.get("label", "")[:40], src)
                if not refuse and hl.get("last_ctx") and _hlm.outside_window(text, hl["last_ctx"], px):
                    refuse = "the request refers to the highlighted region in window %r, but the resolved target is outside that window; not pointing" % ((hl["last_ctx"].get("window") or {}).get("title", "")[:50],)
                unconf = (not refuse) and src == "model_box"
                _cd_status = None
                def _arm_block(step, px, arm_rect, arm_app, src, refuse=None, _cd_status=None):
                    if not refuse and (step.get("type") or "click") != "observe" and os.environ.get("TIPTOUR_CLICK_DETECT", "1") == "1":  # Mac Teaching mode (a .observe step DISARMS the click detector instead: WorkflowRunner.swift:913-914): arm the listen-only click detector BEFORE the cursor lands; a click on the target completes the one-step plan (Mac WorkflowRunner.stop())
                        _tok = plan_tok["n"]
                        _val = None
                        if os.environ.get("TIPTOUR_CLICK_VALIDATE", "1") == "1" and atspi_resolver and not workflow.bypass_validator(step, _steps[idx + 1] if idx + 1 < len(_steps) else None):  # Mac shouldBypassPostClickValidator (rightClick, or the next step is keyboardShortcut/pressKey/type/setValue/scroll)
                            _val = workflow.ClickValidator(lambda: atspi_resolver.all_targets(timeout=8.0), lambda _n: atspi_resolver.fingerprint(_n, timeout=6.0), px if arm_rect is None else (arm_rect[0] + arm_rect[2] / 2, arm_rect[1] + arm_rect[3] / 2), app_hint=arm_app)
                            validators.append(_val); _val.start_baseline(); threading.Thread(target=lambda _v=_val: (_v.ready.wait(60), log("validator baseline ready: scope_set=%s stable=%d noise=%d err=%s" % (bool(_v.scope), len(_v.stable), len(_v.noise), _v.baseline_error))), daemon=True).start()  # baseline runs in the background; arming and drawing never wait for it
                        def _valid(_src=src, _tok=_tok, _val=_val):
                            if _val is None:
                                log("target click detected; pointer dismissed; validator: not run (right-click or disabled) - effect UNVERIFIED"); click_events.append({"target_clicked": True, "src": _src, "validator": "unavailable:not_run", "effect": "unverified"}); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire); return
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
                            threading.Thread(target=_watch, daemon=True).start()
                        def _stale(): log("click on stale armed target ignored (token mismatch)"); click_events.append({"stale_ignored": True})
                        _clicked = guarded_callback(plan_tok, _tok, _valid, _stale)
                        _ok = clicks.arm(px if arm_rect is None else (arm_rect[0] + arm_rect[2] / 2, arm_rect[1] + arm_rect[3] / 2), arm_rect, _clicked)
                        _cd_status = clicks.backend if _ok else "UNAVAILABLE"
                        if _ok:  # while the target is still pending/paused: hide the pointer when a window covers it or another app takes focus (misleading guidance), show it again when restored
                            def _guard(_tok=_tok, _pt=(px if arm_rect is None else (arm_rect[0] + arm_rect[2] / 2, arm_rect[1] + arm_rect[3] / 2)), _pin=clicks._pin, _lab=step.get("label"), _rect=arm_rect, _app=arm_app, _plan_app=args.get("app")):
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
                _cd_status = _arm_block(step, px, arm_rect, arm_app, src, refuse, None)
                cur.update(label=step.get("label"), step=step, px=px, rect=arm_rect, app=arm_app, src=src, armed=not refuse, pin=clicks._pin, rearm=(lambda s=step, p=px, r=arm_rect, ap=arm_app, sc=src: _arm_block(s, p, r, ap, sc, None, None)))
                with glock:  # atomic with the control thread/guard threads: final generation check + commit of hidden state + render post
                    if not refuse and plan_tok["n"] != _gen0:
                        refuse = "superseded by a skip, cancel or newer request while resolving"  # no disarm here: the superseding transition already disarmed, and this must never disarm a NEWER plan's detector
                    ov['hidden'] = bool(refuse); ov['covered'] = False; GLib.idle_add(lambda: panel.hide_panel() and False)
                    if refuse: GLib.idle_add(overlay.retire)  # a refusal must not leave the previous answer's cursor on screen
                    if not refuse: PREV_STEP_POINT['p'] = (px[0], px[1]); stream_state['suppressed'] = True; log('render cursor at', px, 'src', src); GLib.idle_add(overlay.point_to, px[0], px[1], ("? " if unconf else "") + step.get("label", ""))
                    if not refuse and (step.get("type") or "click") == "observe":  # Mac WorkflowRunner.swift:913-921: .observe = ClickDetector.disarm(), point, then after 650ms advance (never waits for a click) if the operation token is unchanged
                        clicks.disarm(); _otok = plan_tok["n"]; _ot = asyncio.ensure_future(_observe_advance(_otok)); hl["obs_task"] = _ot; click_events.append({"observe": "pointed_no_arm", "auto_advance_ms": 650})
                if ambiguous and src == "model_box": src = "model_box(UNCONFIRMED:%d DOM candidates)" % ambiguous
                tool_seen = {"label": step.get("label"), "point_2d": (None if nohint else pt), "no_hint": nohint, "px": px, "model_px": (None if nohint else model_px), "source": src}
                if _cd_status: tool_seen["click_detector"] = _cd_status
                if refuse: tool_seen["source"] = "REFUSED"; tool_seen["refused"] = refuse; log("refused to point (reason in debug log only)"); dlog("refused to point:", refuse)
                if refuse: resp = {"ok": False, "status": "not_pointed", "error": refuse}
                elif a.act and (step.get("type") or "click") in ("click", "doubleClick", "rightClick") and not _hlg.action_matches_intent(step.get("type") or "click", text):
                    log("action NOT executed: the user's words do not ask for a %s" % (step.get("type") or "click"))
                    resp = {"ok": False, "status": "not_executed", "error": "The user's request does not ask for this action; the cursor was only pointed. Tell the user where it is and let them act."}
                elif a.act and (step.get("type") or "click") in ("click", "doubleClick", "rightClick"):
                    from . import actions
                    time.sleep(1.0)  # let the pointer land first, like Mac (point then act)
                    resp = actions.execute(step, px); log("action executed, ok=%s" % resp.get("ok")); dlog("action", json.dumps(resp))
                elif unconf: resp = {"ok": False, "status": "pointed_unconfirmed", "note": "The cursor was placed from the vision estimate only; no UI element or page element confirmed it. Do not claim it is on the target. Tell the user it is a guess and ask them to confirm."}
                else: resp = {"ok": True, "status": "pointed", "note": "point-only mode; user must click"}
            else:
                resp = {"ok": False, "error": "no coordinates"}
            return resp, tool_seen

        def _perceive(full):
            yolo = detector.detect(full) if detector else []
            ocr_el = perception.ocr(full.resize((full.width*2, full.height*2))) if detector else []
            for e in ocr_el: e['bbox']=[v/2 for v in e['bbox']]; e['center']=[v/2 for v in e['center']]
            log('perception: %d yolo boxes, %d ocr lines' % (len(yolo), len(ocr_el)))
            TARGET_CACHE.update([{'bbox': [b['bbox'][0], b['bbox'][1], b['bbox'][0] + b['bbox'][2], b['bbox'][1] + b['bbox'][3]], 'label': b.get('label') or '', 'source': 'yolo', 'conf': b.get('conf', 0)} for b in yolo] + [{'bbox': [e['bbox'][0], e['bbox'][1], e['bbox'][0] + e['bbox'][2], e['bbox'][1] + e['bbox'][3]], 'label': e.get('label') or '', 'source': 'ocr', 'conf': e.get('conf', 0)} for e in ocr_el], size, (0, 0, size[0], size[1]))  # Mac: LocalPerceptionTargetCache.update after each perception pass
            return yolo, ocr_el
        last_call = {}; hl['last_call'] = last_call
        def _cancel_task():
            """Mac cancels the in-flight resolution task BEFORE every transition (skip/advance/start/stop/resume/retry). Loop-thread only."""
            _ob = hl.get('obs_task')
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
            while gate['turn'] or gate['replay']:  # never overlaps a live turn's capture/resolve; waits UNBOUNDED (a transition is never silently dropped): ends by the turn finishing, or by a newer transition cancelling this task
                if tok0 is not None and tok0 != plan_tok['n']: break
                await asyncio.sleep(0.1)
            if not c: click_events.append({"control": kind + "_refused", "reason": "no active step"}); log("control %s refused: no active step" % kind); return
            if tok0 is not None and tok0 != plan_tok['n']: click_events.append({"control": kind + "_refused", "reason": "superseded"}); log("control %s refused: superseded by a skip or a newer target while waiting" % kind); return
            gate['replay'] = True
            try:
                pause_rs['r'] = None
                full, jpeg, size = await asyncio.to_thread(capture_clean, True)
                yolo, ocr_el = await asyncio.to_thread(_perceive, full)
                if tok0 is not None and tok0 != plan_tok['n']: click_events.append({"control": kind + "_refused", "reason": "superseded after capture"}); log("control %s refused: superseded by a skip or a newer target during capture" % kind); return
                resp, ts = await _resolve_step(c["v"], c["args"], c["text"], c.get("idx", 0))
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
                        plan_tok["n"] += 1; clicks.disarm(); ov['hidden'] = True; ov['covered'] = False; GLib.idle_add(overlay.retire); cur['armed'] = False; cur['paused'] = None; pause_rs['r'] = None; last_call.clear(); PREV_STEP_POINT['p'] = None
                    click_events.append({"advance": kind, "plan_complete": True}); log("advance (%s): no next step, plan complete" % kind); return
                last_call["idx"] = c["idx"] + 1; pause_rs['r'] = None
                full, jpeg, size = await asyncio.to_thread(capture_clean, True)
                yolo, ocr_el = await asyncio.to_thread(_perceive, full)
                if tok0 is not None and tok0 != plan_tok['n']: last_call["idx"] = c["idx"]; click_events.append({"advance": kind, "refused": "superseded after capture"}); log("advance (%s) refused: superseded during capture" % kind); return
                resp, ts = await _resolve_step(c["v"], c["args"], c["text"], c["idx"] + 1)
                click_events.append({"advance": kind, "to_step": c["idx"] + 1, "of": n, "source": (ts or {}).get("source"), "refused": (ts or {}).get("refused")}); log("advance (%s): step %d of %d resolved -> %s" % (kind, c["idx"] + 2, n, (ts or {}).get("source")))
            finally: gate['replay'] = False
        hl['advance'] = lambda kind, tok0=None: _spawn(_advance_step(kind, tok0))
        hl['replay'] = lambda kind, tok0=None: _spawn(_replay_step(kind, tok0))
        i = -1
        async for text in _asks():
            i += 1; pause_rs['r'] = None; PREV_STEP_POINT['p'] = None; stream_state['suppressed'] = False  # Mac: user speech / PTT clears the post-tool-call suppression
            voice_turn = text in ("@voice", "@voice-next"); in_tr = []; pending = []
            if voice_turn:
                if not (mic and mic.active): continue  # toggled off before this turn started
                _keep = []
                while not q.empty(): _keep.append(q.get_nowait())
                for _it in _keep:
                    if _it[0] != "voice_stop": q.put_nowait(_it)  # a stop signal from an earlier session must not end this one
                if text == "@voice" and hl.get("last_ctx") and os.environ.get("TIPTOUR_VOICE_CTX", "seed") == "seed":  # silent seed: no model turn until the user speaks
                    await client.send_context(_hl.prompt(hl["last_ctx"], ack=False)); log("voice: seeded latest highlight context silently (no turn)")
                text = ""
            if tainted[0]:  # a previous turn never reached a definitive completion: late events could be misattributed, so start a FRESH session explicitly (no silent drain)
                log("previous turn did not complete definitively; replacing the session before this request")
                old = client
                try: await asyncio.wait_for(old.close(), 3)
                except Exception: pass
                client, key = await new_session(); tainted[0] = False
                while not q.empty(): q.get_nowait()
            if a.serve and not voice_turn and not text.startswith("@") and hl.get("last_ctx"):  # Mac resends the latest highlight context at the start of each new utterance while a session is live
                await client.send_text(_hl.prompt(hl["last_ctx"], ack=False)); log("serve: re-sent latest highlight context before utterance")
            if text.startswith("@highlight"):
                try: ctx, ask_chord = await asyncio.wait_for(hl['q'].get(), 40)
                except asyncio.TimeoutError: results.append({"ask": text, "highlight": "no trail committed in 40s"}); continue
                if ctx is None: results.append({"ask": text, "highlight": "trail too short (<2 points or <=4px); no context, nothing sent"}); log("highlight: no context"); continue
                if ask_chord:
                    results.append({"ask": text, "highlight": "ask-chord (Option at release): trail kept LOCAL, nothing sent to the provider", "rect": ctx["rect"]}); log("highlight: ask chord, local only"); continue
                on_gtk(hl["trail"].hide); full, jpeg, size = capture_clean(pin=True)  # FRESH screenshot, pinned as this request's frame identity
                full.save(os.path.join(a.out, "highlight-screen-%d.png" % i))
                await client.send_screenshot(jpeg)
                ptxt = _hl.prompt(ctx, ack=True); open(os.path.join(a.out, "highlight-prompt-%d.txt" % i), "w").write(ptxt)
                await client.send_text(ptxt); out_tr.clear(); t0 = time.time()
                while time.time() - t0 < 45:
                    try: k, v = await asyncio.wait_for(q.get(), 5)
                    except asyncio.TimeoutError: continue
                    if k == "outputTranscript": out_tr.append(v)
                    elif k == "audio": player and player.write(v)
                    elif k == "interrupted": player and player.flush()
                    elif k == "toolCall": await client.tool_response(v["id"], v["name"], {"ok": False, "status": "not_executed", "error": "acknowledgement only; no action yet"})
                    elif k in ("turnComplete", "closed"): break
                hl['last_ctx'] = ctx
                results.append({"ask": text, "highlight": "sent (fresh screenshot + context prompt)", "rect": ctx["rect"], "window": ctx.get("window"), "reply": "".join(out_tr).strip()}); log("highlight result recorded"); dlog("highlight result", json.dumps(results[-1])[:400]); out_tr.clear()
                continue
            full, jpeg, size = capture_clean(pin=True)
            full.save(os.path.join(a.out, "screen-%d.png" % i))
            yolo, ocr_el = _perceive(full)
            await client.send_screenshot(jpeg)
            from PIL import Image as _I; import io as _io; jw,jh=_I.open(_io.BytesIO(jpeg)).size; log("sent JPEG %dx%d (%d bytes) of %dx%d screen" % (jw,jh,len(jpeg), size[0], size[1])); dlog("ask:", repr(text))
            open(os.path.join(a.out,"sent-%d.jpg"%i),"wb").write(jpeg)
            if os.environ.get('FRAME_SETTLE'): await asyncio.sleep(float(os.environ['FRAME_SETTLE']))  # diagnostic only, off by default
            if not voice_turn: await client.send_text(text)
            tool_seen = None; t0 = time.time()
            turn_audio = [0]; audio_mark = len(audio); answer_wait = {"need": False, "got": False, "until": 0}; saw_event = False; voice_stopped = False
            while time.time() - t0 < 60:
                try: k, v = pending.pop(0) if pending else await asyncio.wait_for(q.get(), 5)
                except asyncio.TimeoutError:
                    if voice_turn and not saw_event and not answer_wait["need"]: continue  # idle listening is not a stuck turn
                    if answer_wait["need"] and time.time() > answer_wait["until"]: log("no answer after the suppressed tool call within the wait window"); tainted[0] = True; break
                    continue
                if k in ("audio", "outputTranscript", "inputTranscript", "toolCall"): saw_event = True
                if k == "audio": audio.extend(v); answer_wait["got"] = True; player and player.write(v)
                elif k == "interrupted": player and player.flush()
                elif k == "inputTranscript":
                    in_tr.append(v)
                elif k == "voice_stop":
                    if voice_turn: voice_stopped = True; break
                elif k == "outputTranscript": out_tr.append(v); answer_wait["got"] = True
                elif k == "toolCall":
                    args = v.get("args", {}); log("toolCall", v.get("name")); dlog("toolCall args", json.dumps(args))
                    from . import highlight as _hlg
                    if voice_turn:  # the user's words come from the input transcript, which can lag the toolCall: wait (bounded), buffering other events
                        _dl = time.time() + 3.0
                        while not "".join(in_tr).strip() and time.time() < _dl:
                            try: _k2, _v2 = await asyncio.wait_for(q.get(), 0.3)
                            except asyncio.TimeoutError: continue
                            (in_tr.append(_v2) if _k2 == "inputTranscript" else pending.append((_k2, _v2)))
                        if "".join(in_tr).strip():
                            _dl = time.time() + 0.7  # let the last transcript chunks land
                            while time.time() < _dl:
                                try: _k2, _v2 = await asyncio.wait_for(q.get(), 0.2)
                                except asyncio.TimeoutError: continue
                                (in_tr.append(_v2) if _k2 == "inputTranscript" else pending.append((_k2, _v2)))
                        text = "".join(in_tr).strip()
                        if not text:
                            log("voice: no transcript of the spoken request; refusing to act or point")
                            await client.tool_response(v["id"], v["name"], {"ok": False, "status": "not_executed", "error": "The spoken request could not be transcribed; ask the user to repeat it. Do not point."}); continue
                    if _hlg.no_action_requested(text):  # USER intent gate: answer-only request -> no cursor, click, right-click or workflow, whatever the model calls
                        GLib.idle_add(overlay.retire); tool_seen = {"source": "NO_ACTION_REQUESTED", "refused": "user asked for an answer only"}
                        log("tool call suppressed: the request is answer-only (no pointing or action)")
                        _aw = float(os.environ.get('TIPTOUR_ANSWER_WAIT_S', '20')); answer_wait.update(need=True, got=False, until=time.time() + _aw)
                        _resp = _hlg.suppressed_payload(text, hl.get("last_ctx"))
                        await client.tool_response(v["id"], v["name"], _resp)
                        continue
                    last_call.update(v=v, args=args, text=text, idx=0)
                    resp, tool_seen = await _resolve_step(v, args, text)
                    await client.tool_response(v["id"], v["name"], resp)
                elif k == "turnComplete":
                    if answer_wait["need"] and not answer_wait["got"] and time.time() < answer_wait["until"]:  # answer-only request: a turnComplete seen before any spoken answer is not the answer; keep listening (bounded)
                        log("turnComplete before any answer after the suppressed tool call; still waiting (bounded)"); continue
                    break
                elif k == "closed": log("socket closed"); dlog("socket closed", v); tainted[0] = True; break
            else:
                if saw_event or not voice_turn: log("turn hit the 60s ceiling without a definitive completion"); tainted[0] = True
            await asyncio.sleep(1.0 + 0.6)  # let glide finish
            if tool_seen:
                await asyncio.sleep(a.hold)
                snap, _, _ = grab(); snap.save(os.path.join(a.out, "pointed-%d.png" % i))
            if voice_turn and voice_stopped and not "".join(in_tr).strip() and not saw_event and not tool_seen and not out_tr:
                log("idle voice listening ended by toggle-off; nothing was said, not recorded as a turn"); continue  # bookkeeping only: an open @voice-next listener that never heard anything
            if voice_turn and not text: text = "".join(in_tr).strip() or "(voice turn, no transcript)"
            results.append({"ask": text, "tool": tool_seen, "reply": "".join(out_tr).strip(), "audio_bytes": len(audio) - audio_mark, "audio_bytes_cumulative": len(audio)})
            out_tr.clear()
            if voice_turn and mic and mic.active and not voice_stopped: serve_q.put_nowait("@voice-next")  # the live voice session stays open until the next Ctrl+Alt press
            log("result recorded (turn %d, tool source %s)" % (i, ((results[-1].get("tool") or {}).get("source", "-")))); dlog("result", json.dumps(results[-1]))
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
        if mic: mic.stop()
        if player: player.close()
        await client.close(); GLib.idle_add(Gtk.main_quit)

    def runner():
        try: asyncio.run(run())
        except Exception as e:
            log("FATAL", type(e).__name__); dlog("FATAL detail", str(e)[:300]); GLib.idle_add(Gtk.main_quit)
    threading.Thread(target=runner, daemon=True).start()
    Gtk.main()
    t = threading.Timer(3.0, lambda: (sys.stderr.write('WATCHDOG: forced exit after 3s (clean shutdown did not finish)\n'), sys.stderr.flush(), os._exit(0))); t.daemon = True; t.start()  # bounded shutdown: a stuck non-daemon thread or in-flight D-Bus call must not hang the process after @quit

if __name__ == "__main__": main()
