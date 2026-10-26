"""ptt chord unit test + (if PulseAudio with null sinks tt_in/tt_out and /tmp/speech/q_point.wav exist) a virtual-audio loopback of Mic and Player. No physical mic."""
import os, sys, time, subprocess, wave
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tiptour_linux.voice import Mic, Player, ptt_chord
from tiptour_linux import highlight as h
assert ptt_chord(h.CTRL | h.ALT) and not ptt_chord(h.CTRL) and not ptt_chord(h.ALT) and not ptt_chord(h.CTRL | h.ALT | h.SHIFT) and not ptt_chord(h.CTRL | h.ALT | h.SUPER)
print("ptt chord unit ok")
wav = "/tmp/speech/q_point.wav"
if subprocess.run("pactl list short sinks | grep -q tt_in && pactl list short sinks | grep -q tt_out", shell=True).returncode == 0 and os.path.exists(wav):
    got = []; m = Mic(lambda b: got.append(len(b)), device="tt_in.monitor"); m.start(); time.sleep(0.5)
    subprocess.run(["paplay", "-d", "tt_in", wav]); time.sleep(0.5); m.stop()
    assert sum(got) > 100000, sum(got); print("virtual mic ok", sum(got), "bytes")
    rec = subprocess.Popen(["parec", "-d", "tt_out.monitor", "--file-format=wav", "/tmp/speech/out_test.wav"]); time.sleep(0.5)
    w = wave.open(wav); pcm = w.readframes(w.getnframes()); p = Player(sink="tt_out")
    for i in range(0, len(pcm), 9600): p.write(pcm[i:i + 9600])
    p.close(); time.sleep(0.5); rec.terminate(); rec.wait()
    assert os.path.getsize("/tmp/speech/out_test.wav") > 100000; print("virtual playback ok")
else: print("virtual audio devices not present: loopback part skipped")
