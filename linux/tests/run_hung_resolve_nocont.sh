#!/bin/bash
# Deliberate STALE REPLAY: Skip lands while a Retry replay is mid-capture/mid-perception. Invariants from the RAW trace: no render, no retry_replay event and no arming after the terminal Skip; the in-flight task is logged cancelled; then a FRESH ask and a FRESH @retry on the NEW plan still work (the old cancel must not disarm/revive anything). Owned page, real Chrome/AT-SPI/YOLO/OCR on virtual X11, fake model, point-only.
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
  echo "point open" > $O/fifo; waitr 0; echo $(nrender) > $O/r1.txt
  # HUNG RESOLVER (external, no product change): SIGSTOP the AT-SPI child while the retry resolves, then Skip, then SIGCONT
  echo "@retry" > $O/fifo; STOPPED=0
  for i in $(seq 400); do P=$(pgrep -f "[p]ython.* -m tiptour_linux.atspi_resolver --(targets|probe)" | head -1); [ -n "$P" ] && { kill -STOP $P && STOPPED=$P; break; }; sleep 0.01; done
  echo "$(date +%T.%N) stopped_child=$STOPPED cmd=$(tr "\0" " " < /proc/$STOPPED/cmdline 2>/dev/null | cut -c1-80)" >> $O/script_events.txt
  sleep 1.5; echo "@skip" > $O/fifo; echo "$(date +%T.%N) skip sent while child stopped" >> $O/script_events.txt
  sleep 1; echo "$(date +%T.%N) NO SIGCONT: child left stopped; the app timeout must kill it" >> $O/script_events.txt
  sleep 20; echo $(nrender) > $O/r_after_skip.txt
  n=$(nrender); echo "point open" > $O/fifo; waitr $n; echo $(nrender) > $O/r_fresh_ask.txt
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording"; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "render cursor|control |advance|cancel|refus|superseded" $O/stdout.txt | cut -c1-200
python3 - <<PY
import json
O="$O"; r=lambda n:int(open(O+"/"+n).read() or 0); log=open(O+"/stdout.txt",errors="ignore").read()
ev=[e.get("control") or e.get("advance") for e in json.load(open(O+"/click_events.json"))["events"]]
print("events",ev)
print("ASSERT 0 the AT-SPI child really was stopped mid-retry (else the test proved nothing):", "stopped_child=0 " not in open(O+"/script_events.txt").read() and "-m tiptour_linux.atspi_resolver" in open(O+"/script_events.txt").read())
print("ASSERT 1 first ask rendered:", r("r1.txt")==1)
print("ASSERT 2 NO render after the Skip that landed while the resolver was hung (and after it resumed):", r("r_after_skip.txt")==1)
print("ASSERT 3 fresh ask after the hung episode renders:", r("r_fresh_ask.txt")==2)
_sk=[i for i,e in enumerate(ev) if e=="skip"]
print("ASSERT 4 no retry_replay event between the Skip and the fresh ask (events after first skip, before the fresh ask render):", bool(_sk) and "retry_replay" not in ev[_sk[0]+1:])
PY
