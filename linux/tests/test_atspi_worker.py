# Local test of the AT-SPI worker queue (no Chrome, no model). Needs the Atspi typelib on GI_TYPELIB_PATH.
import sys, time, threading; sys.path.insert(0, "..")
from tiptour_linux import atspi_resolver as a
W = a._W; res = {}
def slow(n, d): time.sleep(d); return n
def go(name, fn, args, to, low=False):
    def t():
        try: res[name] = W.call(fn, args, to, low)
        except Exception as e: res[name] = type(e).__name__ + ":" + str(e)[:20]
    th = threading.Thread(target=t); th.start(); return th
# 1) rapid gestures while the worker is busy: A in flight (1.5s), B queued, C queued -> B superseded, C runs, results never cross
A = go("A", slow, ("A", 1.5), 5); time.sleep(0.2); B = go("B", slow, ("B", 0.1), 5); time.sleep(0.1); C = go("C", slow, ("C", 0.1), 5)
for t in (A, B, C): t.join()
assert res["A"] == "A" and res["B"].startswith("RuntimeError:superseded") and res["C"] == "C", res
# 2) expiry: a queued request whose deadline passes before start is dropped, never run late
ran = []
D = go("D", slow, ("D", 1.5), 5); time.sleep(0.2); E = go("E", lambda: ran.append(1), (), 0.5)
for t in (D, E): t.join()
time.sleep(1.5); assert res["E"].startswith("TimeoutError") and not ran, (res, ran)
# 3) low-priority warm-up yields to a pending real request and never supersedes it
F = go("F", slow, ("F", 1.0), 5); time.sleep(0.2); G = go("G", slow, ("G", 0.1), 5); time.sleep(0.1); H = go("H", slow, ("H", 0.1), 5, True)
for t in (F, G, H): t.join()
assert res["G"] == "G" and res["H"].startswith("RuntimeError:busy"), res
print("worker queue tests OK:", res)
