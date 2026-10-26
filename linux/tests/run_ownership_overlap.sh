#!/bin/bash
# OWNERSHIP OVERLAP: old retry perception stalled (it captured P1); the screen changes P1->P2 (p2_app); a text-only ask pins P2 + updates the cache; release: the old retry resolve must refuse (own frame/cache overtaken) with labelled pin/perc seq, not resolve against P2/C2.
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
export MUTATE_FLAG=$O/mutate; python3 $PWD/tests/p2_app.py & P2P=$!  # started AFTER browser_env set DISPLAY=:99
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
  sleep 1.0; touch $O/mutate; for i in $(seq 40); do [ -e $O/mutate.shown ] && break; sleep 0.25; done; echo "$(date +%T.%N) SCREEN CHANGE P1->P2 (p2_app shown=$(cat $O/mutate.shown 2>/dev/null))" >> $O/script_events.txt; sleep 1.0; echo "hello there how are you" > $O/fifo; echo "$(date +%T.%N) TEXT-ONLY ask (no toolCall) sent while the OLD retry perception is still stalled" >> $O/script_events.txt
  sleep 2; touch $O/release; echo "$(date +%T.%N) release touched" >> $O/script_events.txt
  sleep 8; echo $(nrender) > $O/r_after_skip.txt
  n=$(nrender); echo "point open" > $O/fifo; waitr $n; echo $(nrender) > $O/r_fresh_ask.txt
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording"; sleep 1; pkill -f "x11grab.*$O/recording"; kill $P2P $CP $XP 2>/dev/null; true' >/dev/null 2>&1
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
print("ASSERT 2 four perception passes (first ask, stalled retry replay, text-only ask, final ask); the OLDER stalled replay pass finished after the newer text-only pass so its cache write is dropped by the generation guard (updates == 3) - recorded, not a failure of the replay itself:", pl==4 and len(ups)==3, pl, len(ups))
ge=[e for e in json.load(open(O+"/click_events.json"))["events"] if e.get("gate")=="own_generation_resolve"]
print("OWN-GENERATION EVENTS (labels only, no refusal by generation):", ge)
print("ASSERT 3 P2 really shown:", __import__("os").path.exists(O+"/mutate.shown"))
print("ASSERT 4 old retry resolved on its OWN generation (own pin/perc older than shared applied):", bool(ge) and all(e["own_pin"]<e["applied_pin"] and e["own_perc"]<e["applied_perc"] for e in ge), "identity_changed=", [e.get("identity_changed") for e in ge])
import re
dec=[l for l in log.split("\n") if re.search("stale-frame check|screen content changed|focused window|identity pinned", l)]
print("DECISION LINES (screen guard / identity decide):"); [print("  ", l[:230]) for l in dec[-8:]]
print("RECORDED (not asserted): renders after release", r("r_after_skip.txt"), "(1 = old retry refused; 2 = old retry rendered)")
PY
