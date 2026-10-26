#!/bin/bash
# REAL Gemini Live (free-tier tiptour-linux key only), owned 5-step wizard page with changing-page edge cases (late page, moving control, disabled decoy + disappearing promo). TEXT turns, point-only (--act OFF). After each render the harness performs a synthetic xdotool click on the OWNED page at the rendered cursor (the user's click stand-in). Per-stage timing comes from the app log.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
KEYFILE=${KEYFILE:?path of the single key file}
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_KEYS_GLOB=$KEYFILE TIPTOUR_DEBUG_LOG=1 TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O
dbus-run-session -- bash -c '
EXPECT_IDS=s1 EXPECT_TITLE="Wizard Test" . tests/browser_env.sh http://localhost:8765/wizard.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
lastpx() { grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/"; }
ev() { echo "$(date +%T.%N | cut -c1-12) $1" >> $O/script_events.txt; }
cdp_log() { python3 - >> $O/page_log.txt <<PY
import json,urllib.request,asyncio,websockets
async def main():
    t=[x for x in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if x["type"]=="page"][0]
    async with websockets.connect(t["webSocketDebuggerUrl"]) as ws:
        await ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":"JSON.stringify(window.__log)"}})); print(json.loads(await ws.recv())["result"]["result"].get("value"))
asyncio.run(main())
PY
}
turn() { n=$(nrender); ev "ASK $1"; echo "$1" > $O/fifo; for i in $(seq 70); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; P=$(lastpx); ev "RENDER $2 at $P (renders=$(nrender))"; }
click() { set -- $P; [ -n "$1" ] && { xdotool mousemove $1 $2; sleep 0.3; xdotool click 1; ev "CLICK $1 $2"; }; }
( sleep 18
  turn "Point to the Start order button." s1; click; sleep 1
  turn "Point to the Choose size button." s2; click; sleep 1
  turn "Point to the Add toppings button." s3; click; sleep 1
  turn "Point to the Review order button." s4; click; sleep 1
  turn "Point to the Place test order button." s5; click; sleep 3; cdp_log
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording" ; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== script events"; cat $O/script_events.txt; echo "== page log"; cat $O/page_log.txt
echo "== app log"; grep -a -E "render cursor|refus|toolCall|result|429|rror" $O/stdout.txt | cut -c1-240 | head -40
