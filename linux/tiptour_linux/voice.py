"""Voice adapter for Linux (PulseAudio/PipeWire-pulse tools): mic capture, reply playback, and the Mac push-to-talk chord.
Source: Utilities/PushToTalkShortcut.swift (Control+Option held, no Command/Shift => pressed/released edges; the Mac app TOGGLES a live voice
session on the press edge), Voice/GeminiLiveSession.swift (mic -> PCM16 16 kHz mono ~100 ms chunks -> realtimeInput audio; server-side VAD),
Voice/GeminiLiveAudioPlayer.swift (reply audio PCM16 24 kHz mono, flushed on interruption).
Differences: parec/paplay subprocesses instead of AVAudioEngine; X11 modifier polling instead of a CGEvent tap. Needs pactl/parec/paplay."""
import os, subprocess, threading, time
from . import highlight as _h

IN_RATE, OUT_RATE, CHUNK = 16000, 24000, 3200  # 3200 bytes = 100 ms of s16le mono at 16 kHz

def ptt_chord(mask):
    """Control+Option held, no Shift, no Super (Mac: control+option, not command, not shift)."""
    return bool(mask & _h.CTRL) and bool(mask & _h.ALT) and not (mask & _h.SHIFT) and not (mask & _h.SUPER)

class Mic:
    def __init__(self, on_chunk, device=None):
        self.on_chunk, self.device, self.p, self.t = on_chunk, device or os.environ.get("TIPTOUR_MIC_SOURCE"), None, None
        self.active = False
    def start(self):
        if self.active: return
        cmd = ["parec", "--format=s16le", "--rate=%d" % IN_RATE, "--channels=1", "--latency-msec=100"] + (["-d", self.device] if self.device else [])
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL); self.active = True
        p = self.p
        def run():
            while self.active and self.p is p:
                b = p.stdout.read(CHUNK)
                if not b: break
                if self.active and self.p is p: self.on_chunk(b)
        self.t = threading.Thread(target=run, daemon=True); self.t.start()
    def stop(self):
        self.active = False
        p, self.p = self.p, None
        if p:
            try: p.terminate(); p.wait(2)
            except Exception:
                try: p.kill()
                except Exception: pass

class Player:
    """Streams reply PCM to paplay; flush() drops queued audio (interruption)."""
    def __init__(self, sink=None): self.sink, self.p, self.lock = sink or os.environ.get("TIPTOUR_AUDIO_SINK"), None, threading.Lock()
    def _open(self):
        cmd = ["paplay", "--raw", "--format=s16le", "--rate=%d" % OUT_RATE, "--channels=1"] + (["-d", self.sink] if self.sink else [])
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    def write(self, pcm):
        with self.lock:
            try:
                if self.p is None or self.p.poll() is not None: self._open()
                self.p.stdin.write(pcm); self.p.stdin.flush()
            except Exception: self.p = None
    def flush(self):
        with self.lock:
            p, self.p = self.p, None
            if p:
                try: p.kill()
                except Exception: pass
    def close(self):
        with self.lock:
            p, self.p = self.p, None
            if p:
                try: p.stdin.close(); p.wait(5)
                except Exception:
                    try: p.kill()
                    except Exception: pass

class PttMonitor:
    """Polls the X11 modifier mask at 30 Hz; calls on_press once per Control+Option press edge (the app toggles the voice session)."""
    def __init__(self, on_press, hz=30):
        from Xlib import display as xdisplay
        self.d = xdisplay.Display(); self.root = self.d.screen().root; self.on_press, self.dt, self.stop_flag, self.down = on_press, 1.0 / hz, False, False
    def start(self): threading.Thread(target=self._run, daemon=True).start()
    def stop(self): self.stop_flag = True
    def _run(self):
        while not self.stop_flag:
            try: held = ptt_chord(self.root.query_pointer().mask)
            except Exception: held = False
            if held and not self.down: self.down = True; self.on_press()
            elif not held: self.down = False
            time.sleep(self.dt)


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
