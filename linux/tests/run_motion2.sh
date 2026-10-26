#!/bin/bash
# Retry / Resume = re-capture + rerun the full resolver cascade for the active step (Mac retryCurrentStep()/resume()). Owned page, real Chrome + AT-SPI + real YOLO/OCR, FAKE model, point-only.
# 1) "point open" -> pointed. 2) @resume while NOT paused -> refused. 3) @retry -> fresh capture + full cascade -> a SECOND render at the same control; the model got no second tool_response.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"open":"Open settings"}'
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O REC_FPS=30
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
waitr() { n=$1; for i in $(seq 80); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
( sleep 20
  # (1) FOLLOW: move the real X pointer, sample the overlay window position
  WID=$(xdotool search --classname tiptour-overlay | head -1); echo $WID > $O/overlay_wid.txt
  samp() { echo "$(date +%s.%N) $1 $(xdotool getmouselocation | tr " " "\n" | grep -E "^(x|y):" | tr "\n" " ") $(xdotool getwindowgeometry $WID | grep Position | sed -E "s/.*Position: ([0-9-]+),([0-9-]+).*/\1 \2/")" >> $O/samples.txt; }
  for p in "300 300" "700 500" "400 700" "800 300"; do xdotool mousemove $p; for i in $(seq 8); do samp follow; sleep 0.06; done; done
  # (2) FLIGHT to the target: sample every ~50ms
  echo "point open" > $O/fifo; n0=$(nrender); for i in $(seq 160); do samp flight; sleep 0.05; [ $(nrender) -gt $n0 ] && break; done; for i in $(seq 70); do samp settle; sleep 0.05; done
  # (3) click the target (owned page), retire -> fly back to the cursor
  read X Y <<< "$(grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/")"; echo "$X $Y" > $O/target.txt
  xdotool mousemove $X $Y; sleep 0.2; xdotool click 1; sleep 0.1; xdotool mousemove 1000 700; for i in $(seq 110); do samp afterclick; sleep 0.05; done
  # (5) STRESS early click: a click on the target DURING the flight (0.4s after the render); the label chip must not revive after the release
  sleep 2; echo "point open" > $O/fifo; n=$(nrender); for i in $(seq 100); do [ $(nrender) -gt $n ] && break; sleep 0.1; done; sleep 0.4
  xdotool mousemove $X $Y; sleep 0.1; xdotool click 1; sleep 0.1; xdotool mousemove 900 650; for i in $(seq 120); do samp early; sleep 0.05; done
  # (4) mouse moved > 100px during a return cancels it
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording" ; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== samples"; wc -l $O/samples.txt; head -3 $O/samples.txt; cat $O/target.txt; grep -a -E "render cursor" $O/stdout.txt | cut -c1-100
