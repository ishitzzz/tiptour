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
  echo "@retry" > $O/fifo; sleep 0.4; echo "@skip" > $O/fifo; sleep 12; echo $(nrender) > $O/r_after_skip.txt
  n=$(nrender); echo "point open" > $O/fifo; waitr $n; echo $(nrender) > $O/r_fresh_ask.txt
  n=$(nrender); echo "@retry" > $O/fifo; waitr $n; echo $(nrender) > $O/r_fresh_retry.txt
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
print("ASSERT 1 first ask rendered:", r("r1.txt")==1)
print("ASSERT 2 NO render after the mid-capture Skip:", r("r_after_skip.txt")==1)
i_skip = ev.index("skip") if "skip" in ev else -1
rr = [i for i, x in enumerate(ev) if x == "retry_replay"]
fresh_ctl = [i for i, x in enumerate(ev) if x == "retry" and i > i_skip]
print("ASSERT 3 the cancelled in-flight retry produced NO retry_replay: the ONLY retry_replay is the one that follows the fresh retry control issued after the skip:", i_skip >= 0 and len(rr) == 1 and len(fresh_ctl) == 1 and rr[0] > fresh_ctl[0])
print("ASSERT 4 in-flight replay cancelled or refused superseded (logged):", ("in-flight replay/advance cancelled" in log) or ("superseded" in log))
print("ASSERT 5 fresh ask after skip renders (new plan not disarmed/blocked):", r("r_fresh_ask.txt")==2)
print("ASSERT 6 fresh @retry on the NEW plan re-resolves and renders:", r("r_fresh_retry.txt")==3)
PY
