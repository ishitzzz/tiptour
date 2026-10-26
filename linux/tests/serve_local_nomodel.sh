cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_DEBUG_ATSPI_TIMING=1 ${AB_ENV} TIPTOUR_KEYS_GLOB='/home/sandbox/.vault/gemini-*/password'
dbus-run-session -- bash -c '
O=${AB_OUT:-/tmp/sv5}; mkdir -p $O; rm -f $O/fifo $O/ext-*
. tests/browser_env.sh http://localhost:8765/index.html $O
RECT=$(python3 - <<PY
import json,urllib.request,asyncio,websockets
async def main():
    t=[x for x in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if x["type"]=="page"][0]
    async with websockets.connect(t["webSocketDebuggerUrl"]) as ws:
        js="(()=>{const h=document.querySelector(\"h2\");const r=document.createRange();r.selectNodeContents(h);const s=getSelection();s.removeAllRanges();s.addRange(r);const b=h.getBoundingClientRect();return [Math.round(screenX+(outerWidth-innerWidth)/2+b.x),Math.round(screenY+outerHeight-innerHeight+b.y),Math.round(b.width),Math.round(b.height)]})()"
        await ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":js,"returnByValue":True}}))
        print(*json.loads(await ws.recv())["result"]["result"]["value"])
asyncio.run(main())
PY
)
echo "heading rect $RECT" > $O/rect.txt; for p in $(pgrep -f "remote-debugging-port=9222" | head -3); do tr "\0" "\n" < /proc/$p/environ | grep -E "^(ACCESSIBILITY_ENABLED|GTK_A11Y)=" ; done | sort -u >> $O/rect.txt
read X Y W H <<< "$RECT"; W=330
( sleep ${AB_DELAY:-30}; xdotool mousemove $((X-6)) $((Y-6)); xdotool keydown ctrl keydown shift
  for p in "$((X+W/2)) $((Y-6))" "$((X+W+6)) $((Y-6))" "$((X+W+6)) $((Y+H+6))" "$((X+W/2)) $((Y+H+6))" "$((X-6)) $((Y+H+6))" "$((X-6)) $((Y-3))"; do xdotool mousemove $p; sleep 0.2; done
  xdotool keyup shift keyup ctrl
  sleep 22; echo "What text is selected inside the area I highlighted? Quote it exactly, do not point yet." > $O/fifo
  sleep 14; echo "@quit" > $O/fifo ) &
SUB=$!
python3 -m tiptour_linux.app --highlight --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1
wait $SUB 2>/dev/null; kill $FP $CP $XP' >/dev/null 2>&1
