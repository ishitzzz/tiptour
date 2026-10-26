#!/bin/bash
# Real xfwm4 + real Chrome (owned page): another owned top-level window overlaps the armed target. A click on the overlapped target point must NOT count; after it closes the same click must.
cd /home/sandbox/tiptour/linux
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
  python3 tests/overlap_window.py $((X-150)) $((Y-80)) 300 160 8 & OW=$!; sleep 2.5
  W=$(xdotool search --name ownedOverlap | head -1); xdotool windowmove $W $((X-150)) $((Y-80)); xdotool windowraise $W; sleep 3
  ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 $O/1_covered.png 2>/dev/null; ev "covered/paused screenshot"
  wait $OW; sleep 2; ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 $O/2_after_close_no_resume.png 2>/dev/null; ev "cover removed; pointer must STAY hidden (app-switch pause, no auto-resume)"
  xdotool mousemove $X $Y; sleep 0.3; xdotool click 1; sleep 1.5; ev "click while paused (must not count)"
  xdotool mousemove 900 900; xdotool search --class Chrome | head -1 | xargs -I{} xdotool windowfocus {}; sleep 1
  say "@retry"; sleep 2; ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 $O/3_after_retry.png 2>/dev/null; ev "@retry sent with Chrome focused"
  say "@skip"; sleep 2; ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 $O/4_after_skip.png 2>/dev/null; ev "@skip sent"
  say "@skip"; sleep 1; say "@retry"; sleep 2; ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 $O/4b_after_double_skip_retry.png 2>/dev/null; ev "double @skip then @retry after skip sent (both must be refused; pointer stays hidden)"
  python3 tests/overlap_window.py $((X-150)) $((Y-80)) 300 160 4 & OW=$!; sleep 6; wait $OW; sleep 1.5; ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 $O/5_cover_after_skip_no_resurrect.png 2>/dev/null; ev "cover opened and closed AFTER skip; pointer must stay hidden"
  say "@quit" ) &
SUB=$!
python3 -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1
wait $SUB 2>/dev/null; pkill -INT -x ffmpeg; sleep 1; pkill -x ffmpeg; pkill -x chrome; pkill -x xfwm4; kill $XP; true' >/dev/null 2>&1
echo "== script events"; cat $O/script_events.txt
echo "== presses"; python3 -c "
import json;d=json.load(open(\"$O/click_events.json\"));[print(p) for p in d[\"presses\"]];print(d[\"events\"],d[\"errors\"])"
