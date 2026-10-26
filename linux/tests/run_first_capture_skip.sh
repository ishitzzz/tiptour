#!/bin/bash
# ASSESSMENT (not a pass/fail gate): Skip 0.4s after an ask, while the ask-start sync capture/perceive blocks the loop. # was: STALE REPLAY: Skip lands while a Retry replay is mid-capture/mid-perception. Invariants from the RAW trace: no render, no retry_replay event and no arming after the terminal Skip; the in-flight task is logged cancelled; then a FRESH ask and a FRESH @retry on the NEW plan still work (the old cancel must not disarm/revive anything). Owned page, real Chrome/AT-SPI/YOLO/OCR on virtual X11, fake model, point-only.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"open":"Open settings"}'
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
waitr() { n=$1; for i in $(seq 60); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
( sleep 25
  echo "point open" > $O/fifo; echo "$(date +%T.%N) ask sent" >> $O/script_events.txt
  sleep 0.4; echo "@skip" > $O/fifo; echo "$(date +%T.%N) skip sent 0.4s after the ask (ask-start sync capture/perceive in progress)" >> $O/script_events.txt
  sleep 15; echo $(nrender) > $O/r_after_skip.txt
  n=$(nrender); echo "point open" > $O/fifo; waitr $n; echo $(nrender) > $O/r_fresh_ask.txt
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording"; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "render cursor|control |advance|cancel|refus|superseded" $O/stdout.txt | cut -c1-200
echo "== script events"; cat $O/script_events.txt
python3 - <<PY
import json
O="$O"; log=open(O+"/stdout.txt",errors="ignore").read()
ev=[e.get("control") or e.get("advance") for e in json.load(open(O+"/click_events.json"))["events"]]
print("events",ev)
print("renders after skip window:", open(O+"/r_after_skip.txt").read().strip(), "fresh:", open(O+"/r_fresh_ask.txt").read().strip())
PY
