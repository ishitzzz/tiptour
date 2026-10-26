#!/bin/bash
# Modal gate (Mac WorkflowRunner :586 port). Virtual X11 + AT-SPI, GTK host app, FAKE model, point-only (--act OFF).
# Case A: no dialog -> must point at "Save". Case B: a modal dialog 'Unsaved changes' appears -> must refuse with "dialog appeared: <AT-SPI dialog name>" (GTK names this MessageDialog 'Warning') and render NO cursor.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"save":"Save"}' TIPTOUR_FAKE_APP=modal_app.py TIPTOUR_USE_CDP=0
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0 DISPLAY=:99 GTK_A11Y=atspi MODAL_AFTER_S=40 O
dbus-run-session -- bash -c '
Xvfb :99 -screen 0 1920x1080x24 >/dev/null 2>&1 & XP=$!; sleep 1
/usr/libexec/at-spi-bus-launcher --launch-immediately >/dev/null 2>&1 & sleep 1
python3 tests/modal_app.py >/dev/null 2>&1 & TP=$!; sleep 3
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
( sleep 20; echo "point save A" > $O/fifo; sleep 12; echo "$(nrender)" > $O/renders_after_A.txt
  sleep 25; echo "point save B" > $O/fifo; sleep 12; echo "$(nrender)" > $O/renders_after_B.txt; echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; kill $TP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "modal check|render cursor|refus|dialog appeared" $O/stdout.txt | cut -c1-220
A=$(cat $O/renders_after_A.txt); B=$(cat $O/renders_after_B.txt)
echo "ASSERT A pointed (renders after A >= 1): $([ "${A:-0}" -ge 1 ] && echo True || echo False)"
echo "ASSERT B no new cursor (renders unchanged): $([ "${B:-0}" = "${A:-x}" ] && echo True || echo False)"
echo "ASSERT B refused with dialog text: $(grep -a -q 'dialog appeared:' $O/stdout.txt $O/results.json 2>/dev/null && echo True || echo False)"
