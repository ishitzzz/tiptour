#!/bin/bash
# Retry / Resume = re-capture + rerun the full resolver cascade for the active step (Mac retryCurrentStep()/resume()). Owned page, real Chrome + AT-SPI + real YOLO/OCR, FAKE model, point-only.
# 1) "point open" -> pointed. 2) @resume while NOT paused -> refused. 3) @retry -> fresh capture + full cascade -> a SECOND render at the same control; the model got no second tool_response.
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
waitr() { n=$1; for i in $(seq 80); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
( sleep 25
  n=$(nrender); echo "point open" > $O/fifo; waitr $n; echo $(nrender) > $O/r1.txt
  echo "@resume" > $O/fifo; sleep 4; echo $(nrender) > $O/r_after_resume.txt
  echo "@retry" > $O/fifo; waitr $(nrender); echo $(nrender) > $O/r_after_retry.txt
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -x ffmpeg; sleep 1; pkill -x ffmpeg; pkill -x chrome; pkill -x xfwm4; kill $XP; true' >/dev/null 2>&1
echo "== log"; grep -a -E "render cursor|control |refus" $O/stdout.txt | cut -c1-200
R1=$(cat $O/r1.txt); RR=$(cat $O/r_after_resume.txt); RT=$(cat $O/r_after_retry.txt)
echo "ASSERT 1 pointed: $([ "${R1:-0}" -ge 1 ] && echo True || echo False)"
echo "ASSERT 2 resume refused when not paused, no new render: $([ "$RR" = "$R1" ] && grep -a -q 'control resume refused: not paused' $O/stdout.txt && echo True || echo False)"
echo "ASSERT 3 retry re-resolved from a fresh capture, new render: $([ "${RT:-0}" -gt "${R1:-0}" ] && grep -a -q 'control retry: re-resolved the active step from a fresh capture' $O/stdout.txt && echo True || echo False)"
echo "ASSERT 4 fresh perception ran again on retry (2 perception passes total): $([ "$(grep -a -c "perception:" $O/stdout.txt)" = 2 ] && echo True || echo False)"
echo "NOTE: whether the model received a 2nd tool_response is NOT asserted here (fake client does not log it); replay code path has no client call by construction"
