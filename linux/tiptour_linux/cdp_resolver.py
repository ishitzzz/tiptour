"""Browser DOM stage over CDP: Linux counterpart of the Mac browser-DOM resolver (ports 9222-9230).
Generic: no per-site selectors. Enumerates visible interactive/labelled elements in every visible page
target, converts to screen px using the window origin + browser chrome offset, matches by label tokens."""
import json, re, urllib.request, asyncio
import websockets
PORTS = range(9222, 9231)
STOP = {"the", "a", "an", "link", "box", "button", "icon", "image", "field", "tab", "of", "to", "at", "in", "on", "top", "right", "left", "bar", "toggle", "switch", "checkbox", "dropdown", "menu", "select", "text", "input", "control", "radio", "option", "click", "press"}
JS = r"""(()=>{
const sel='a,button,input,textarea,select,summary,img,svg,[role],[onclick],[tabindex],label,h1,h2,h3,figure,video,canvas';
const out=[];const vw=innerWidth,vh=innerHeight;
for(const e of document.querySelectorAll(sel)){
 const r=e.getBoundingClientRect(); if(r.width<4||r.height<4) continue; if(r.width*r.height>0.4*innerWidth*innerHeight) continue;
 const off=(r.right<0||r.bottom<0||r.left>vw||r.top>vh);
 if(e.tagName==='LABEL'&&e.control) continue;
 const cs=getComputedStyle(e); if(cs.visibility==='hidden'||cs.display==='none'||+cs.opacity===0) continue;
 const cx=Math.min(Math.max(r.left+r.width/2,0),vw-1), cy=Math.min(Math.max(r.top+r.height/2,0),vh-1);
 if(!off){const top=document.elementFromPoint(cx,cy); if(!top||!(e===top||e.contains(top)||top.contains(e))) continue;}
 const cl=x=>(x||'').replace(/\s+/g,' ').trim().slice(0,120);
 const names=[e.getAttribute('aria-label'),e.getAttribute('alt'),e.getAttribute('title'),e.getAttribute('placeholder'),e.tagName==='INPUT'?e.value:'',...(e.labels?[...e.labels].map(l=>l.innerText):[]),...((e.getAttribute('aria-labelledby')||'').split(' ').map(i=>{const q=document.getElementById(i);return q?q.innerText:''})),e.tagName==='SELECT'?'':(e.innerText||e.textContent)].map(cl).filter(Boolean);
 if(!names.length&&(e.tagName==='IMG'||e.tagName==='svg')){const f=e.closest('figure');if(f){const c=f.querySelector('figcaption');if(c)names.push(cl(c.innerText))}}
 if(!names.length) continue; const name=names[0];
 out.push({off,name,names,tag:e.tagName.toLowerCase(),x:r.left,y:r.top,w:r.width,h:r.height});
 if(out.length>600) break;}
return {els:out,sx:window.screenX,sy:window.screenY,left:Math.max(0,(outerWidth-innerWidth)/2),top:outerHeight-innerHeight,dpr:devicePixelRatio,vis:document.visibilityState,focus:document.hasFocus(),ow:outerWidth,oh:outerHeight}})()"""

def _targets():
    res = []
    for p in PORTS:
        try:
            for t in json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % p, timeout=0.4)):
                if t.get("type") == "page" and not t["url"].startswith("chrome"): res.append((t["webSocketDebuggerUrl"], t.get("title", "")))
        except Exception: pass
    return res

async def _snap(ws_url):
    async with websockets.connect(ws_url, max_size=None, open_timeout=2) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": JS, "returnByValue": True}}))
        return json.loads(await asyncio.wait_for(ws.recv(), 5))["result"]["result"].get("value")

def _run(coro):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as ex: return ex.submit(asyncio.run, coro).result()

GATE = {"reason": "", "browser_rects": []}

def _x_active_pid():
    import subprocess
    try:
        w = subprocess.run(["xdotool", "getwindowfocus"], capture_output=True, text=True, timeout=2).stdout.strip()
        return int(subprocess.run(["xdotool", "getwindowpid", w], capture_output=True, text=True, timeout=2).stdout.strip()) if w else None
    except Exception: return None

async def _browser_pids():
    pids = set()
    for p in PORTS:
        try:
            v = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/version" % p, timeout=0.4))
            async with websockets.connect(v["webSocketDebuggerUrl"], max_size=None, open_timeout=2) as ws:
                await ws.send(json.dumps({"id": 1, "method": "SystemInfo.getProcessInfo"}))
                for pi in json.loads(await asyncio.wait_for(ws.recv(), 5))["result"]["processInfo"]:
                    if pi["type"] == "browser": pids.add(pi["id"])
        except Exception: pass
    return pids

def all_targets():
    """Page/window binding: only the focused visible page is used. If no page has focus and exactly one visible
    page exists, use it. Several visible pages and none focused -> fail closed (no CDP candidates)."""
    GATE["reason"] = ""
    act = _x_active_pid(); bp = _run(_browser_pids())
    if act is None or act not in bp:
        GATE["reason"] = "foreground X11 window pid %s is not the CDP browser process %s" % (act, sorted(bp))
        GATE["browser_rects"] = []
        for u, _t in _targets():
            try: sn = _run(_snap(u))
            except Exception: continue
            if sn and sn["vis"] == "visible": GATE["browser_rects"].append([sn["sx"], sn["sy"], sn["ow"], sn["oh"]])
        return []
    import subprocess
    def xo(*a):
        try: return subprocess.run(["xdotool", *a], capture_output=True, text=True, timeout=2).stdout.strip()
        except Exception: return ""
    wid = xo("getwindowfocus"); xname = xo("getwindowname", wid) if wid else ""
    GATE["x_window"] = wid
    snaps = []
    for u, title in _targets():
        try: s = _run(_snap(u))
        except Exception: continue
        # window identity: the focused X11 window's title must be this page target's title (Chrome titles windows "<tab title> - <browser>")
        if s and s["vis"] == "visible" and title and xname.startswith(title): snaps.append(s)
    if len(snaps) != 1:
        GATE["reason"] = "focused X11 window %s %r matches %d page targets (need exactly 1)" % (wid, xname[:40], len(snaps)); return []
    chosen = snaps
    res = []
    for s in chosen:
        if abs(s["dpr"] - 1) > 1e-6: continue  # dpr!=1 not validated: fail closed to next stage
        for e in s["els"]:
            res.append({"off": e["off"], "label": e["name"], "names": e["names"], "role": e["tag"], "rect": [s["sx"] + s["left"] + e["x"], s["sy"] + s["top"] + e["y"], e["w"], e["h"]],
                        "origin": [s["sx"] + s["left"], s["sy"] + s["top"]]})
    return res

def _tok(s): return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP]

def resolve(label, screen_size=None):
    l = label.strip().lower(); lt = _tok(label); cands = []
    for t in all_targets():
        if t.get('off'): continue
        if screen_size and not (0 <= t["rect"][0] < screen_size[0] and 0 <= t["rect"][1] < screen_size[1]): continue
        sc = 0
        for n in (x.lower() for x in t["names"]):
            if n == l: sc = max(sc, 3)
            elif l and l in n and len(l) / len(n) >= 0.5: sc = max(sc, 2)
            elif len(n) >= 4 and l.startswith(n) and len(l) <= 6 * len(n): sc = max(sc, 1)  # model label = element name + descriptive tail
            elif lt:
                nt = _tok(n)
                if nt and all(x in nt for x in lt) and len(nt) <= 2 * len(lt) + 1: sc = max(sc, 1)
                if nt and lt and all(x in lt for x in nt) and len(nt) * 2 >= len(lt): sc = max(sc, 1)  # element name fully contained in the model's longer label
        if sc: t["score"] = sc; cands.append(t)
    if not cands: return []
    best = max(c["score"] for c in cands)
    cands = [c for c in cands if c["score"] == best]
    # collapse wrappers: drop a match that contains another match (keep the innermost), then merge near-identical centers
    def inside(a, b): return a["rect"][0] <= b["rect"][0] and a["rect"][1] <= b["rect"][1] and a["rect"][0] + a["rect"][2] >= b["rect"][0] + b["rect"][2] and a["rect"][1] + a["rect"][3] >= b["rect"][1] + b["rect"][3]
    cands = [c for c in cands if not any(o is not c and inside(c, o) for o in cands)]
    out = []
    for c in cands:
        cc = (c["rect"][0] + c["rect"][2] / 2, c["rect"][1] + c["rect"][3] / 2)
        if not any(abs(cc[0] - (o["rect"][0] + o["rect"][2] / 2)) < 30 and abs(cc[1] - (o["rect"][1] + o["rect"][3] / 2)) < 30 for o in out): out.append(c)
    return out

if __name__ == "__main__":
    import sys
    for t in resolve(" ".join(sys.argv[1:])): print(t)


def resolve_ex(label, screen_size=None):
    """-> (status, hits). status: ok | ambiguous | offscreen | none | gated"""
    hits = resolve(label, screen_size)
    if GATE["reason"]: return "gated", []
    if len(hits) == 1: return "ok", hits
    if len(hits) > 1: return "ambiguous", hits
    l = label.strip().lower(); lt = _tok(label)
    for t in all_targets():
        if not t.get("off"): continue
        for n in (x.lower() for x in t["names"]):
            if n == l or (l and l in n and len(l) / len(n) >= 0.5) or (lt and all(x in _tok(n) for x in lt) and len(_tok(n)) <= 2 * len(lt) + 1): return "offscreen", [t]
    return "none", []


def revalidate(label, hit_rect, screen_size=None, tol=4):
    """Render-time recheck: same X window still focused, still exactly one binding, element rect unchanged."""
    wid = GATE.get("x_window")
    st, hits = resolve_ex(label, screen_size)
    if st != "ok": return False, "re-resolve status %s (%s)" % (st, GATE["reason"])
    if GATE.get("x_window") != wid: return False, "focused window changed"
    r = hits[0]["rect"]
    if any(abs(a - b) > tol for a, b in zip(r, hit_rect)): return False, "element moved %s -> %s" % ([round(v) for v in hit_rect], [round(v) for v in r])
    return True, ""


SEL_JS = r"""(()=>{const s=getSelection();const m={sx:window.screenX,sy:window.screenY,left:Math.max(0,(outerWidth-innerWidth)/2),top:outerHeight-innerHeight,dpr:devicePixelRatio,vis:document.visibilityState,focus:document.hasFocus()};
if(!s||s.rangeCount===0||s.isCollapsed) return Object.assign(m,{text:null});
const rs=[...s.getRangeAt(0).getClientRects()].filter(r=>r.width>0&&r.height>0).map(r=>[r.x,r.y,r.width,r.height]);
return Object.assign(m,{text:s.toString().slice(0,600),rects:rs.slice(0,200)});})()"""

async def _sel_snap(ws_url):
    async with websockets.connect(ws_url, max_size=None, open_timeout=2) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": SEL_JS, "returnByValue": True}}))
        return json.loads(await asyncio.wait_for(ws.recv(), 5))["result"]["result"].get("value")

def _rects_hit(a, b):
    return a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1]

def selection(rect, hint_pid):
    """Browser DOM text selection intersecting the user's highlight, read over CDP. Returns (selection|None, status).
    Provenance/identity rules (fail closed -> status 'unavailable: ...', never a guess):
      - hint_pid (the window the highlight was painted over) must be > 0, be the CDP browser process, AND be the foreground X11 window pid;
      - exactly one visible page target whose title is the foreground window's title prefix, with document focus (no stale other tab/window);
      - devicePixelRatio 1 only; the selection's range rect (screen px = window origin + chrome offset + client rect) must intersect the highlight.
    The selection is returned (whole text, up to 600 chars) only when AT LEAST ONE of its range rects intersects the highlight; if none does, nothing is returned. Text outside the highlight can be included when it belongs to the same selection."""
    try: hp = int(hint_pid or 0)
    except (TypeError, ValueError): hp = 0
    if hp <= 0: return None, "unavailable: no window pid for the highlighted area"
    act = _x_active_pid(); bp = _run(_browser_pids())
    if not bp: return None, "unavailable: no CDP browser reachable"
    if hp not in bp or act != hp: return None, "unavailable: highlighted window pid %s is not the foreground CDP browser (foreground %s)" % (hp, act)
    import subprocess
    def xo(*a):
        try: return subprocess.run(["xdotool", *a], capture_output=True, text=True, timeout=2).stdout.strip()
        except Exception: return ""
    wid = xo("getwindowfocus"); xname = xo("getwindowname", wid) if wid else ""
    snaps = []
    for u, title in _targets():
        try: s = _run(_sel_snap(u))
        except Exception: continue
        if s and s["vis"] == "visible" and s["focus"] and title and xname.startswith(title): snaps.append(s)
    if len(snaps) != 1: return None, "unavailable: focused window matches %d focused visible page targets (need exactly 1)" % len(snaps)
    s = snaps[0]
    if abs(s["dpr"] - 1) > 1e-6: return None, "unavailable: devicePixelRatio != 1 not validated"
    if not s.get("text"): return None, "none: no DOM text selection in the focused tab"
    ox, oy = s["sx"] + s["left"], s["sy"] + s["top"]
    hits = [r for r in s.get("rects", []) if _rects_hit([ox + r[0], oy + r[1], r[2], r[3]], rect)]
    if not hits: return None, "none: the tab's selection does not intersect the highlight"
    return {"text": s["text"].strip(), "app": "browser tab", "role": "DOM selection", "source": "cdp_dom"}, "ok"
