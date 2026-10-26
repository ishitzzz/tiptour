"""Ask harness for Linux/X11: hold Ctrl+Alt+Shift, speak a question; on release a preview opens (screenshot + transcript);
Copy text / Copy image / Insert as DRAFT into the app that was focused at press. Nothing is sent or submitted.
Source: Ask/AskHarnessShortcut.swift (chord), AskHarnessCore.swift (session gate, clipboard ownership), AskHarnessController.swift
(press: capture screen + start transcriber; release: stop, publish only if generation current), AskDraftStager.swift (focus-checked paste).
Differences / NOT ported: scribble compositing (annotation, excluded by the user), Mac on-device SFSpeech (here: offline Vosk if installed),
NSPasteboard changeCount (X11 has none: ownership is a read-back hash compare), AX focused-element check (here: X active window id).
Insert uses xdotool key ctrl+v, so it needs X11/XWayland focus; target apps are not guaranteed to accept it."""
import hashlib, io, json, os, subprocess, sys, threading, time, wave

class SessionGate:
    """Mirror of AskSessionGate: idle/capturing/finishing with a generation; stale finishes cannot publish."""
    def __init__(s): s.phase, s.gen = "idle", 0
    def begin(s):
        if s.phase != "idle": return None
        s.gen += 1; s.phase = "capturing"; return s.gen
    def begin_finish(s):
        if s.phase != "capturing": return None
        s.phase = "finishing"; return s.gen
    def cancel(s):
        s.gen += 1
        if s.phase == "capturing": s.phase = "idle"
    def finished(s):
        if s.phase == "finishing": s.phase = "idle"
    def may_publish(s, g): return g == s.gen and s.phase == "finishing"

def is_ask_chord(mask):
    from . import highlight as h
    return bool(mask & h.CTRL) and bool(mask & h.ALT) and bool(mask & h.SHIFT) and not (mask & h.SUPER)

class Clipboard:
    """X11 clipboard via xclip. Ownership = hash of what WE staged; before a paste we read back and refuse if someone else changed it.
    Previous clipboard policy (explicit): snapshot every real target before our FIRST stage. Restore happens only if the clipboard is still exactly ours.
    xclip can offer one format per process, so if the previous clipboard holds more than one distinct format (text aliases count as one) or cannot be read,
    we REFUSE before overwriting anything (no lossy restore). Truly empty previous clipboard: we cannot clear X11 selections, so our staged data stays and that is reported. If anything else changed the clipboard during paste/restore, we never touch it."""
    META = {"TARGETS", "TIMESTAMP", "MULTIPLE", "SAVE_TARGETS", "DELETE", "INSERT_PROPERTY", "INSERT_SELECTION", "LENGTH", "ATOM", "ATOM_PAIR", "NULL"}
    def __init__(s): s.owned = None; s.prev = {}; s.mime = None
    @staticmethod
    def _targets():
        r = subprocess.run(["xclip", "-selection", "clipboard", "-o", "-t", "TARGETS"], capture_output=True, timeout=5)
        return [t for t in r.stdout.decode(errors="ignore").split() if t not in Clipboard.META] if r.returncode == 0 else []
    @staticmethod
    def _read(target="UTF8_STRING"):
        r = subprocess.run(["xclip", "-selection", "clipboard", "-o", "-t", target], capture_output=True, timeout=5); return r.stdout if r.returncode == 0 else None
    TEXT_ALIASES = {"UTF8_STRING", "STRING", "TEXT", "COMPOUND_TEXT", "text/plain", "text/plain;charset=utf-8"}
    @staticmethod
    def distinct_formats(prev):
        return {("text" if t in Clipboard.TEXT_ALIASES else t) for t in prev}
    def _snapshot(s):
        out = {}
        for t in s._targets():
            if t in ("STRING", "TEXT", "COMPOUND_TEXT") and "UTF8_STRING" in out: continue
            d = s._read(t)
            if d: out[t] = d
        return out
    def stage(s, payload, mime):  # raises RuntimeError (nothing overwritten) when the previous clipboard cannot be preserved exactly
        if s.owned is None:
            s.prev = s._snapshot(); fm = s.distinct_formats(s.prev)
            if len(fm) > 1: s.prev = {}; raise RuntimeError("cannot preserve previous clipboard (%d formats: %s); nothing overwritten" % (len(fm), ", ".join(sorted(fm))))
            if s._targets() and not s.prev: raise RuntimeError("cannot read previous clipboard contents; nothing overwritten")
        elif s.read_hash() != s.owned: s.owned = None; raise RuntimeError("clipboard changed by others")  # refuse this time; the next explicit stage re-snapshots
        s._write(payload, mime); s.owned = hashlib.sha256(payload).hexdigest(); s.mime = mime
    @staticmethod
    def _write(data, mime):
        p = subprocess.Popen(["xclip", "-selection", "clipboard", "-t", mime, "-i"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        p.stdin.write(data); p.stdin.close(); time.sleep(0.15)
    def read_hash(s):
        d = s._read(s.mime) if s.owned else None
        return hashlib.sha256(d).hexdigest() if d is not None else None
    def still_ours(s): return s.owned is not None and s.read_hash() == s.owned
    def restore(s):
        """Returns a status string; see class doc."""
        if not s.owned: return "nothing staged"
        if not s.still_ours(): s.owned = None; return "clipboard changed by others; left untouched"
        prev, s.owned = s.prev, None
        if not prev: return "previous clipboard empty/unreadable; staged data left in place"
        pick = "image/png" if "image/png" in prev else "UTF8_STRING" if "UTF8_STRING" in prev else next(iter(prev))
        s._write(prev[pick], pick)
        return "restored previous %s" % pick

def active_window():
    r = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True); return r.stdout.strip() if r.returncode == 0 else None

def open_windows():
    """[(wid, wm_class, title)] of viewable top-level windows with a title (xdotool/xprop). Used only for the local chooser UI."""
    out = []
    r = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "."], capture_output=True, text=True)
    for wid in r.stdout.split():
        n = subprocess.run(["xdotool", "getwindowname", wid], capture_output=True, text=True).stdout.strip()
        c = subprocess.run(["xprop", "-id", wid, "WM_CLASS"], capture_output=True, text=True).stdout
        cls = c.split("=")[-1].replace('"', "").split(",")[-1].strip() if "=" in c else ""
        t = subprocess.run(["xprop", "-id", wid, "_NET_WM_WINDOW_TYPE"], capture_output=True, text=True).stdout
        if n and cls and "_NET_WM_WINDOW_TYPE_NORMAL" in t and "TipTour Ask preview" not in n: out.append((wid, cls, n))  # normal application windows only (no WM helper/dock/desktop windows)
    return out

def resolve_target(default_win, wm_class):
    """Chosen target class -> window id. Empty class = the window focused at press. Refuses (None, reason) when the class has 0 or >1 windows."""
    if not wm_class: return default_win, None
    ws = [w for w in open_windows() if w[1] == wm_class]
    if len(ws) != 1: return None, "target app %s has %d matching windows; pick the window focused at press instead" % (wm_class, len(ws))
    return ws[0][0], None

def insert_draft(clip, text, target_win):
    """Draft-only paste into the window that was focused at press. Refuses on focus change or clipboard change. Never presses Enter."""
    if not target_win: return "refused: no target window recorded"
    subprocess.run(["xdotool", "windowactivate", "--sync", target_win], capture_output=True, timeout=5); time.sleep(0.2)
    if active_window() != target_win: return "refused: target window did not take focus"
    try: clip.stage(text.encode(), "UTF8_STRING")
    except Exception as e: return "refused: " + str(e) if ("changed by others" in str(e) or "cannot " in str(e)) else "refused: could not stage clipboard (%s)" % type(e).__name__
    if not clip.still_ours(): return "refused: clipboard changed before paste"
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"], timeout=5); time.sleep(0.3)
    return "inserted as draft (not sent); clipboard: " + clip.restore()

class Transcriber:
    """Offline Vosk transcription of the PCM16/16k mic stream captured while the chord is held."""
    def __init__(s, model_dir=None):
        s.model_dir = model_dir or os.environ.get("TIPTOUR_VOSK_MODEL", ""); s.buf = bytearray()
    def feed(s, b): s.buf += b
    def result(s):
        try:
            import vosk; vosk.SetLogLevel(-1)
            if not os.path.isdir(s.model_dir): return "", "no speech model (set TIPTOUR_VOSK_MODEL to a Vosk model dir)"
            r = vosk.KaldiRecognizer(vosk.Model(s.model_dir), 16000); r.AcceptWaveform(bytes(s.buf)); return json.loads(r.FinalResult()).get("text", ""), None
        except ImportError: return "", "vosk not installed"

class Controller:
    def __init__(s, show, model_dir=None):
        from . import capture, voice
        s.cap, s.voice, s.show, s.gate, s.sess, s.model_dir, s.clip = capture, voice, show, SessionGate(), None, model_dir, Clipboard()
        s.mic = None
    def press(s):
        g = s.gate.begin()
        if g is None: return "busy"
        tr = Transcriber(s.model_dir); s.mic = s.voice.Mic(tr.feed); s.mic.start()
        full, jpg, size = s.cap.grab(max_w=1600)
        s.sess = dict(gen=g, tr=tr, img=full, win=active_window(), t0=time.time()); return "capturing"
    def release(s):
        sess = s.sess; g = s.gate.begin_finish()
        if g is None or sess is None or sess["gen"] != g: return None
        s.sess = None
        if s.mic: s.mic.stop()
        def fin():
            try:
                text, err = sess["tr"].result()
                if not s.gate.may_publish(g): return
                s.show(dict(image=sess["img"], text=text, err=err, win=sess["win"], seconds=round(time.time() - sess["t0"], 1)), s)
            finally: s.gate.finished()
        threading.Thread(target=fin, daemon=True).start(); return "finishing"
    def copy_text(s, text):
        try: s.clip.stage(text.encode(), "UTF8_STRING"); return "copied text"
        except Exception as e: return "refused: " + str(e) if ("changed by others" in str(e) or "cannot " in str(e)) else "refused: copy failed (%s)" % type(e).__name__
    def copy_image(s, img):
        b = io.BytesIO(); img.convert("RGB").save(b, "PNG")
        try: s.clip.stage(b.getvalue(), "image/png"); return "copied image"
        except Exception as e: return "refused: " + str(e) if ("changed by others" in str(e) or "cannot " in str(e)) else "refused: copy failed (%s)" % type(e).__name__
    def insert(s, text, win, wm_class=""):
        t, why = resolve_target(win, wm_class)
        return "refused: " + why if why else insert_draft(s.clip, text, t)

def gtk_preview(draft, ctl, on_status=print):
    """GTK3 preview: screenshot thumbnail, editable question, Copy text / Copy image / Insert draft / Cancel."""
    import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk, GdkPixbuf, GLib
    w = Gtk.Window(title="TipTour Ask preview"); w.set_default_size(560, 520); box = Gtk.VBox(spacing=6); w.add(box)
    img = draft["image"].convert("RGB"); th = img.copy(); th.thumbnail((540, 300))
    pb = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(th.tobytes()), GdkPixbuf.Colorspace.RGB, False, 8, th.width, th.height, th.width * 3)
    box.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
    tv = Gtk.TextView(); tv.set_wrap_mode(Gtk.WrapMode.WORD); tv.get_buffer().set_text(draft["text"] or ""); box.pack_start(tv, True, True, 0)
    st = Gtk.Label(label=draft["err"] or "Draft only: nothing is sent."); st.set_line_wrap(True); st.set_max_width_chars(70); box.pack_start(st, False, False, 0)
    def txt(): b = tv.get_buffer(); return b.get_text(b.get_start_iter(), b.get_end_iter(), True)
    from . import settings as _st
    combo = Gtk.ComboBoxText(); combo.append("", "Insert into: window focused at press"); open_cls = sorted({c for _, c, _ in open_windows()}); saved = _st.load()["askTargetWmClass"]
    for c in open_cls: combo.append(c, "Insert into: any %s window (must be exactly one)" % c)
    if saved and saved not in open_cls: combo.append(saved, "Insert into: %s (NOT OPEN: Insert will be refused)" % saved)  # keep the saved choice visible; never silently fall back to another app
    combo.set_active_id(saved if saved else ""); box.pack_start(combo, False, False, 0)
    combo.connect("changed", lambda *_: _st.save("askTargetWmClass", combo.get_active_id() or ""))  # connected AFTER construction: opening Ask cannot rewrite the saved target
    row = Gtk.HBox(spacing=6); box.pack_start(row, False, False, 0)
    def mk(label, fn):
        b = Gtk.Button(label=label); b.connect("clicked", lambda *_: fn()); row.pack_start(b, True, True, 0); return b
    def stat(m): st.set_text(m); on_status(m)
    mk("Copy text", lambda: stat(ctl.copy_text(txt())))
    mk("Copy image", lambda: stat(ctl.copy_image(draft["image"])))
    def ins():
        w.hide()
        try: m = ctl.insert(txt(), draft["win"], combo.get_active_id() or "")
        except Exception as e: m = "refused: insert failed (%s)" % type(e).__name__
        stat(m); w.show()
    mk("Insert draft", ins); mk("Cancel", lambda: w.destroy())
    w.show_all(); return w

def main():
    import argparse, gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk, GLib
    from Xlib import display as xd; from . import highlight as h
    ap = argparse.ArgumentParser(); ap.add_argument("--model", default=os.environ.get("TIPTOUR_VOSK_MODEL", "")); a = ap.parse_args()
    ctl = Controller(lambda d, c: GLib.idle_add(lambda: gtk_preview(d, c) and False), a.model)
    root = xd.Display().screen().root; down = [False]
    def poll():
        try: held = is_ask_chord(root.query_pointer().mask)
        except Exception: held = False
        if held and not down[0]: down[0] = True; print("ask:", ctl.press(), flush=True)
        elif not held and down[0]: down[0] = False; print("ask:", ctl.release(), flush=True)
        return True
    try:  # best-effort tray icon (Gtk.StatusIcon needs a tray host; NOT verified on a real desktop)
        ic = Gtk.StatusIcon.new_from_icon_name("audio-input-microphone"); ic.set_tooltip_text("TipTour Ask: hold Ctrl+Alt+Shift"); m = Gtk.Menu()
        for lab, fn in (("Settings...", lambda *_: __import__("tiptour_linux.settings", fromlist=["x"]).gtk_window()), ("Quit", lambda *_: Gtk.main_quit())):
            mi = Gtk.MenuItem(label=lab); mi.connect("activate", fn); m.append(mi)
        m.show_all(); ic.connect("popup-menu", lambda i, b, t: m.popup(None, None, Gtk.StatusIcon.position_menu, i, b, t)); main._tray = ic
    except Exception as e: print("tray unavailable:", type(e).__name__, flush=True)
    GLib.timeout_add(33, poll); print("ask harness ready: hold Ctrl+Alt+Shift and speak", flush=True); Gtk.main()

if __name__ == "__main__": main()
