#!/bin/bash
# ASSESSMENT (not a pass/fail gate): Skip 0.4s after an ask, while the ask-start sync capture/perceive blocks the loop. # was: STALE REPLAY: Skip lands while a Retry replay is mid-capture/mid-perception. Invariants from the RAW trace: no render, no retry_replay event and no arming after the terminal Skip; the in-flight task is logged cancelled; then a FRESH ask and a FRESH @retry on the NEW plan still work (the old cancel must not disarm/revive anything). Owned page, real Chrome/AT-SPI/YOLO/OCR on virtual X11, fake model, point-only.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
A_STEPS_EFF='{"open":["Open settings","No-op action"],"other":"Open settings"}'; [ -n "$A_STEPS" ] && A_STEPS_EFF="$A_STEPS"
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client2:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_TYPES=${A_TYPES:-observe,observe} TIPTOUR_FAKE_GOAL1="goal A" TIPTOUR_FAKE_STEPS="$A_STEPS_EFF"
export TIPTOUR_FAKE_EXTRA="${FAKE_EXTRA:-[]}"
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O TIPTOUR_LOG_MS=1
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
waitr() { n=$1; for i in $(seq 60); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
( sleep 25
  echo "point open" > $O/fifo; echo "$(date +%T.%N) plan A (observe x2: Open settings 107,268 then No-op action 238,268) ask sent" >> $O/script_events.txt
  for i in $(seq 160); do [ $(nrender) -ge 1 ] && break; sleep 0.05; done
  sleep ${TEXT_DELAY:-0.2}; echo "hello there how are you" > $O/fifo; echo "$(date +%T.%N) TEXT-ONLY ask (no toolCall) ${TEXT_DELAY:-0.2}s after A step1 render" >> $O/script_events.txt
  sleep 14; echo $(nrender) > $O/r_end.txt
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording"; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "render cursor|control |advance|cancel|refus|superseded" $O/stdout.txt | cut -c1-200
echo "== script events"; cat $O/script_events.txt
echo "renders total: $(cat $O/r_end.txt)  (oracle: 2 = A step2 (238,268) rendered AND "plan complete" logged; 1 = the pending observe advance was killed; read the log for ordering - TEXT_DELAY 0.2 = during the 650ms hold, 1.5 = during the advance resolve)"
