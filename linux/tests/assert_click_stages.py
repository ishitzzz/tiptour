#!/usr/bin/env python3
"""Offline semantic assertions over a SEALED run dir (no model calls, no display). Exit 0 only if every expected label/verdict is present.
usage: assert_click_stages.py RUN_DIR   (parent dir holding click_validate/, click_unrelated/, click_pause/, click_guardlife/)"""
import sys, json, re, os
R = sys.argv[1]; bad = []
def log(s): return open(os.path.join(R, s, "stdout.txt"), errors="replace").read()
def chk(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: bad.append(name)
v = log("click_validate")
cur = re.findall(r"render cursor at \((\d+), (\d+)\) src (\S+)", v)
chk("validate: every point resolved from atspi (not model_box / error page)", bool(cur) and all(s.startswith("atspi") for _, _, s in cur[:3]))
chk("validate T1 changed", "validator: changed" in v)
chk("validate T2 unchanged_paused", "AT-SPI state unchanged" in v)
chk("validate T3b refused as stale", "refused to point: the screen content changed" in v)
chk("validate: no unavailable verdicts", "validator: unavailable" not in v)
u = log("click_unrelated")
chk("unrelated: unchanged_paused and not changed", "AT-SPI state unchanged" in u and "validator: changed" not in u)
p = log("click_pause")
chk("pause: retry then skip, second skip refused", "control retry: re-resolved the active step" in p and "control skip: pointer dismissed" in p and "control skip refused: no current target" in p)
ev = [e.get("pointer_guard") or e.get("control") for e in json.load(open(os.path.join(R, "click_guardlife", "click_events.json")))["events"]]
chk("guardlife: app-switch pause, retry, skip, repeated skip/retry refused", ev[:2] == ["focus_other", "paused_app_switch"] and "retry" in ev and "skip" in ev and ev[-2:] == ["skip_refused", "retry_refused"])
# ---- stricter, ordered/exact checks (events come from click_events.json, not unordered stdout)
def ce(stage): return json.load(open(os.path.join(R, stage, "click_events.json")))
cv = ce("click_validate")
chk("validate: exactly 3 renders, ALL from atspi", len(cur) == 3 and all(s.startswith("atspi") for _, _, s in cur))
chk("validate: exactly 2 press hits, in order T1 then T2", [x[2] for x in cv["presses"]] == ["hit", "hit"] and cv["presses"][0][:2] != cv["presses"][1][:2])
vv = [e.get("validator") for e in cv["events"]]
chk("validate: ordered verdicts changed -> unchanged_paused (first two)", vv[:2] == ["changed", "unchanged_paused"])
chk("validate: third (moved/stale) point differs from the first two", len({(c[0], c[1]) for c in cur}) == 3)
cp = ce("click_pause")
pv = [e.get("control") or e.get("validator") for e in cp["events"]]
chk("pause: ordered unchanged_paused,retry,unchanged_paused,retry,skip, then the QUEUED retry is refused as superseded (no retry_replay after skip), then skip_refused", pv[:7] == ["unchanged_paused", "retry", "unchanged_paused", "retry", "skip", "retry_refused", "skip_refused"] and "retry_replay" not in pv[4:])
chk("pause: presses hit,hit,ignored-disarmed (exact)", [x[2] for x in cp["presses"]] == ["hit", "hit", "ignored-disarmed"])
print("RESULT", "FAILED: %s" % bad if bad else "all semantic assertions hold (this is evidence about THIS sealed run only)")
sys.exit(1 if bad else 0)
