#!/usr/bin/env python3
"""Oracle for the owned wizard page (CDP): page log, element rect in SCREEN pixels, element visible/enabled.
Usage: wizard_oracle.py log | rect ID | state ID | calib   (calib: store the page->screen offset using #s1 vs cdp_resolver 'Start order')"""
import json, sys, urllib.request, asyncio, os, websockets
OFF = os.environ.get("WIZ_OFF", "/tmp/wiz_off.json")
async def ev(expr):
    t = [x for x in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if x["type"] == "page"][0]
    async with websockets.connect(t["webSocketDebuggerUrl"]) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
        return json.loads(await ws.recv())["result"]["result"].get("value")
def run(e): return asyncio.run(ev(e))
cmd = sys.argv[1]
if cmd == "log": print(run("JSON.stringify(window.__log.map(x=>x[1]))"))
elif cmd == "state":
    print(json.dumps(run("(function(i){var e=document.getElementById(i);if(!e)return null;var r=e.getBoundingClientRect();return {w:r.width,h:r.height,disabled:!!e.disabled,text:e.textContent}})(%s)" % json.dumps(sys.argv[2]))))
elif cmd in ("calib", "rect"):
    if cmd == "calib":
        # screen offset of the page viewport: window.screenX + chrome height; derived from the resolver's rect for the same button
        sys.path.insert(0, os.getcwd())
        import subprocess
        from tiptour_linux import cdp_resolver
        g = subprocess.run(["xdotool", "getdisplaygeometry"], capture_output=True, text=True).stdout.split(); size = (int(g[0]), int(g[1]))
        st, h = cdp_resolver.resolve_ex("Start order", size); rr = h[0]["rect"]
        pr = run("(function(){var r=document.getElementById('s1').getBoundingClientRect();return [r.left,r.top]})()")
        json.dump({"dx": rr[0] - pr[0], "dy": rr[1] - pr[1]}, open(OFF, "w")); print(open(OFF).read())
    else:
        o = json.load(open(OFF))
        r = run("(function(i){var e=document.getElementById(i);if(!e)return null;var r=e.getBoundingClientRect();return [r.left,r.top,r.width,r.height]})(%s)" % json.dumps(sys.argv[2]))
        print(json.dumps(None if r is None else [r[0] + o["dx"], r[1] + o["dy"], r[2], r[3]]))
