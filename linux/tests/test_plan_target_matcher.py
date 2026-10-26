#!/usr/bin/env python3
"""Offline: encodes WorkflowRunner.activationMatchesCurrentPlanTarget (Swift :1284) read from source, not run on a Mac."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tiptour_linux.workflow import PlanTargetMatcher as M
bad = 0
def check(n, c):
    global bad; print(("PASS " if c else "FAIL ") + n); bad += (not c)
m = M("Chrome", "click", "Save", "google-chrome.google-chrome")
check("same app id as seeded target -> tolerated", m.matches("google-chrome", "google-chrome.google-chrome"))
check("unrelated app -> pause (no match)", not m.matches("xterm", "xterm.xterm"))
m = M("Chrome", "click", "Save", None)
check("plan app name contained in class name -> match", m.matches("google-chrome", "google-chrome.google-chrome"))
check("match caches the target id; later same id matches even with other name", m.matches("renamed", "google-chrome.google-chrome"))
check("then an unrelated app still pauses", not m.matches("xterm", "xterm.xterm"))
m = M("chrome", "click", "Terminal", None)
check("click-step label is NOT a target name (only openApp)", not m.matches("xterm", "xterm.xterm"))
m = M(None, "openApp", "Firefox", None)
check("openApp step label counts as a target name", m.matches("firefox", "navigator.firefox"))
m = M("gimp", "click", "x", None)
check("substring of bundle-id equivalent matches", m.matches("some app", "gimp-2.10.gimp"))
check("empty plan app and no seed -> never matches", not M(None, "click", "x", None).matches("a", "a.a"))
print("FAILS:", bad); sys.exit(1 if bad else 0)
