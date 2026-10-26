#!/usr/bin/env python3
"""Extract the Mac Gemini tool declarations (GeminiLiveClient.swift submitWorkflowPlanTool / createNoteTool) from the Swift dictionary literals into JSON, verbatim strings. usage: extract_mac_tool_schema.py SWIFT_FILE OUT_JSON"""
import re, sys, json
src = open(sys.argv[1], encoding="utf-8").read()
def lit(name):
    i = src.index("let %s: [String: Any] = [" % name) + len("let %s: [String: Any] = " % name)
    return src[i:]
class P:
    def __init__(s, t): s.t = t; s.i = 0
    def ws(s):
        while True:
            while s.i < len(s.t) and s.t[s.i] in " \t\r\n": s.i += 1
            if s.t.startswith("//", s.i):
                while s.i < len(s.t) and s.t[s.i] != "\n": s.i += 1
            else: break
    def val(s):
        s.ws(); c = s.t[s.i]
        if c == '"': return s.string()
        if c == "[": return s.coll()
        m = re.match(r"-?\d+", s.t[s.i:])
        if m: s.i += m.end(); return int(m.group())
        raise ValueError("unexpected %r at %d" % (s.t[s.i:s.i+30], s.i))
    def string(s):
        s.i += 1; out = []
        while s.t[s.i] != '"':
            if s.t[s.i] == "\\": 
                n = s.t[s.i+1]; out.append({"n": "\n", '"': '"', "\\": "\\", "'": "'"}.get(n, n)); s.i += 2
            else: out.append(s.t[s.i]); s.i += 1
        s.i += 1; return "".join(out)
    def coll(s):
        s.i += 1; s.ws()
        if s.t[s.i] == ":" : s.i += 2; return {}
        if s.t[s.i] == "]": s.i += 1; return []
        first = s.val(); s.ws()
        if s.t[s.i] == ":":  # dictionary
            d = {first: None}; s.i += 1; d[first] = s.val(); s.ws()
            while s.t[s.i] == ",":
                s.i += 1; s.ws()
                if s.t[s.i] == "]": break
                k = s.val(); s.ws(); assert s.t[s.i] == ":"; s.i += 1; d[k] = s.val(); s.ws()
            assert s.t[s.i] == "]", s.t[s.i:s.i+20]; s.i += 1; return d
        a = [first]
        while s.t[s.i] == ",":
            s.i += 1; s.ws()
            if s.t[s.i] == "]": break
            a.append(s.val()); s.ws()
        assert s.t[s.i] == "]"; s.i += 1; return a
out = {n: P(lit(n)).val() for n in ("submitWorkflowPlanTool", "createNoteTool")}
json.dump(out, open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
