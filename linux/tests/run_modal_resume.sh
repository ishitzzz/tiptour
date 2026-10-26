#!/bin/bash
# Resume after a MODAL pause (Mac: modalDialogPresented -> resume() re-resolves once the dialog is gone). GTK host, virtual X11 + AT-SPI, FAKE model, point-only.
# t0 point save (no dialog) -> render. Dialog opens. @retry while open -> refused by modal gate, no render, pause recorded. @resume while open -> allowed (paused) but gate refuses again, no render. Dialog closes. @resume -> re-resolves, renders.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"save":"Save"}' TIPTOUR_FAKE_APP=modal_app.py TIPTOUR_USE_CDP=0
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0 DISPLAY=:99 GTK_A11Y=atspi MODAL_AFTER_S=48 MODAL_CLOSE_S=26 O
dbus-run-session -- bash -c '
Xvfb :99 -screen 0 1920x1080x24 >/dev/null 2>&1 & XP=$!; sleep 1
/usr/libexec/at-spi-bus-launcher --launch-immediately >/dev/null 2>&1 & sleep 1
python3 tests/modal_app.py >/dev/null 2>&1 & TP=$!; sleep 3
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
mark() { echo "$(date +%T) $1 renders=$(nrender)" >> $O/timeline.txt; }
( sleep 20; echo "point save" > $O/fifo; sleep 12; mark after_point
  sleep 18; mark dialog_should_be_open; echo "@retry" > $O/fifo; sleep 5; mark after_retry_open
  echo "@resume" > $O/fifo; sleep 5; mark after_resume_open
  sleep 22; mark dialog_should_be_closed; echo "@resume" > $O/fifo; sleep 10; mark after_resume_closed
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; kill $TP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "modal check|render cursor|control |refus|dialog appeared" $O/stdout.txt | cut -c1-200; echo "== timeline"; cat $O/timeline.txt
python3 - <<PY
import re
O="$O"; T=[l.split() for l in open(O+"/timeline.txt")]; n={x[1]:int(x[2].split("=")[1]) for x in T}; log=open(O+"/stdout.txt",errors="ignore").read()
print("ASSERT 1 pointed before dialog:", n["after_point"]>=1)
print("ASSERT 2 @retry with dialog open: no new render, modal gate hit:", n["after_retry_open"]==n["after_point"] and log.count("dialog present")>=2)
print("ASSERT 3 @resume with dialog open is ACCEPTED as paused (not refused 'not paused'), no render:", "control resume refused: not paused" not in log and n["after_resume_open"]==n["after_point"] and "control resume: re-resolved" in log)
print("ASSERT 4 @resume after dialog closed re-resolves and renders:", n["after_resume_closed"]>n["after_resume_open"])
PY
