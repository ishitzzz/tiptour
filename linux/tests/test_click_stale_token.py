"""Stale-token race (UNIT-level simulation, no X): a press delivered after the plan was replaced but before disarm must be ignored."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tiptour_linux.clickdetect import ClickDetector, guarded_callback
tok = {"n": 1}; ok = []; stale = []
d = ClickDetector(); d._point = (100, 100); d._rect = None
d._cb = guarded_callback(tok, 1, lambda: ok.append(1), lambda: stale.append(1))
tok["n"] = 2   # new plan replaced the old one; the old arm was NOT yet disarmed (the race window)
r = d.handle_press(100, 100)
print("press result", r, "valid", ok, "stale", stale)
assert r == "hit" and ok == [] and stale == [1], "stale arm must not advance"
d._point = (100, 100); d._last_hit = None; d._cb = guarded_callback(tok, 2, lambda: ok.append(2), lambda: stale.append(2))
d.handle_press(100, 100); assert ok == [2]
print("PASS stale-token unit race")
