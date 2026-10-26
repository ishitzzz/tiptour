#!/bin/bash
# CONFIRMATION GATE (fake model; real X11/Chrome/AT-SPI). CMDS="cmd1;cmd2;..." sent via the serve fifo, 7s apart; the render count after each is recorded in steps.txt.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client2:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_TYPES=observe,observe TIPTOUR_FAKE_GOAL1="goal A" TIPTOUR_FAKE_STEPS='{"open":["Open settings","No-op action"],"other":["Open settings"]}'
export TIPTOUR_FAKE_GOALS='{"other":"goal B"}'
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O CMDS="${CMDS:?}" TIPTOUR_LOG_MS=1
env | grep "^TIPTOUR_FAKE\|^TIPTOUR_CLIENT" | sort > $O/fake_config.txt; echo "$CMDS" > $O/cmds.txt
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
( sleep 25; IFS=";" read -ra C <<< "$CMDS"; for c in "${C[@]}"; do if [ "${c:0:1}" = "~" ]; then c="${c:1}"; echo "$c" > $O/fifo; echo "$(date +%T.%N) sent(no wait): $c" >> $O/script_events.txt; sleep 0.3; continue; fi; echo "$c" > $O/fifo; echo "$(date +%T.%N) sent: $c" >> $O/script_events.txt; sleep ${STEP_WAIT:-7}; echo "$c => renders=$(nrender)" >> $O/steps.txt; done; echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording"; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== steps"; cat $O/steps.txt; echo "== gate events"
python3 -c "
import json;[print(e) for e in json.load(open('$O/click_events.json'))['events'] if 'gate' in e]"
grep -a "PLAN PROPOSAL\|confirmation:" $O/stdout.txt | cut -c1-200
