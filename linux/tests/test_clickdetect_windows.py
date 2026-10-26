"""Real X11 (Xvfb, no WM, xdotool synthetic clicks): overlap and focus change must not count as a target click."""
import os, sys, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from Xlib import display, X
from tiptour_linux.clickdetect import ClickDetector
d = display.Display(); root = d.screen().root
def mk(x, y, w, h, cls):
    win = root.create_window(x, y, w, h, 0, d.screen().root_depth, X.InputOutput, X.CopyFromParent, background_pixel=d.screen().white_pixel, event_mask=X.ExposureMask)
    win.set_wm_class(cls, cls); win.map(); d.sync(); return win
fails = []
def check(n, c):
    print(("PASS " if c else "FAIL ") + n)
    if not c: fails.append(n)
def xd(*a): subprocess.run(["xdotool", *a], check=True)
A = mk(100, 100, 400, 300, "ownedA"); C = mk(700, 100, 200, 200, "ownedC"); time.sleep(0.2)
A.set_input_focus(X.RevertToParent, X.CurrentTime); d.sync()
ev = []; r = ClickDetector(); r.arm((300, 250), (250, 230, 100, 40), lambda: ev.append(1)); time.sleep(0.2)
print("pinned", r._pin)
xd("mousemove", "300", "250"); xd("click", "1"); time.sleep(0.3)
check("same window, same focus: hit", len(ev) == 1)
# overlap: B on top of the target
ev.clear(); r.arm((300, 250), (250, 230, 100, 40), lambda: ev.append(1)); time.sleep(0.2)
B = mk(200, 200, 300, 150, "overlapB"); time.sleep(0.2)
xd("mousemove", "300", "250"); xd("click", "1"); time.sleep(0.3)
check("overlapping window on top: click NOT counted", len(ev) == 0)
print([p for p in r.presses][-1])
B.unmap(); d.sync(); time.sleep(0.2)
# focus change
ev.clear(); A.set_input_focus(X.RevertToParent, X.CurrentTime); d.sync(); r.arm((300, 250), (250, 230, 100, 40), lambda: ev.append(1)); time.sleep(0.2)
C.set_input_focus(X.RevertToParent, X.CurrentTime); d.sync(); time.sleep(0.1)
xd("mousemove", "300", "250"); xd("click", "1"); time.sleep(0.3)
check("focus moved to another window: click NOT counted", len(ev) == 0)
print([p for p in r.presses][-1])
# control: re-arm now (focus on C pinned), click target -> hit
ev.clear(); r.arm((300, 250), (250, 230, 100, 40), lambda: ev.append(1)); time.sleep(0.2)
xd("mousemove", "300", "250"); xd("click", "1"); time.sleep(0.3)
check("control: re-armed with current window state: hit", len(ev) == 1)
# focus on another window at arm, then focus moves TO target window (as a click-to-focus WM would): hit
ev.clear(); C.set_input_focus(X.RevertToParent, X.CurrentTime); d.sync(); r.arm((300, 250), (250, 230, 100, 40), lambda: ev.append(1)); time.sleep(0.2)
A.set_input_focus(X.RevertToParent, X.CurrentTime); d.sync(); time.sleep(0.1)
xd("mousemove", "300", "250"); xd("click", "1"); time.sleep(0.3)
check("focus moves TO the target window (click-to-focus): hit", len(ev) == 1)
r.stop(); print("FAILS", fails); sys.exit(1 if fails else 0)

# fail-closed: no window at the target point -> identity unresolved -> arm must refuse (explicit UNAVAILABLE), never arm blindly
_r2 = ClickDetector(); _ok = _r2.arm((1270, 790), (1260, 780, 10, 10), lambda: None)
print(("PASS" if _ok is False else "FAIL") + " unresolved window identity: arm refuses (fail closed)")
