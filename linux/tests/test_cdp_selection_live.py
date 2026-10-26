"""LIVE local test (real Chrome on Xvfb, no model, no AT-SPI): cdp_resolver.selection identity/provenance rules. Run via run_cdp_selection_live.sh."""
import os, sys, json, time, subprocess, urllib.request, asyncio, websockets
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tiptour_linux import cdp_resolver as C

def cdp(ws_url, js):
    async def go():
        async with websockets.connect(ws_url, max_size=None) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}))
            return json.loads(await ws.recv())["result"]["result"].get("value")
    return asyncio.run(go())
def pages(): return [t for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if t["type"] == "page"]
def fgpid(): return int(subprocess.run("xdotool getwindowpid $(xdotool getwindowfocus)", shell=True, capture_output=True, text=True).stdout.strip())
res = []
def check(name, ok, detail): res.append(ok); print(("PASS " if ok else "FAIL ") + name, "-", detail, flush=True)

t = pages()[0]
box = cdp(t["webSocketDebuggerUrl"], "(()=>{const h=document.querySelector('h2');const r=document.createRange();r.selectNodeContents(h);const s=getSelection();s.removeAllRanges();s.addRange(r);const b=h.getBoundingClientRect();return [screenX+(outerWidth-innerWidth)/2+b.x,screenY+outerHeight-innerHeight+b.y,Math.min(b.width,300),b.height]})()")
subprocess.run(["xdotool", "mousemove", "10", "10", "click", "1"]) if False else None
time.sleep(0.5)
pid = fgpid(); x, y, w, h = box
region = (x - 12, y - 12, 330, h + 24)
sel, st = C.selection(region, pid); check("1 positive: bound focused tab, region intersects selection", bool(sel) and "Account preferences" in sel["text"] and sel["source"] == "cdp_dom", (st, (sel or {}).get("text")))
sel, st = C.selection((x + 400, y + 400, 60, 60), pid); check("2 region elsewhere -> no selection returned", sel is None and st.startswith("none"), st)
sel, st = C.selection(region, 1); check("3 wrong hint pid -> unavailable", sel is None and st.startswith("unavailable"), st)
sel, st = C.selection(region, 0); check("4 pid 0 -> unavailable", sel is None and st.startswith("unavailable"), st)
sel, st = C.selection(region, None); check("5 pid None -> unavailable", sel is None and st.startswith("unavailable"), st)
# second tab becomes the focused visible one; the first tab (with the selection) is hidden and must NOT be read
urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:9222/json/new?about:blank", method="PUT")); time.sleep(1.5)
sel, st = C.selection(region, fgpid()); check("6 other tab in front (selection tab hidden) -> nothing read", sel is None, st)
print("ALL PASS" if all(res) else "SOME FAILED"); sys.exit(0 if all(res) else 1)
