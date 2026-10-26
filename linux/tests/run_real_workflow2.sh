#!/bin/bash
# REAL Gemini Live, owned 5-step wizard (late page, moving control, disabled decoy, disappearing promo). Page-aware: a click is made ONLY after a plan whose step type is "click"; a wait/non-click plan is recorded and NOT clicked. The deliberate ask during loading is an edge case recorded separately; then a recovery ask after the page log shows the page loaded. Text turns; point-only (--act OFF); synthetic click on the owned page stands in for the user's click. ms-resolution app log (TIPTOUR_LOG_MS=1) for capture/perception/model/render timing.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
KEYFILE=${KEYFILE:?path of the single key file}
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_LOG_MS=1 TIPTOUR_KEYS_GLOB=$KEYFILE TIPTOUR_DEBUG_LOG=1 TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O
dbus-run-session -- bash -c '
EXPECT_IDS=s1 EXPECT_TITLE="Wizard Test" . tests/browser_env.sh http://localhost:8765/wizard.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
lastpx() { grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/"; }
lasttype() { grep -a "toolCall args" $O/stdout.txt | tail -1 | grep -a -o "\"type\": \"[a-zA-Z]*\"" | tail -1 | cut -d\" -f4; }
now() { date +%T.%N | cut -c1-12; }
ev() { echo "$(now) $1" >> $O/script_events.txt; }
pagelog() { python3 - <<PY
import json,urllib.request,asyncio,websockets
async def main():
    t=[x for x in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if x["type"]=="page"][0]
    async with websockets.connect(t["webSocketDebuggerUrl"]) as ws:
        await ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":"JSON.stringify(window.__log.map(x=>x[1]))"}})); print(json.loads(await ws.recv())["result"]["result"].get("value"))
asyncio.run(main())
PY
}
reached() { pagelog | grep -c "\"$1\""; }
turn() { n=$(nrender); ev "ASK $1 | page: $(pagelog)"; echo "$1" > $O/fifo; for i in $(seq 60); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 1.5; P=$(lastpx); T=$(lasttype); ev "RENDER at $P plantype=$T renders=$(nrender)"; }
clickifclick() { if [ "$T" = click ] && [ -n "$P" ]; then set -- $P; xdotool mousemove $1 $2; sleep 0.3; xdotool click 1; ev "CLICK $1 $2"; else ev "NO CLICK (plantype=$T)"; fi; sleep 1.5; }
( sleep 18
  turn "Point to the Start order button."; clickifclick
  ev "EDGE deliberate ask while page loading"; turn "Point to the Choose size button."; clickifclick
  for i in $(seq 30); do [ $(reached "s2 shown late") -ge 1 ] && break; sleep 0.5; done; ev "page loaded: $(pagelog)"
  turn "Point to the Choose size button."; clickifclick; ev "reached step3? $(reached step3)"
  turn "Point to the Add toppings button."; clickifclick; ev "reached step4? $(reached step4)"
  turn "Point to the Review order button."; clickifclick; ev "reached step5? $(reached step5)"
  turn "Point to the Place test order button."; clickifclick; ev "reached step6 (done)? $(reached step6)"; ev "FINAL page: $(pagelog)"
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording" ; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== script events"; cat $O/script_events.txt
echo "== app log"; grep -a -E "render cursor|refus|toolCall args|perception|sent JPEG|429|rror" $O/stdout.txt | cut -c1-200 | head -60
