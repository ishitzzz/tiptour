"""Unit (fake clock, no X) + real-X11 (xdotool on Xvfb) tests for ClickDetector.
Real part runs only if DISPLAY works; label in output: unit vs x11-xdotool (synthetic input)."""
import os, subprocess, sys, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tiptour_linux.clickdetect import ClickDetector

fails = []
def check(n, c):
    print(("PASS " if c else "FAIL ") + n)
    if not c: fails.append(n)

t = [0.0]
d = ClickDetector(clock=lambda: t[0]); hits = []
check("disarmed ignores", d.handle_press(5, 5) == "ignored")
d.arm.__func__  # exists
d._point, d._cb = (100, 100), lambda: hits.append(1)
check("point inside tol hit", d.hit_test(130, 100))
check("point outside tol miss", not d.hit_test(150, 100))
check("miss keeps armed", d.handle_press(300, 300) == "miss" and d.armed())
check("hit fires once and disarms", d.handle_press(110, 100) == "hit" and hits == [1] and not d.armed())
d._rect, d._cb = (200, 200, 50, 20), lambda: hits.append(2)
check("rect inflate 6 hit", d.hit_test(194, 210) and not d.hit_test(192, 210))
t[0] = 0.05
check("grace swallows click", d.handle_press(210, 210) == "ignored" and hits == [1])
t[0] = 0.5
check("after grace hits", d.handle_press(210, 210) == "hit" and hits == [1, 2])

# real X11 synthetic input
if os.environ.get("DISPLAY") and subprocess.run(["which", "xdotool"], capture_output=True).returncode == 0:
    ev = []
    r = ClickDetector(); r.check_windows = False  # pure input-hook test; window identity is covered by test_clickdetect_windows
    ok = r.arm((400, 300), (380, 290, 40, 20), lambda: ev.append(time.time()))
    check("x11 start available", ok); time.sleep(0.2); print("INFO backend="+str(r.backend))
    def xd(*a): subprocess.run(["xdotool", *a], check=True)
    xd("mousemove", "100", "100"); xd("click", "1"); time.sleep(0.3)
    check("x11 click outside rect: no fire, still armed", not ev and r.armed())
    xd("mousemove", "400", "300"); time.sleep(0.1); check("x11 hover alone no fire", not ev)
    xd("mousedown", "1"); time.sleep(0.1); xd("mouseup", "1"); time.sleep(0.3)
    check("x11 click in rect fires once", len(ev) == 1 and not r.armed())
    xd("click", "3"); time.sleep(0.2)
    check("x11 right click never fires", len(ev) == 1)
    r.stop()

    # limitation probes (documented, not hidden): short click and multi-button
    ev2=[]; r2=ClickDetector(poll_hz=100); r2.check_windows = False
    r2.arm((400,300),(380,290,40,20),lambda: ev2.append(1))
    xd("mousemove","400","300"); time.sleep(0.1)
    n=0
    for _ in range(20):
        r2.arm((400,300),(380,290,40,20),lambda: ev2.append(1)); r2._last_hit=None
        xd("click","1"); time.sleep(0.05)
    print("INFO backend=%s short xdotool click (press+release back-to-back) detected %d/20" % (r2.backend,len(ev2)))
    check("short clicks all detected (>=19/20)", len(ev2)>=19)
    ev3=[]; r2.disarm(); r2._last_hit=None
    r2.arm((400,300),(380,290,40,20),lambda: ev3.append(1))
    xd("mousedown","3"); time.sleep(0.1); xd("mousedown","1"); time.sleep(0.2); xd("mouseup","1"); xd("mouseup","3"); time.sleep(0.1)
    print("INFO btn3 held then btn1 pressed: fires=%d (edge on Button1 only)" % len(ev3))
    check("x11 button1 edge while button3 held fires", len(ev3)==1)
    ev4=[]; r2._last_hit=None
    xd("mousedown","1"); time.sleep(0.1)
    r2.arm((400,300),(380,290,40,20),lambda: ev4.append(1)); time.sleep(0.2); xd("mouseup","1"); time.sleep(0.1)
    print("INFO button already held when armed: fires=%d (no edge, Mac tap also needs a new mouseDown)" % len(ev4))
    check("x11 held-before-arm does not fire", len(ev4)==0)
    r2.stop()
else:
    print("SKIP x11 (no DISPLAY/xdotool)")
print("FAILS:", fails); sys.exit(1 if fails else 0)
