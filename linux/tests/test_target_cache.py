#!/usr/bin/env python3
"""Offline unit tests: expected values are derived by reading LocalPerceptionTargetCache.swift (scores/thresholds), NOT from running the Mac code."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tiptour_linux.target_cache import *
bad = 0
def check(n, c):
    global bad; print(("PASS " if c else "FAIL ") + n); bad += (not c)
S = label_match_score
check("exact=100", S("Save", "save") == 100)
check("normalized full equal ignoring case only -> exact path first", S("Save Changes", "save changes") == 100)
check("substring (>=5 chars both)=72", S("settings", "open settings page") == 72)
check("fuzzy single word distance1=68", S("settinks", "settings") == 68)
check("fuzzy distance2 with len>=8 =54", S("settingz1", "settings2") == 54)
check("fuzzy distance2 with len<8 rejected", S("savexy", "saveab") is None)
check("stop words ignored: 'the save button' vs 'save'", S("the save button", "save") == 58)
check("coverage 1.0 -> 58", S("save file", "file save now") == 58)
check("multiword partial coverage rejected", S("save file now", "save") is None)
check("no overlap -> None", S("trash", "gear") is None)
check("edit distance", edit_distance("kitten", "sitting") == 3)
t = [0.0]; c = LocalPerceptionTargetCache(clock=lambda: t[0])
els = [{"bbox": [100, 100, 200, 140], "label": "", "source": "yolo", "conf": 0.9},
       {"bbox": [105, 105, 150, 135], "label": "Save", "source": "ocr", "conf": 0.8},
       {"bbox": [300, 100, 380, 140], "label": "Cancel", "source": "ocr", "conf": 0.7},
       {"bbox": [10, 10, 12, 12], "label": "tiny", "source": "ocr", "conf": 1.0}]
c.update(els, (1000, 800), (0, 0, 1000, 800))
tg = c.current_targets()
check("tiny box (<=4px) dropped; yolo box enriched from OCR label 'Save'", len(tg) == 3 and any(x["source"] == "yolo" and x["label"] == "Save" for x in tg))
check("marks 1..n, ocr first (priority 4) then conf", [x["mark"] for x in tg] == [1, 2, 3] and tg[0]["source"] == "ocr" and tg[0]["confidence"] == 0.8)
check("id format source:label:x1:y1:x2:y2", tg[0]["id"] == "ocr:Save:105:105:150:135")
r = c.resolve("save")
check("resolve exact label prefers ocr (source bonus)", r and r["source"] == "ocr" and abs(r["global_point"][0] - 127.5) < 1e-6)
check("normalized box2d [y1,x1,y2,x2] 0..1000", r["normalized_box_2d"] == [131, 105, 169, 150])
t[0] = 61.0
check("TTL 60s: stale cache returns nothing", c.resolve("save") is None and c.current_targets() == [])
t[0] = 0.0
c.update([{"bbox": [100, 100, 140, 130], "label": "Open", "source": "ocr", "conf": 0.5}, {"bbox": [700, 600, 740, 630], "label": "Open", "source": "ocr", "conf": 0.5}], (1000, 800), (0, 0, 1000, 800))
near = c.resolve("open", prefer_near_global_point=(720, 615))
check("proximity tiebreak picks the nearer duplicate", near and near["global_point"][0] > 600)
c.update(els, (2000, 1600), (0, 0, 1000, 800))
check("image/display scaling maps pixels to global", abs(c.resolve("cancel")["global_point"][0] - 170.0) < 1e-6)
check("box2d rounds .5 away from zero (not banker's): 0.5->1, 2.5->3", LocalPerceptionTargetCache.box2d((0.5, 2.5, 0, 0), (1000, 1000))[:2] == [3, 1])
c.clear(); check("clear() empties the cache", c.resolve("save") is None and c.current_targets() == [])
c.update([], (10, 10), (0, 0, 10, 10)); check("empty snapshot resolves nothing", c.resolve("x") is None)
c.update([{"bbox": [10, 10, 60, 40], "label": "Go", "source": "ocr", "conf": 0.5}, {"bbox": [210, 10, 260, 40], "label": "Go", "source": "ocr", "conf": 0.5}], (1000, 800), (0, 0, 1000, 800))
check("equal-score tie keeps the FIRST candidate (Swift max(by: <) replaces only when strictly less; unverified, no Swift toolchain here)", c.resolve("go")["global_point"][0] < 100)
print("FAILS:", bad); sys.exit(1 if bad else 0)
