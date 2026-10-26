"""Ground truth from Chrome itself via CDP (independent of the app): element rect -> screen coords; compare overlay tip."""
import asyncio, json, os, sys, urllib.request, websockets
SEL = json.loads(os.environ["TRUTH_SEL"]) if os.environ.get("TRUTH_SEL") else {"search": "#searchInput, input[name=search]", "login": "#pt-login-2 a, a[href*='UserLogin']", "diagram": "img[src*=Colored_neural_network]", "history": "a[href='#History']", "donate": "a[href*='donate.wikimedia.org']"}
async def truth(keys):
    tabs = [t for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if t["type"] == "page"]
    async with websockets.connect(tabs[0]["webSocketDebuggerUrl"], max_size=None) as ws:
        out = {}
        for i, k in enumerate(keys):
            js = "(()=>{const e=document.querySelector(%s);if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,sx:window.screenX,sy:window.screenY,top:window.outerHeight-window.innerHeight,left:window.outerWidth-window.innerWidth,dpr:window.devicePixelRatio,vw:innerWidth,vh:innerHeight}})()" % json.dumps(SEL[k])
            await ws.send(json.dumps({"id": i, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}))
            r = json.loads(await ws.recv())["result"]["result"].get("value")
            if r and r['w'] > 0 and r['h'] > 0: out[k] = [r["sx"] + r["left"] / 2 + r["x"], r["sy"] + r["top"] + r["y"], r["w"], r["h"]]
        return out
async def real_pointer(points, sels):
    """Independent mapping check: move the REAL X pointer to each tip and ask the page which element received the mouse event."""
    import subprocess
    tabs = [t for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if t["type"] == "page"]
    out = []
    async with websockets.connect(tabs[0]["webSocketDebuggerUrl"], max_size=None) as ws:
        async def ev(js):
            await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == 1: return m["result"]["result"].get("value")
        await ev("window.__t=null;addEventListener('mousemove',e=>{window.__t=e.target},true);0")
        for (x, y), sel in zip(points, sels):
            await ev("window.__t=null;0")
            for dx in (-3, 0, 3):
                subprocess.run(["xdotool", "mousemove", str(int(x) + dx), str(int(y))]); await asyncio.sleep(0.15)
            out.append(await ev("(()=>{const t=window.__t;if(!t)return 'no-event';const m=t.closest(%s);return m?'MATCH':t.tagName+':'+(t.className||'').toString().slice(0,30)})()" % (json.dumps(sel),)))
    return out

if __name__ == "__main__":
    res = json.load(open(sys.argv[1] + "/results.json")); keys = sys.argv[2:]
    keys = [k.rstrip("!") for k in sys.argv[2:]]; expect_refuse = [k.endswith("!") for k in sys.argv[2:]]
    tr = asyncio.run(truth(keys)); json.dump(tr, open(sys.argv[1] + "/cdp-truth.json", "w")); ok = True
    idx = [i for i, r in enumerate(res) if r["tool"]["source"] != "REFUSED" and keys[i] in tr]
    got = asyncio.run(real_pointer([tuple(res[i]["tool"]["px"]) for i in idx], [SEL[keys[i]] for i in idx])) if idx else []
    rp = ["-"] * len(res)
    for i, g in zip(idx, got): rp[i] = g
    for r, k, er, real in zip(res, keys, expect_refuse, rp):
        if r["tool"]["source"] == "REFUSED":
            print("%-8s REFUSED (%s) expected_refusal=%s" % (k, r["tool"].get("refused"), er)); ok &= er; continue
        if er: print(k, "expected refusal but pointed", r["tool"]["px"]); ok = False; continue
        if k not in tr: print(k, "NO ELEMENT"); ok = False; continue
        x, y = r["tool"]["px"]; rx, ry, w, h = tr[k]; inside = rx <= x <= rx + w and ry <= y <= ry + h
        print("%-8s src=%s model_px=%s tip=(%d,%d) cdp_rect=%s inside=%s real_pointer=%s" % (k, r["tool"]["source"], r["tool"]["model_px"], x, y, [round(v) for v in tr[k]], inside, real)); ok &= inside
    print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
