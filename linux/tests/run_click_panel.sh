#!/bin/bash
# On-screen pause panel: no-op click -> panel (Retry/Skip) visible; REAL xdotool click on the Retry button re-arms; click no-op again; REAL click on Skip dismisses panel+pointer. Owned page, fake model, --act OFF.
cd /home/sandbox/tiptour/linux
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"open":"Open settings","noop":"No-op action"}'
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O TIPTOUR_PANEL_COORDS=$O/panel_coords.txt
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
lastpx() { grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/"; }
say() { echo "$1" > $O/fifo; }
ev() { echo "$(date +%T) $1" >> $O/script_events.txt; }
shot() { ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 $O/$1.png 2>/dev/null; }
( sleep 25
  say "point noop"; for i in $(seq 60); do grep -a -q "render cursor at" $O/stdout.txt && break; sleep 0.5; done; sleep 2; read X Y <<< "$(lastpx)"; ev "target px $X $Y"
  for i in $(seq 60); do grep -a -q "validator baseline ready" $O/stdout.txt && break; sleep 0.5; done
  xdotool mousemove $X $Y; sleep 0.3; xdotool click 1; sleep 28; shot 1_panel_after_noop; ev "no-op clicked; panel expected"
  ev "overlay-class windows: $(xdotool search --class TipTourOverlay | tr "\n" " ")"
  cp $O/panel_coords.txt $O/panel_buttons.txt; rm $O/panel_coords.txt; ev "buttons: $(cat $O/panel_buttons.txt | tr "\n" ";")"
  read RX RY <<< "$(grep ^retry $O/panel_buttons.txt | cut -d" " -f2-3)"; read SX SY <<< "$(grep ^skip $O/panel_buttons.txt | cut -d" " -f2-3)"
  xdotool mousemove $RX $RY; sleep 0.3; xdotool click 1; sleep 3; shot 2_after_retry_click; ev "Retry button clicked"
  for i in $(seq 40); do [ $(grep -a -c "validator baseline ready" $O/stdout.txt) -ge 2 ] && break; sleep 0.5; done
  xdotool mousemove $X $Y; sleep 0.3; xdotool click 1; sleep 28; shot 3_panel_again; ev "no-op clicked again"
  sleep 1; cp $O/panel_coords.txt $O/panel_buttons2.txt
  read SX SY <<< "$(grep ^skip $O/panel_buttons2.txt | cut -d" " -f2-3)"
  xdotool mousemove $SX $SY; sleep 0.3; xdotool click 1; sleep 3; shot 4_after_skip_click; ev "Skip button clicked"
  say "@quit" ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -x ffmpeg; sleep 1; pkill -x ffmpeg; pkill -x chrome; pkill -x xfwm4; kill $XP; true' >/dev/null 2>&1
echo "== script events"; cat $O/script_events.txt; echo "== log"; grep -a -E "control|validator:|post-click" $O/stdout.txt | cut -c1-170
