#!/bin/bash
# Teaching-mode click detector, real Chrome + real xdotool clicks on an OWNED page (fake model = canned toolcalls; point-only, --act OFF).
# Turn1 point "Save changes": click far away (must NOT fire), click on target (fires, pointer dismissed).
# Turn2 point "Cancel": click Save (miss, no fire), then click Cancel (fires).
# Turn3 point "Save changes" then immediately a new turn "cancel" re-arms: click on old Save target must NOT fire (disarmed/new plan).
cd /home/sandbox/tiptour/linux
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"save":"Save changes","cancel":"Cancel"}'
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O
dbus-run-session -- bash -c '
EXPECT_IDS=gear,save EXPECT_TITLE="Owned Controls Test" . tests/browser_env.sh http://localhost:8765/index.html $O
lastpx() { grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/"; }
say() { echo "$1" > $O/fifo; }
ev() { echo "$(date +%T) $1" >> $O/script_events.txt; }
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
# say, then wait (max 40s) until a NEW render line appears, then settle 2s (glide is 0.6s)
sayw() { n=$(nrender); say "$1"; for i in $(seq 80); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
nclk() { cat $O/clicklog.txt 2>/dev/null | wc -l; }
( sleep 25
  sayw "point save"; read X Y <<< "$(lastpx)"; ev "turn1 px $X $Y"
  xdotool mousemove 1500 900 click 1; sleep 1; ev "far click done"
  xdotool mousemove $X $Y; sleep 0.3; xdotool click 1; sleep 2; ev "target click done"
  sayw "point cancel"; read X2 Y2 <<< "$(lastpx)"; ev "turn2 px $X2 $Y2"
  xdotool mousemove $X $Y click 1; sleep 1; ev "click on Save (wrong) done"
  xdotool mousemove $X2 $Y2; sleep 0.3; xdotool click 1; sleep 2; ev "click on Cancel done"
  sayw "point save"; read X3 Y3 <<< "$(lastpx)"; ev "turn3a px $X3 $Y3"
  sayw "point cancel"; ev "turn3b re-armed on cancel"
  xdotool mousemove $X3 $Y3 click 1; sleep 1; ev "click on stale Save target done"
  say "@quit" ) &
SUB=$!
TIPTOUR_HANG_DUMP=${HANG_DUMP:-240} python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1
wait $SUB 2>/dev/null; pkill -INT -x ffmpeg; sleep 1; pkill -x ffmpeg; pkill -x chrome; pkill -x xfwm4; kill $XP; true' >/dev/null 2>&1
echo "== script events"; cat $O/script_events.txt
echo "== app log (click lines)"; grep -a -E "click|render cursor|armed" $O/stdout.txt
echo "== click_events.json"; cat $O/click_events.json; echo
echo "== tool results"; python3 - <<PY
import json;[print(r.get("tool",{}).get("source"),r.get("tool",{}).get("click_detector"),r.get("tool",{}).get("px")) for r in json.load(open("$O/results.json"))]
PY
