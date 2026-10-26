cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
export ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
dbus-run-session -- bash -c '
. tests/browser_env.sh http://localhost:8765/index.html /tmp/atc
sleep 6
python3 - <<PY
import json,urllib.request,asyncio,websockets,time
async def main():
    t=[x for x in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if x["type"]=="page"][0]
    async with websockets.connect(t["webSocketDebuggerUrl"]) as ws:
        js="(()=>{const l=document.getElementById(\"em\");l.value=\"hello owned world\";l.focus();l.setSelectionRange(6,17);const b=l.getBoundingClientRect();return [b.x,b.y,b.width,b.height,screenX,screenY,outerHeight-innerHeight]})()"
        await ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":js,"returnByValue":True}}))
        print(json.loads(await ws.recv())["result"]["result"]["value"])
asyncio.run(main())
PY
python3 - <<PY
import time
from tiptour_linux import atspi_resolver as a, highlight as h
# region around the selected label (label ~ x80..260, y~250 screen) and a control-only region elsewhere
t=time.time()
for name,rect in (("selected-label",(60,235,260,40)),("email-field",(150,380,290,50)),("empty",(900,600,100,100))):
    el,sel=a.probe(rect); print(name,"ELEMENT",el,"SELECTION",sel, round(time.time()-t,1)); t=time.time()
ctx=h.build_context([(70,250),(200,252),(300,255)],None,h.atspi_probe); print(h.prompt(ctx,False) if hasattr(h,"prompt") else "")
PY
kill $FP $CP $XP' 2>&1 | grep -v -E "dbus|ERROR|Warning|keyring|xfconf|display|prompter"
