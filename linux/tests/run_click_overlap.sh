#!/bin/bash
# Real xfwm4 + real Chrome (owned page): another owned top-level window overlaps the armed target. A click on the overlapped target point must NOT count; after it closes the same click must.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"open":"Open settings","noop":"No-op action"}' TIPTOUR_CLICK_VALIDATE=0
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
lastpx() { grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/"; }
say() { echo "$1" > $O/fifo; }
ev() { echo "$(date +%T) $1" >> $O/script_events.txt; }
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
sayw() { n=$(nrender); say "$1"; for i in $(seq 80); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
( sleep 25
  sayw "point noop"; read X Y <<< "$(lastpx)"; ev "armed target px $X $Y"
  python3 tests/overlap_window.py $((X-150)) $((Y-80)) 300 160 14 & OW=$!; sleep 2.5
  xdotool search --name ownedOverlap | head -1 > $O/overlap_wid.txt; W=$(cat $O/overlap_wid.txt)
  xdotool windowmove $W $((X-150)) $((Y-80)); xdotool windowraise $W; sleep 1
  xdotool getwindowgeometry $W >> $O/script_events.txt 2>&1; ev "overlap window wanted at $((X-150)),$((Y-80)) size 300x160 (target $X,$Y); WM-reported geometry above"
  xdotool getmouselocation >> $O/script_events.txt
  xdotool mousemove $X $Y; sleep 0.3; xdotool click 1; sleep 1; ev "click on target point while overlapped (must NOT count)"
  sleep 0.5; ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 $O/overlapped.png 2>/dev/null
  wait $OW; sleep 1.5; ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 $O/after_close.png 2>/dev/null
  xdotool mousemove $X $Y; sleep 0.3; xdotool click 1; sleep 2; ev "click on target point after overlap closed (must count)"
  say "@quit" ) &
SUB=$!
python3 -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1
wait $SUB 2>/dev/null; pkill -INT -x ffmpeg; sleep 1; pkill -x ffmpeg; pkill -x chrome; pkill -x xfwm4; kill $XP; true' >/dev/null 2>&1
echo "== script events"; cat $O/script_events.txt
echo "== presses"; python3 -c "
import json;d=json.load(open(\"$O/click_events.json\"));[print(p) for p in d[\"presses\"]];print(d[\"events\"],d[\"errors\"])"
