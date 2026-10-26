#!/bin/bash
# Unrelated-app mutation must NOT certify a no-op click: noop button clicked while a different GTK app changes its controls. Expect validator unchanged_paused (app-scoped fingerprint).
cd /home/sandbox/tiptour/linux
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
MUTATE_FLAG=$O/mutate.flag python3 tests/mutator_app.py & MP=$!
( sleep 25; for w in $(xdotool search --onlyvisible --class google-chrome); do xdotool windowactivate $w 2>/dev/null; done; sleep 2
  sayw "point noop"; read X2 Y2 <<< "$(lastpx)"; ev "noop px $X2 $Y2"
  for i in $(seq 60); do grep -a -q "validator baseline ready" $O/stdout.txt && break; sleep 0.5; done; ev "baseline wait done: $(grep -a "baseline ready" $O/stdout.txt | cut -c1-120)"
  xdotool mousemove $X2 $Y2; sleep 0.3; xdotool click 1; touch $O/mutate.flag; ev "noop click done + unrelated app mutated at the same moment"; sleep 22
  PYTHONPATH=. python3 -c "
from tiptour_linux import atspi_resolver as a
ts=a.all_targets(6)
print(sorted({(t[\"app\"],t[\"label\"]) for t in ts if \"nrelated\" in t[\"label\"] or \"nrelated\" in (t[\"app\"] or \"\")}))
" > $O/atspi_after_mutation.txt 2>&1
  say "@quit"; sleep 2; kill $MP ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -x ffmpeg; sleep 1; pkill -x ffmpeg; pkill -x chrome; pkill -x xfwm4; kill $XP; true' >/dev/null 2>&1
echo "== script events"; cat $O/script_events.txt
echo "== app log"; grep -a -E "click|render cursor|validator|refus|stale-frame" $O/stdout.txt | grep -v '" result {' | cut -c1-200
echo "== click_events.json"; cat $O/click_events.json; echo
echo "== tool results"; python3 - <<PY
import json;[print(r.get("ask"),"|",r.get("tool",{}).get("source"),r.get("tool",{}).get("click_detector"),r.get("tool",{}).get("refused")) for r in json.load(open("$O/results.json"))]
PY
