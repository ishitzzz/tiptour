#!/usr/bin/env python3
"""Fresh-browser page check via CDP, run before a click stage. The stage must stop (exit 4) unless:
 - there is a page tab whose URL starts with URL_PREFIX and whose title contains TITLE_MARKER,
 - that tab is fully loaded and contains every required element id (the owned fixture's real controls) with a non-empty rendered box,
 - the tab is the ONLY page tab and is visible (active); NO page tab is a chrome-error / about:blank-only error page (a stray error tab or wrong tab fails the preflight).
usage: page_preflight.py OUTDIR URL_PREFIX TITLE_MARKER [wait_s] [id,id,...]   -> writes OUTDIR/page_preflight.json (URL/title/ids only)"""
import sys, json, time, asyncio, urllib.request
import websockets
out, url_prefix, marker = sys.argv[1:4]
wait = float(sys.argv[4]) if len(sys.argv) > 4 else 25
ids = [x for x in (sys.argv[5].split(",") if len(sys.argv) > 5 else []) if x]
PORT = int(__import__("os").environ.get("TT_CDP_PORT", "9222"))
JS = "JSON.stringify({rs: document.readyState, vis: document.visibilityState, ids: %s.map(i => { const e = document.getElementById(i); if (!e) return [i, false]; const r = e.getBoundingClientRect(); return [i, r.width > 0 && r.height > 0]; })})" % json.dumps(ids)
async def probe(ws_url):
    async with websockets.connect(ws_url, open_timeout=5) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": JS, "returnByValue": True}}))
        r = json.loads(await asyncio.wait_for(ws.recv(), 5))
        return json.loads(r["result"]["result"]["value"])
res = {"ok": False}; end = time.time() + wait
while time.time() < end:
    try:
        tabs = [t for t in json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=3)) if t.get("type") == "page"]
        seen = [{"url": t.get("url"), "title": t.get("title")} for t in tabs]
        res = {"ok": False, "seen": seen}
        if any((t.get("url") or "").startswith("chrome-error:") for t in tabs): res["why"] = "error page tab present"; time.sleep(0.5); continue
        good = [t for t in tabs if (t.get("url") or "").startswith(url_prefix) and marker in (t.get("title") or "")]
        if not good: res["why"] = "no tab with expected url+title"; time.sleep(0.5); continue
        if len(tabs) != 1: res["why"] = "expected exactly one page tab, saw %d" % len(tabs); time.sleep(0.5); continue
        pr = asyncio.run(probe(good[0]["webSocketDebuggerUrl"])); res["probe"] = pr
        if pr["vis"] != "visible": res["why"] = "tab is not the active/visible one"; time.sleep(0.5); continue
        if pr["rs"] != "complete": res["why"] = "not loaded"; time.sleep(0.5); continue
        if not all(v for _, v in pr["ids"]): res["why"] = "required control missing or zero-size"; time.sleep(0.5); continue
        res["ok"] = True; break
    except Exception as e: res = {"ok": False, "why": "cdp error " + type(e).__name__}; time.sleep(0.5)
res.update({"expected_url_prefix": url_prefix, "expected_title_marker": marker, "required_ids": ids})
json.dump(res, open(out + "/page_preflight.json", "w"), indent=1)
print("page preflight", "OK" if res["ok"] else "FAILED: %s" % res.get("why")); sys.exit(0 if res["ok"] else 4)
