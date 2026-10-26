#!/bin/bash
# Idle context stream parity (Mac GeminiLiveSession.captureAndProcessFrameForGemini): 3.0s timer (1s here), perceptual-hash dedup, suppressed after a plan renders until the next ask, skipped while a plan/resolve is active. Owned page, FAKE model. Asserts: >=1 and <=2 idle frames before the first ask, 0 after the first render. Does NOT prove pixel exclusion of the follower.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_TYPES=observe,observe TIPTOUR_FAKE_STEPS='{"open":["Open settings","No-op action"]}'
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O TIPTOUR_STREAM_INTERVAL=1
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
waitr() { n=$1; for i in $(seq 80); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
( sleep 22; sleep 9   # idle: stream (1s timer here) must send >=1 idle frame, then dedup (same scene) must stop repeats
  echo "point open" > $O/fifo; waitr 0; echo $(nrender) > $O/r1.txt
  sleep 9; echo $(nrender) > $O/r2.txt; echo $(nrender) > $O/r3.txt
  TIPTOUR_USE_CDP=1 python3 - > $O/oracle_rects.json <<PY
print("{}")
PY
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording" ; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "render cursor|control |advance|refus" $O/stdout.txt | cut -c1-200
python3 - <<PY
import re
O="$O"; log=open(O+"/stdout.txt",errors="ignore").read().splitlines()
def t(l): return l[:8]
first=[i for i,l in enumerate(log) if "render cursor at" in l][0]
pre=[l for l in log[:first] if "stream frame sent" in l]; post=[l for l in log[first:] if "stream frame sent" in l]
print("stream frames before first ask:",len(pre),"after the first render:",len(post))
print("ASSERT 1 idle stream sent at least one frame and dedup stopped repeats on the unchanged scene (sent <= 2 over ~30s at 1s timer):", 1<=len(pre)<=2)
print("ASSERT 2 NO stream frame sent after the plan rendered (suppressed until the next user ask / plan active):", len(post)==0)
import glob; print("stream jpgs", sorted(glob.glob(O+"/stream-*.jpg")))
PY
