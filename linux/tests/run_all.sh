#!/bin/bash
# Consolidated regression on the CURRENT tree. Writes STAGES.tsv (stage, status, exit, note). It NEVER prints overall success:
# FINISHED means only "the runner ended"; read STAGES.tsv. A stage that is missing/not executable, or whose preflight fails, is SKIPPED and makes the run INCOMPLETE.
# PINNED TREE + RESUME. Fresh run: copy the current tree to $P/pin/linux and run every stage from that copy (later edits to the working tree cannot change a run).
# Resume: RESUME=<existing run dir> reuses ITS pinned tree and STAGES.tsv; stages already RAN rc=0 (or ASSERTED) are not repeated; a RUNNING marker with a dead runner is recorded as ORPHANED and that stage dir is moved aside (kept) before rerun.
# Stages that may call a model (everything except the click stages) are NEVER rerun on resume unless ALLOW_MODEL_RERUN=1 (they are logged SKIPPED, INCOMPLETE).
SRC=/home/sandbox/tiptour/linux
exec 9>/tmp/tt-x99.lock; flock -n 9 || { echo "display lock /tmp/tt-x99.lock is held by another run; refusing before any mutation" >&2; exit 3; }
export TT_X99_OWNED=1
if [ -n "${RESUME:-}" ]; then P=$RESUME; [ -d $P/pin/linux ] || { echo "no pinned tree in $P" >&2; exit 2; }; RESUMING=1
else P=${RUN_DIR:?new unique parent dir}; [ -e $P ] && { echo exists; exit 2; }; mkdir -p $P/pin; tar --exclude=__pycache__ -cf - -C $(dirname $SRC) linux | tar -xf - -C $P/pin; RESUMING=0; fi
export TT_TREE=$P/pin/linux; cd $TT_TREE
. tests/clean_env.sh; [ $RESUMING = 0 ] && tools/snapshot_tree.sh $P
ST=$P/STAGES.tsv; [ $RESUMING = 0 ] && echo -e "stage\tstatus\texit\tnote" > $ST; INCOMPLETE=0
alive() { [ -r /proc/$1/status ] && ! grep -q "^State:.*Z" /proc/$1/status; }  # kill -0 is true for a zombie (nothing reaps orphans in this sandbox)
# orphan from an earlier runner that died (RUNNING holds "stage runner_pid stage_pgid")
if [ -f $P/RUNNING ]; then read ostage opid opg < $P/RUNNING
  if ! alive $opid; then
    [ -n "$opg" ] && kill -0 -- -$opg 2>/dev/null && kill -TERM -- -$opg 2>/dev/null
    echo -e "$ostage\tORPHANED\t-\trunner $opid died mid-stage; partial dir kept as $ostage.orphaned-$(date +%H%M%S)" >> $ST
    [ -d $P/$ostage ] && mv $P/$ostage $P/$ostage.orphaned-$(date +%H%M%S); rm -f $P/RUNNING; INCOMPLETE=1
  else echo "another runner ($opid) is live on $P; refusing" >&2; exit 3; fi; fi
CUR_PG=""; RUNNER=$$
cleanup() { [ -n "$CUR_PG" ] && kill -TERM -- -$CUR_PG 2>/dev/null; sleep 1; [ -n "$CUR_PG" ] && kill -KILL -- -$CUR_PG 2>/dev/null; rm -f $P/RUNNING; }
trap 'cleanup; echo "runner interrupted" > $P/INTERRUPTED; exit 143' TERM INT HUP
done_ok() { awk -F'\t' -v n=$1 '$1==n && (($2=="RAN" && $3==0) || $2=="ASSERTED"){f=1} END{exit !f}' $ST 2>/dev/null; }
MODEL_FREE=" click-detect click_validate click_unrelated click_guardlife click_pause "
export PYTHONPATH=.
stage() { # name script [preflight-cmd]
  local n=$1 sc=$2 pre=$3
  case " ${ONLY_STAGES:-} " in "  ") ;; *" $n "*) ;; *) return;; esac  # ONLY_STAGES="a b" runs just those
  if [ $RESUMING = 1 ] && done_ok $n; then echo "resume: $n already done, not repeated"; return; fi
  if [ $RESUMING = 1 ] && [ -d $P/$n ]; then
    case "$MODEL_FREE" in *" $n "*) ;; *) if [ "${ALLOW_MODEL_RERUN:-0}" != 1 ]; then echo -e "$n\tSKIPPED\t-\tresume: possible model stage not rerun (ALLOW_MODEL_RERUN=1 to override)" >> $ST; INCOMPLETE=1; return; fi;; esac
    local ts=$(date +%H%M%S); mv $P/$n $P/$n.superseded-$ts; echo "superseded by rerun at $ts; kept" > $P/$n.superseded-$ts/NOTE
  fi
  if [ ! -x "$sc" ]; then echo -e "$n\tSKIPPED\t-\tscript missing or not executable" >> $ST; INCOMPLETE=1; return; fi
  if [ -n "$pre" ] && ! eval "$pre" >/dev/null 2>&1; then echo -e "$n\tSKIPPED\t-\tpreflight failed: $pre" >> $ST; INCOMPLETE=1; return; fi
  pkill -x Xvfb; pkill -x chrome; pkill -x xfwm4; pkill dbus-daemon; sleep 2
  local tmo=""; [ "$n" = voice-real ] && tmo="timeout 330"
  RUN_DIR=$P/$n setsid $tmo $sc > $P/$n.txt 2>&1 9>&- < /dev/null & local spid=$!; CUR_PG=$spid
  echo "$n $RUNNER $spid" > $P/RUNNING
  # parent-liveness: if this runner is killed hard (no trap), the watchdog takes the stage's whole process group down with it
  ( while [ -r /proc/$RUNNER/status ] && ! grep -q "^State:.*Z" /proc/$RUNNER/status; do sleep 2; done; kill -TERM -- -$spid 2>/dev/null; sleep 2; kill -KILL -- -$spid 2>/dev/null ) 9>&- >/dev/null 2>&1 & local wd=$!
  wait $spid; local rc=$?; kill $wd 2>/dev/null; CUR_PG=""; rm -f $P/RUNNING
  local ex=$(cat $P/$n/app_exit.txt 2>/dev/null | tr -d '\n')
  [ $rc -ne 0 ] && INCOMPLETE=1
  local td=""; [ -f $P/$n/teardown.txt ] && td=" teardown.txt present"
  echo -e "$n\tRAN\t$rc\t${ex:-no app_exit.txt}$td" >> $ST
}
HTTP_OK='curl -sf -o /dev/null http://127.0.0.1:8765/teach.html && curl -sf -o /dev/null http://127.0.0.1:8765/index.html'
PULSE_OK='pactl list short sinks | grep -q tt_in && pactl list short sinks | grep -q tt_out'
if [ -z "${ONLY_STAGES:-}" ]; then
{ for t in test_ask_core test_voice_adapter test_no_action_gate test_scope_guard test_workflow_validator test_click_stale_token test_prompt_fidelity; do echo "== $t"; python3 tests/$t.py 2>&1 | tail -3; done; } > $P/units.txt 2>&1
mkdir -p $P/stale; OUT=$P/stale python3 tests/test_interrupt_stale.py > $P/stale/stdout.txt 2>&1; if grep -a -q -E "FAIL|Traceback|pa_context_connect" $P/units.txt; then echo -e "units\tFAILED\t-\tFAIL/Traceback/pa error in units.txt" >> $ST; INCOMPLETE=1; else echo -e "units\tRAN\t0\tno FAIL/Traceback/pa error markers" >> $ST; fi
fi
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
if [ -z "${ONLY_STAGES:-}" ]; then
{ Xvfb :97 -screen 0 1280x800x24 -noreset >/dev/null 2>&1 & XPID=$!; sleep 1.5; for t in test_clickdetect test_clickdetect_windows; do echo "== $t"; DISPLAY=:97 python3 tests/$t.py 2>&1 | grep -E "PASS|FAIL|INFO"; done; kill $XPID; } > $P/click-units.txt 2>&1; if grep -a -q -E "^FAIL |FAILS: \\[[^]]|Traceback" $P/click-units.txt || ! grep -a -q "PASS" $P/click-units.txt; then echo -e "click-units\tFAILED\t-\tFAIL/Traceback or no PASS in click-units.txt" >> $ST; INCOMPLETE=1; else echo -e "click-units\tRAN\t0\tno FAIL markers" >> $ST; fi
fi
stage voice-real tests/run_voice_virtual_real.sh "$PULSE_OK"
pkill -INT -x ffmpeg; sleep 3; pkill -x Xvfb; pkill -x chrome; pkill dbus-daemon
for d in $P $P/*/; do [ -d $d ] && (cd $d && $TT_TREE/tools/run_manifest.sh . >/dev/null 2>&1); done
if [ -d $P/click_validate ] && [ -d $P/click_pause ] && [ -d $P/click_guardlife ] && [ -d $P/click_unrelated ]; then
  python3 tests/assert_click_stages.py $P > $P/semantic_assertions.txt 2>&1; arc=$?
  echo -e "semantic-click\t$([ $arc -eq 0 ] && echo ASSERTED || echo FAILED)\t$arc\tsee semantic_assertions.txt" >> $ST; [ $arc -ne 0 ] && INCOMPLETE=1
else echo -e "semantic-click\tSKIPPED\t-\tclick stage dirs missing" >> $ST; INCOMPLETE=1; fi
echo "FINISHED (runner ended; this is NOT a pass). INCOMPLETE=$INCOMPLETE. Read STAGES.tsv and each stage's artifacts." > $P/FINISHED
cat $ST