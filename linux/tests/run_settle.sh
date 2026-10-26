#!/bin/bash
# Release-vs-late-arrival race: click the target at several offsets (1.30-1.56s after the render, around the end of the 1.34s flight and the 0.22s settle) on a freshly reloaded owned page each cycle; asserts that no "pointing" event follows a "release" and the overlay ends in follow with the label hidden. FAKE model, virtual Xvfb.
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
  reload() { python3 - <<PY
import json,urllib.request,asyncio,websockets
async def main():
    t=[x for x in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if x["type"]=="page"][0]
    async with websockets.connect(t["webSocketDebuggerUrl"]) as ws:
        await ws.send(json.dumps({"id":1,"method":"Page.reload","params":{}})); await ws.recv()
asyncio.run(main())
PY
  }
  for OFF in 1.30 1.40 1.48 1.56; do
    reload; sleep 5
    n=$(nrender); echo "point open" > $O/fifo; for i in $(seq 100); do [ $(nrender) -gt $n ] && break; sleep 0.05; done
    echo "$(date +%s.%N) offset $OFF render-seen" >> $O/cycles.txt
    read X Y <<< "$(grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/")"
    sleep $OFF; xdotool mousemove $X $Y; xdotool click 1; echo "$(date +%s.%N) offset $OFF clicked" >> $O/cycles.txt; xdotool mousemove 900 650
    sleep 6
  done
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording" ; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
 grep -a -E "render cursor" $O/stdout.txt | cut -c1-100

python3 - <<PY
import json
O="$O"; d=json.load(open(O+"/overlay_events.json")); ev=d["events"]
cyc=[l.split() for l in open(O+"/cycles.txt")]
starts=[float(c[0]) for c in cyc if c[-1]=="render-seen"]; clicks=[float(c[0]) for c in cyc if c[-1]=="clicked"]
ok=True
for s,c in zip(starts,clicks):
    seq=[(round(e["t"]-s,2),e["kind"]) for e in ev if s-0.2<=e["t"]<=c+4 and e["kind"] in ("nav_start","pointing","release","arrival_ignored","dock","follow","return_cancelled_by_mouse")]
    kinds=[k for _,k in seq]
    print("cycle click at +%.2fs after render:"%(c-s), seq)
    if "release" in kinds:
        after=kinds[kinds.index("release"):]
        if "pointing" in after: ok=False
print("final overlay state:", d["final"])
print("ASSERT 1 in every cycle no pointing (label re-enabled) event after the release:", ok)
print("ASSERT 2 final overlay: follow mode, label hidden, not retired:", d["final"]["mode"]=="follow" and not d["final"]["show_label"] and not d["final"]["retired"])
print("ASSERT 3 four cycles ran with a release each:", sum(1 for e in ev if e["kind"]=="release")>=4)
PY
