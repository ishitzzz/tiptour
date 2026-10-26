#!/usr/bin/env python3
"""Offline. The Linux system prompt must equal the Mac prompt except for the explicit OS deltas; re-extracts from the Swift source when present."""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tiptour_linux import live
bad = 0
def check(n, c):
    global bad; print(("PASS " if c else "FAIL ") + n); bad += (not c)
here = os.path.join(os.path.dirname(__file__), "..")
vf = open(os.path.join(here, "tiptour_linux/prompts/mac_system_prompt.verbatim.txt")).read()
exp = vf
for o, n in live.PROMPT_OS_DELTAS: exp = exp.replace(o, n, 1)
check("Linux SYSTEM_PROMPT == verbatim Mac prompt + explicit OS deltas only", live.SYSTEM_PROMPT == exp)
check("exactly 2 documented OS deltas", len(live.PROMPT_OS_DELTAS) == 2)
sw = os.path.join(here, "../TipTour/App/CompanionManager.swift")
if os.path.exists(sw):
    m = re.search(r'companionVoiceResponseSystemPrompt = """\n(.*?)\n\s*"""', open(sw).read(), re.S)
    check("verbatim file == Swift source re-extracted", "\n".join(l.strip() for l in m.group(1).split("\n")) + "\n" == vf)
else: print("INFO Swift source not present: source re-extraction not checked")
import json, subprocess, tempfile
vj = json.load(open(os.path.join(here, "tiptour_linux/prompts/mac_tool_schema.verbatim.json")))
check("Linux TOOL == Mac submitWorkflowPlanTool verbatim", live.TOOL == vj["submitWorkflowPlanTool"])
check("Linux step fields == Mac step fields (10)", list(live.TOOL["parameters"]["properties"]["steps"]["items"]["properties"]) == ["label","type","hint","value","direction","amount","by","targetContext","point_2d","box_2d"])
sf = os.path.join(here, "../TipTour/Voice/GeminiLiveClient.swift")
if os.path.exists(sf):
    o = tempfile.mktemp(suffix=".json"); subprocess.check_call([sys.executable, os.path.join(here, "tools/extract_mac_tool_schema.py"), sf, o])
    check("tool schema file == Swift source re-extracted", json.load(open(o)) == vj)
print("FAILS:", bad); sys.exit(1 if bad else 0)
