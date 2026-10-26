#!/bin/bash
# Consolidated regression on the CURRENT tree. Writes STAGES.tsv (stage, status, exit, note). It NEVER prints overall success:
# FINISHED means only "the runner ended"; read STAGES.tsv. A stage that is missing/not executable, or whose preflight fails, is SKIPPED and makes the run INCOMPLETE.
cd /home/sandbox/tiptour/linux
# serialize: ONE runner at a time, and nothing may hold the display/browser lock, BEFORE any environment/resource mutation (units, pkill, Xvfb, Pulse)
# OWN the display lock for the WHOLE run (no check-then-release gap), before any mutation (units, pkill, Xvfb). Stage scripts skip their own lock via TT_X99_OWNED=1.
exec 9>/tmp/tt-x99.lock; flock -n 9 || { echo "display lock /tmp/tt-x99.lock is held by another run; refusing before any mutation" >&2; exit 3; }
export TT_X99_OWNED=1
P=${RUN_DIR:?new unique parent dir}; [ -e $P ] && { echo exists; exit 2; }; mkdir -p $P
. tests/clean_env.sh; tools/snapshot_tree.sh $P
export PYTHONPATH=.
ST=$P/STAGES.tsv; echo -e "stage\tstatus\texit\tnote" > $ST; INCOMPLETE=0
stage() { # name script [preflight-cmd]
  local n=$1 sc=$2 pre=$3
  case " ${ONLY_STAGES:-} " in "  ") ;; *" $n "*) ;; *) return;; esac  # ONLY_STAGES="a b" runs just those (resume without repeating sealed stages/model calls)
  if [ ! -x "$sc" ]; then echo -e "$n\tSKIPPED\t-\tscript missing or not executable" >> $ST; INCOMPLETE=1; return; fi
  if [ -n "$pre" ] && ! eval "$pre" >/dev/null 2>&1; then echo -e "$n\tSKIPPED\t-\tpreflight failed: $pre" >> $ST; INCOMPLETE=1; return; fi
  pkill -x Xvfb; pkill -x chrome; pkill -x xfwm4; pkill dbus-daemon; sleep 2
  if [ "$n" = voice-real ]; then RUN_DIR=$P/$n timeout 330 $sc > $P/$n.txt 2>&1 9>&-; else RUN_DIR=$P/$n $sc > $P/$n.txt 2>&1 9>&-; fi
  local rc=$?; local ex=$(cat $P/$n/app_exit.txt 2>/dev/null | tr -d '\n')
  [ $rc -ne 0 ] && INCOMPLETE=1
  local td=""; [ -f $P/$n/teardown.txt ] && td=" teardown.txt present"
  echo -e "$n\tRAN\t$rc\t${ex:-no app_exit.txt}$td" >> $ST
}
HTTP_OK='curl -sf -o /dev/null http://127.0.0.1:8765/teach.html && curl -sf -o /dev/null http://127.0.0.1:8765/index.html'
PULSE_OK='pactl list short sinks | grep -q tt_in && pactl list short sinks | grep -q tt_out'
{ for t in test_ask_core test_voice_adapter test_no_action_gate test_scope_guard test_workflow_validator test_click_stale_token; do echo "== $t"; python3 tests/$t.py 2>&1 | tail -3; done; } > $P/units.txt 2>&1
mkdir -p $P/stale; OUT=$P/stale python3 tests/test_interrupt_stale.py > $P/stale/stdout.txt 2>&1; if grep -a -q -E "FAIL|Traceback|pa_context_connect" $P/units.txt; then echo -e "units\tFAILED\t-\tFAIL/Traceback/pa error in units.txt" >> $ST; INCOMPLETE=1; else echo -e "units\tRAN\t0\tno FAIL/Traceback/pa error markers" >> $ST; fi
stage insert-neg tests/run_ask_insert_neg.sh
stage ask-virtual tests/run_ask_virtual.sh "$PULSE_OK"
stage ask-target tests/run_ask_target.sh "$PULSE_OK"
stage clean-exit tests/run_clean_exit.sh "$PULSE_OK"
stage ask-target-closed tests/run_ask_target_closed.sh
stage click-detect tests/run_click_detect.sh "$HTTP_OK"
stage click_validate tests/run_click_validate.sh "$HTTP_OK"
stage click_unrelated tests/run_click_unrelated.sh "$HTTP_OK"
stage click_guardlife tests/run_click_guardlife.sh "$HTTP_OK"
stage click_pause tests/run_click_pause.sh "$HTTP_OK"
{ Xvfb :97 -screen 0 1280x800x24 -noreset >/dev/null 2>&1 & XPID=$!; sleep 1.5; for t in test_clickdetect test_clickdetect_windows; do echo "== $t"; DISPLAY=:97 python3 tests/$t.py 2>&1 | grep -E "PASS|FAIL|INFO"; done; kill $XPID; } > $P/click-units.txt 2>&1; if grep -a -q -E "^FAIL |FAILS: \\[[^]]|Traceback" $P/click-units.txt || ! grep -a -q "PASS" $P/click-units.txt; then echo -e "click-units\tFAILED\t-\tFAIL/Traceback or no PASS in click-units.txt" >> $ST; INCOMPLETE=1; else echo -e "click-units\tRAN\t0\tno FAIL markers" >> $ST; fi
stage voice-real tests/run_voice_virtual_real.sh "$PULSE_OK"
pkill -INT -x ffmpeg; sleep 3; pkill -x Xvfb; pkill -x chrome; pkill dbus-daemon
for d in $P $P/*/; do [ -d $d ] && (cd $d && /home/sandbox/tiptour/linux/tools/run_manifest.sh . >/dev/null 2>&1); done
if [ -d $P/click_validate ] && [ -d $P/click_pause ] && [ -d $P/click_guardlife ] && [ -d $P/click_unrelated ]; then
  python3 tests/assert_click_stages.py $P > $P/semantic_assertions.txt 2>&1; arc=$?
  echo -e "semantic-click\t$([ $arc -eq 0 ] && echo ASSERTED || echo FAILED)\t$arc\tsee semantic_assertions.txt" >> $ST; [ $arc -ne 0 ] && INCOMPLETE=1
else echo -e "semantic-click\tSKIPPED\t-\tclick stage dirs missing" >> $ST; INCOMPLETE=1; fi
echo "FINISHED (runner ended; this is NOT a pass). INCOMPLETE=$INCOMPLETE. Read STAGES.tsv and each stage's artifacts." > $P/FINISHED
cat $ST