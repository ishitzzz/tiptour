"""LOCAL/REAL-AUDIO-PATH (virtual sink): Player.flush drops queued audio on tt_out; plus stale-frame fraction on synthetic images. Not a model test."""
import sys, os, time, subprocess, wave, math, struct, threading; sys.path.insert(0, ".")
from tiptour_linux import voice, capture
from PIL import Image, ImageDraw
O = os.environ.get("OUT", "/tmp"); cap = O + "/interrupt-capture.wav"
rec = subprocess.Popen(["parec", "-d", "tt_out.monitor", "--file-format=wav", cap]); time.sleep(.6)
p = voice.Player("tt_out")
pcm = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 24000))) for i in range(24000 * 6))
def feed():
    for i in range(0, len(pcm), 9600): p.write(pcm[i:i + 9600])
threading.Thread(target=feed, daemon=True).start()
time.sleep(1.5); p.flush(); tf = time.time(); time.sleep(4.5); rec.terminate(); rec.wait()
w = wave.open(cap); rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes(); raw = w.readframes(n); w.close()
import array; a = array.array("h"); a.frombytes(raw[:len(raw) // 2 * 2]); step = rate * ch // 10  # 100 ms windows
env = [max(abs(x) for x in a[i:i + step]) if a[i:i + step] else 0 for i in range(0, len(a), step)]
loud = [i for i, e in enumerate(env) if e > 500]
print("loud 100ms windows: first %d last %d of %d (capture %.1fs); flush at ~1.5s after playback start" % (loud[0], loud[-1], len(env), n / rate))
print("INTERRUPT", "PASS" if loud and (loud[-1] - loud[0]) * 0.1 < 3.0 else "FAIL", "(audible span %.1fs of 6.0s queued)" % ((loud[-1] - loud[0] + 1) * 0.1))
b = Image.new("RGB", (800, 500), "white"); ImageDraw.Draw(b).rectangle((100, 100, 300, 160), fill="blue")
c1 = b.copy(); ImageDraw.Draw(c1).rectangle((600, 450, 604, 470), fill="black")  # caret-sized change
c2 = b.copy(); ImageDraw.Draw(c2).rectangle((0, 200, 800, 380), fill="red")      # content changed
f1, f2, f3 = capture.changed_fraction(b, b), capture.changed_fraction(b, c1), capture.changed_fraction(b, c2)
print("STALE same %.3f caret %.3f content %.3f" % (f1, f2, f3), "PASS" if f1 == 0 and f2 < 0.03 and f3 > 0.03 else "FAIL")

# target-level: a small control moves/changes inside the crop while the frame-wide change stays under 3%
g = Image.new("RGB", (1280, 800), "white"); ImageDraw.Draw(g).rectangle((600, 400, 680, 430), fill="blue")
g2 = Image.new("RGB", (1280, 800), "white"); ImageDraw.Draw(g2).rectangle((640, 400, 720, 430), fill="blue")  # button moved 40 px
ff, tf = capture.changed_fraction(g, g2), capture.target_changed_fraction(g, g2, (640, 415))
g3 = Image.new("RGB", (1280, 800), "white"); ImageDraw.Draw(g3).rectangle((600, 400, 680, 430), fill="blue"); ImageDraw.Draw(g3).rectangle((10, 10, 200, 60), fill="black")  # change far from target
print("TARGET moved-button frame %.3f target %.3f" % (ff, tf), "PASS" if ff < 0.03 and tf > 0.06 else "FAIL")
print("TARGET far-change target %.3f" % capture.target_changed_fraction(g, g3, (640, 415)), "PASS" if capture.target_changed_fraction(g, g3, (640, 415)) == 0 else "FAIL")
