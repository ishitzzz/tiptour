#!/bin/bash
# Ships the actual measurement behind the "poll 0/20 vs xi2 20/20" claim: 20 back-to-back xdotool clicks per backend on Xvfb (synthetic input).
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"; O=${RUN_DIR:?new dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
Xvfb :96 -screen 0 1280x800x24 -noreset >/dev/null 2>&1 & XP=$!; sleep 1.5
for B in poll xi2; do
DISPLAY=:96 TIPTOUR_CLICK_BACKEND=$([ $B = poll ] && echo poll || echo auto) PYTHONPATH=. python3 - <<'PY' | tee -a $O/measure.txt
import os, subprocess, time
from tiptour_linux.clickdetect import ClickDetector
n=[0]; d=ClickDetector()
subprocess.run(["xdotool","mousemove","400","300"])
for i in range(20):
    d._last_hit=None; d.check_windows=False
    d.arm((400,300),(380,290,40,20),lambda: n.__setitem__(0,n[0]+1)); 
    if i==0: time.sleep(0.3)
    subprocess.run(["xdotool","click","1"]); time.sleep(0.05)
time.sleep(0.3)
print("backend=%s detected %d/20 back-to-back xdotool clicks; errors=%s thread_starts=%d" % (d.backend, n[0], d.errors, d.thread_starts))
d.stop()
PY
done
kill $XP; true
