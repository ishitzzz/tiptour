#!/bin/bash
# Teaching flow on an OWNED page, real Chrome/AT-SPI, real xdotool clicks, fake model (canned toolcalls). Point-only, --act OFF.
# T1 "Open settings": click -> AT-SPI state changes -> validator 'changed' -> pointer dismissed
# T2 "No-op action": click -> nothing changes -> validator 'unchanged_paused' (pointer kept)
# T3a stale-a: target moved during an 8s model delay (label resolves live -> follows, no refusal expected). T3b staleb: target removed + region repainted, model point on the old target -> expect refusal, no cursor, no arm
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"open":"Open settings","noop":"No-op action"}'
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
lastpx() { grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/"; }
say() { echo "$1" > $O/fifo; }
ev() { echo "$(date +%T) $1" >> $O/script_events.txt; }
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
sayw() { n=$(nrender); say "$1"; for i in $(seq 80); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
cdp_eval() { python3 - "$1" <<PY
import json,sys,urllib.request,asyncio,websockets
async def main():
    t=[x for x in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if x["type"]=="page"][0]
    async with websockets.connect(t["webSocketDebuggerUrl"]) as ws:
        await ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":sys.argv[1]}})); await ws.recv()
asyncio.run(main())
PY
}
( sleep 25
  sayw "point open"; read X Y <<< "$(lastpx)"; ev "T1 px $X $Y"
  for i in $(seq 60); do grep -a -q "validator baseline ready" $O/stdout.txt && break; sleep 0.5; done
  xdotool mousemove $X $Y; sleep 0.3; xdotool click 1; sleep 20; ev "T1 click done"
  say "@quit" ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -x ffmpeg; sleep 1; pkill -x ffmpeg; pkill -x chrome; pkill -x xfwm4; kill $XP; true' >/dev/null 2>&1
echo "== script events"; cat $O/script_events.txt
echo "== app log"; grep -a -E "click|render cursor|validator|refus|stale-frame" $O/stdout.txt | grep -v '" result {' | cut -c1-200
echo "== click_events.json"; cat $O/click_events.json; echo
echo "== tool results"; python3 - <<PY
import json;[print(r.get("ask"),"|",r.get("tool",{}).get("source"),r.get("tool",{}).get("click_detector"),r.get("tool",{}).get("refused")) for r in json.load(open("$O/results.json"))]
PY
