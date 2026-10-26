#!/usr/bin/env python3
"""CONTRACT (written BEFORE reading any ownership raw; derived from the Mac per-plan capture semantics + Linux guards):
 K1 P2 was really shown (mutate.shown exists).
 K2 the old retry resolved on ITS OWN generation: a gate:own_generation_resolve event with own_pin<applied_pin and own_perc<applied_perc.
 K3 P1->P2 is a REAL screen change, so the ORIGINAL guards must refuse the old retry: a refusal decided by the screen-stale guard ('screen content changed' / 'stale-frame check' >threshold) or the identity check - NOT by generation. No render after release (renders stay 1).
 K4 no refusal text mentioning 'newer capture/perception' (generation refusal removed).
 Any failed K is reported as FAIL; nothing is relaxed."""
import sys, os, json, re
O = sys.argv[1]; log = open(O + "/stdout.txt", errors="ignore").read()
ev = json.load(open(O + "/click_events.json"))["events"]
r = lambda n: int((open(O + "/" + n).read() or "0"))
ge = [e for e in ev if e.get("gate") == "own_generation_resolve"]
ok = {}
ok["K1"] = os.path.exists(O + "/mutate.shown")
ok["K2"] = bool(ge) and all(e["own_pin"] < e["applied_pin"] and e["own_perc"] < e["applied_perc"] for e in ge)
dec = [l for l in log.split("\n") if re.search(r"screen content changed|focused window, title or geometry changed", l)]
ok["K3"] = bool(dec) and r("r_after_skip.txt") == 1
ok["K4"] = not re.search(r"newer capture replaced|newer perception replaced|resolve overtaken", log)
for k, v in ok.items(): print("ASSERT", k, v)
print("events:", ge); print("decision lines:", [l[:200] for l in dec[-3:]]); print("renders after release:", r("r_after_skip.txt"))
sys.exit(0 if all(ok.values()) else 1)
