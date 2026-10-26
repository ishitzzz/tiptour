#!/usr/bin/env python3
"""Post-hoc predicates over a sealed run_retry_fallback run dir (reads raw only). usage: assert_retry_fallback.py RUN_DIR"""
import sys, re, os
O = sys.argv[1]; log = open(os.path.join(O, "stdout.txt"), errors="replace").read(); ev = open(os.path.join(O, "script_events.txt")).read()
bad = []
def chk(n, c):
    print(("PASS " if c else "FAIL ") + n); (c or bad.append(n))
chk("A: fallback retry re-armed the same target (no replay callback)", "control retry: re-armed the same target" in log)
chk("B: the stopped process was the --targets --app verification child", re.search(r"stopped_child=\d+ cmd=.*atspi_resolver --targets --app", ev) is not None)
lines = [l for l in log.splitlines() if "control skip: pointer dismissed" in l or "control retry refused: superseded while verifying" in l]
chk("B: Skip applied BEFORE the late validity result, which was discarded as superseded", len(lines) == 2 and "control skip" in lines[0] and "superseded while verifying" in lines[1])
tail = log.split("control retry refused: superseded while verifying")[-1]
chk("B: no re-arm or render after the discarded retry", "re-armed the same target" not in tail and "render cursor at" not in tail)
print("RESULT", "all predicates hold (this run only)" if not bad else "FAILED: %s" % bad); sys.exit(1 if bad else 0)
