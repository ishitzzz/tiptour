#!/bin/bash
# Mac validator parity: the AX fingerprint is role|title|value with GEOMETRY EXCLUDED, so a target that merely MOVES (no state change) and a click at the OLD pointed point must read "unchanged" and pause (Mac WorkflowRunner.swift:1376-1465 / postClickStateUnchanged), never "changed". Owned page (movebtn.html), real Chrome + AT-SPI, FAKE model, click plan; synthetic xdotool click.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1 TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"toppings":"Add toppings"}' TIPTOUR_LOG_MS=1
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O
dbus-run-session -- bash -c '
EXPECT_IDS=b EXPECT_TITLE="Move Test" . tests/browser_env.sh http://localhost:8765/movebtn.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
( sleep 22; echo "point toppings" > $O/fifo; for i in $(seq 100); do [ $(nrender) -ge 1 ] && break; sleep 0.3; done; sleep 4
  python3 - <<PY
import json,urllib.request,asyncio,websockets
async def main():
    t=[x for x in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json")) if x["type"]=="page"][0]
    async with websockets.connect(t["webSocketDebuggerUrl"]) as ws:
        await ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":"window.go()"}})); await ws.recv()
asyncio.run(main())
PY
  echo "$(date +%T.%N) page control moved" >> $O/script_events.txt; sleep 1.5
  read X Y <<< "$(grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/")"; xdotool mousemove $X $Y; sleep 0.3; xdotool click 1; echo "$(date +%T.%N) clicked OLD point $X $Y" >> $O/script_events.txt; sleep 8
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording" ; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "render cursor|click|validator|paused" $O/stdout.txt | cut -c1-220; cat $O/script_events.txt
python3 - <<PY
log=open("$O/stdout.txt",errors="ignore").read()
print("ASSERT 1 control moved + click at the OLD point -> validator reads UNCHANGED and pauses (not changed):", "post-click validator: AT-SPI state unchanged" in log and "effect confirmed" not in log)
PY
