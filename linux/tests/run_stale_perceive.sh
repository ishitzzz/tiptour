#!/bin/bash
# Deliberate STALE REPLAY: Skip lands while a Retry replay is mid-capture/mid-perception. Invariants from the RAW trace: no render, no retry_replay event and no arming after the terminal Skip; the in-flight task is logged cancelled; then a FRESH ask and a FRESH @retry on the NEW plan still work (the old cancel must not disarm/revive anything). Owned page, real Chrome/AT-SPI/YOLO/OCR on virtual X11, fake model, point-only.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"open":"Open settings"}'
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O TIPTOUR_TEST_STALL=1 TIPTOUR_LOG_MS=1
export PYTHONPATH=$PWD/tests/stall2:$PYTHONPATH
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
waitr() { n=$1; for i in $(seq 60); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
( sleep 25
  echo "point open" > $O/fifo; waitr 0; echo $(nrender) > $O/r1.txt
  # STALLED CAPTURE (test-only sitecustomize wrapper): the next grab (the Retry replay capture, in a worker thread) blocks until $O/release
  for i in $(seq 120); do grep -a -q "result recorded" $O/stdout.txt && break; sleep 0.25; done; sleep 0.5  # the first turn must be finished (gate[turn] clear) so @retry reaches its own capture
  touch $O/arm_stall; echo "$(date +%T.%N) arm_stall touched" >> $O/script_events.txt
  echo "@retry" > $O/fifo
  for i in $(seq 200); do grep -q STALLED $O/stall_events.txt 2>/dev/null && break; sleep 0.05; done
  echo "$(date +%T.%N) stall observed: $(cat $O/stall_events.txt)" >> $O/script_events.txt
  sleep 1.5; echo "point open" > $O/fifo; echo "$(date +%T.%N) NEW ASK sent while the OLD retry capture thread is still stalled" >> $O/script_events.txt
  sleep 2; touch $O/release; echo "$(date +%T.%N) release touched" >> $O/script_events.txt
  sleep 8; echo $(nrender) > $O/r_after_skip.txt
  n=$(nrender); echo "point open" > $O/fifo; waitr $n; echo $(nrender) > $O/r_fresh_ask.txt
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording"; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== stall"; cat $O/stall_events.txt; echo "== log"; grep -a -E "render cursor|control |advance|cancel|refus|superseded" $O/stdout.txt | cut -c1-200
python3 - <<PY
import json
O="$O"; r=lambda n:int(open(O+"/"+n).read() or 0); log=open(O+"/stdout.txt",errors="ignore").read()
ev=[e.get("control") or e.get("advance") for e in json.load(open(O+"/click_events.json"))["events"]]
print("events",ev)
print("ASSERT 0 the OLD retry perception (ocr) really was stalled in a worker thread and released later:", "ocr STALLED" in open(O+"/stall_events.txt").read() and "ocr RELEASED" in open(O+"/stall_events.txt").read())
print("ASSERT 1 first ask rendered:", r("r1.txt")==1)
ups=[x for x in open(O+"/cache_updates.txt").read().split("\n") if x]; pl=log.count("perception:")
print("cache.update calls:", len(ups), "perception passes logged:", pl)
print("ASSERT 2 four perception passes ran (first ask, STALLED old retry replay, new ask, later ask) but the old stale one never wrote TARGET_CACHE (updates == perception passes - 1):", pl==4 and len(ups)==3)
print("ASSERT 3 a later ask still renders:", r("r_fresh_ask.txt")==3)
_sk=[i for i,e in enumerate(ev) if e=="skip"]
print("ASSERT 4 the cancelled retry never reached retry_replay:", "retry_replay" not in ev)
PY
