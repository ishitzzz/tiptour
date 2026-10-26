#!/bin/bash
# VOICE ORDERING (fake model, @voice turn without mic): events from TIPTOUR_FAKE_VOICE_SCRIPT fire after the ask-start screenshot. Records which toolCall ids were gated/accepted.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client2:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_TYPES=observe,observe TIPTOUR_FAKE_GOAL1="goal A" TIPTOUR_FAKE_STEPS='{"open":["Open settings","No-op action"]}'
export TIPTOUR_STREAM=0 TIPTOUR_TEST_FAKE_MIC=1 TIPTOUR_FAKE_VOICE_SCRIPT="${VOICE_SCRIPT:?}" TIPTOUR_FAKE_VOICE_SCRIPT2="${VOICE_SCRIPT2:-}" TIPTOUR_FAKE_VOICE_SCRIPT3="${VOICE_SCRIPT3:-}"
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O TIPTOUR_LOG_MS=1
env | grep "^TIPTOUR_FAKE\|^TIPTOUR_CLIENT" | sort > $O/fake_config.txt
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
( sleep 25; echo "@voice" > $O/fifo; echo "$(date +%T.%N) @voice sent" >> $O/script_events.txt; sleep ${POST_WAIT:-14}; echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording"; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "confirmation|voice|boundary|rejecting|superseding|render cursor|toolCall |transcript|ignoring|plan|suppress|answer|turnComplete" $O/stdout.txt | cut -c1-200
python3 -c "
import json;print([e for e in json.load(open('$O/click_events.json'))['events'] if 'gate' in e])" 2>&1
