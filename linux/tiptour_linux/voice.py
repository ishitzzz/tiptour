"""Voice adapter for Linux (PulseAudio/PipeWire-pulse tools): mic capture, reply playback, and the Mac push-to-talk chord.
Source: Utilities/PushToTalkShortcut.swift (Control+Option held, no Command/Shift => pressed/released edges; the Mac app TOGGLES a live voice
session on the press edge), Voice/GeminiLiveSession.swift (mic -> PCM16 16 kHz mono ~100 ms chunks -> realtimeInput audio; server-side VAD),
Voice/GeminiLiveAudioPlayer.swift (reply audio PCM16 24 kHz mono, flushed on interruption).
Differences: parec/paplay subprocesses instead of AVAudioEngine; X11 modifier polling instead of a CGEvent tap. Needs pactl/parec/paplay."""
import os, subprocess, threading, time, queue
from . import highlight as _h

IN_RATE, OUT_RATE, CHUNK = 16000, 24000, 3200  # 3200 bytes = 100 ms of s16le mono at 16 kHz

def ptt_chord(mask):
    """Control+Option held, no Shift, no Super (Mac: control+option, not command, not shift)."""
    return bool(mask & _h.CTRL) and bool(mask & _h.ALT) and not (mask & _h.SHIFT) and not (mask & _h.SUPER)

def _reap(p, timeout=.5):
    """Kill before closing Python pipe wrappers, then reap. Never wait on pipe flush."""
    if p is None: return True
    try:
        if p.poll() is None: p.terminate()
        try: p.wait(timeout)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait(timeout)
    except (OSError, subprocess.TimeoutExpired): return False
    for stream in (p.stdin, p.stdout):
        if stream:
            try: stream.close()
            except OSError: pass
    return True


class _Reaper:
    """One owned worker per adapter; resources retire promptly, never on ingress."""
    def __init__(self):
        self.q = queue.Queue(); self.ok = True; self.thread = None
    def add(self, p, reader=None):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True, name='tiptour-audio-reaper'); self.thread.start()
        self.q.put((p, reader))
    def _run(self):
        while True:
            item = self.q.get()
            try:
                if item is None: return
                p,t = item; self.ok = _reap(p) and self.ok
                if t: t.join(.5); self.ok = not t.is_alive() and self.ok
            finally: self.q.task_done()
    def close(self):
        if self.thread:
            self.q.put(None); self.thread.join(2)
        return self.ok and (not self.thread or not self.thread.is_alive())


class Mic:
    def __init__(self, on_chunk, device=None, on_error=None):
        self.on_chunk, self.device = on_chunk, device or os.environ.get("TIPTOUR_MIC_SOURCE")
        self.on_error = on_error
        self.p = self.t = None; self.active = False; self.closed = False
        self.lock = threading.Lock(); self.reaper = _Reaper(); self.failed = False; self.generation = 0
    def start(self):
        with self.lock:
            if self.active or self.closed: return False
            cmd = ["parec", "--format=s16le", "--rate=%d" % IN_RATE, "--channels=1", "--latency-msec=100"] + (["-d", self.device] if self.device else [])
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            self.p = p; self.active = True; self.failed = False; self.generation += 1; generation = self.generation
            def run():
                try:
                    while self.active and self.p is p:
                        b = p.stdout.read(CHUNK)
                        if not b: break
                        if self.active and self.p is p: self.on_chunk(b)
                except (OSError, ValueError): self.failed = True
                finally:
                    # Natural EOF is OFF, not a silently live mic. Retire this child
                    # only when stop/replacement has not already taken ownership.
                    unexpected = False
                    with self.lock:
                        if self.p is p:
                            self.active = False; self.p = None; self.failed = True; unexpected = True
                            self.reaper.add(p)
                    if unexpected and self.on_error: self.on_error('microphone stream ended', generation)
            self.t = threading.Thread(target=run, daemon=True, name='tiptour-mic'); self.t.start()
            return True
    def stop(self):
        # Fast invalidation at ingress. Reaping runs on the owned worker, off the loop.
        with self.lock:
            self.active = False; self.generation += 1; p, self.p = self.p, None
            if p:
                self.reaper.add(p, self.t)
                try: p.terminate()
                except OSError: pass
    def close(self):
        with self.lock: self.closed = True
        self.stop()
        return self.reaper.close()



class Player:
    """Nonblocking PCM pipe: bounded user-space backlog, no loop-thread pipe flush.

    Saturation fails closed and reports False. No later write reopens after close.
    """
    def __init__(self, sink=None):
        self.sink = sink or os.environ.get("TIPTOUR_AUDIO_SINK")
        self.p = None; self.lock = threading.Lock(); self.closed = False
        self.pending = bytearray(); self.reaper = _Reaper(); self.failed = False
        self.event = threading.Event(); self.thread = None
    def _open(self):
        cmd = ["paplay", "--raw", "--format=s16le", "--rate=%d" % OUT_RATE, "--channels=1"] + (["-d", self.sink] if self.sink else [])
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        os.set_blocking(self.p.stdin.fileno(), False)
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True, name='tiptour-player'); self.thread.start()
    def _run(self):
        while True:
            self.event.wait(.02); self.event.clear()
            with self.lock:
                if self.closed: return
                p = self.p
                if not p or not self.pending: continue
                try:
                    n = os.write(p.stdin.fileno(), self.pending[:8192]); del self.pending[:n]
                except BlockingIOError: pass
                except (OSError, ValueError):
                    self.failed = True; self._detach()
    def _detach(self):
        p, self.p = self.p, None; self.pending.clear()
        if p:
            self.reaper.add(p)
            try: p.kill()
            except OSError: pass
    def write(self, pcm):
        with self.lock:
            if self.closed or self.failed: return False
            if len(self.pending) + len(pcm) > OUT_RATE * 2 * 30:
                self.failed = True; self._detach(); return False
            try:
                if self.p is None: self._open()
                self.pending.extend(pcm); self.event.set(); return True
            except OSError:
                self.failed = True; self._detach(); return False
    def flush(self):
        with self.lock: self._detach()
    def close(self):
        with self.lock:
            self.closed = True; self._detach()
        self.event.set()
        ok = self.reaper.close()
        if self.thread: self.thread.join(.5); ok = not self.thread.is_alive() and ok
        return ok


class PttMonitor:
    def __init__(self, on_press, hz=30):
        from Xlib import display as xdisplay
        self.d = xdisplay.Display(); self.root = self.d.screen().root
        self.on_press, self.dt, self.down = on_press, 1.0 / hz, False
        self.closed = threading.Event(); self.thread = None
    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name='tiptour-ptt'); self.thread.start()
    def stop(self): self.closed.set()
    def close(self):
        self.stop()
        if self.thread: self.thread.join(.5)
        return not self.thread or not self.thread.is_alive()
    def _run(self):
        try:
            while not self.closed.wait(self.dt):
                try: held = ptt_chord(self.root.query_pointer().mask)
                except Exception: held = False
                if self.closed.is_set(): break
                if held and not self.down: self.down = True; self.on_press()
                elif not held: self.down = False
        finally:
            self.d.close()


def echo_risk():
    """Returns a warning string if the default source can capture the default sink's output (reply audio would feed back into the mic), else None.
    This only inspects PulseAudio/PipeWire-pulse names; it cannot detect speakers acoustically leaking into a physical mic. Supported setups:
    headphones, or `pactl load-module module-echo-cancel` and TIPTOUR_MIC_SOURCE/TIPTOUR_AUDIO_SINK set to its source/sink."""
    def q(*a):
        try: return subprocess.run(["pactl", *a], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception: return ""
    src = os.environ.get("TIPTOUR_MIC_SOURCE") or q("get-default-source"); sink = os.environ.get("TIPTOUR_AUDIO_SINK") or q("get-default-sink")
    if not src or not sink: return "could not determine default audio source/sink; if you use speakers, echo of the reply may reach the mic (use headphones or module-echo-cancel)"
    if src == sink + ".monitor": return "mic source is the monitor of the reply sink: replies WILL feed back into the mic"
    return None
