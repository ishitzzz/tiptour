#!/bin/bash
# Retry after the target MOVED: owned GTK app, real AT-SPI/YOLO/OCR on virtual X11, FAKE model, point-only (--act OFF).
# Oracle: the app itself writes its button's absolute screen rect. Proves the retry re-resolved from a FRESH capture (cursor follows the moved control), not identical stale coords.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"save":"Save"}' TIPTOUR_FAKE_APP=move_app.py TIPTOUR_USE_CDP=0
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0 DISPLAY=:99 GTK_A11Y=atspi
export ORACLE_FILE=$O/oracle.json MOVE_FLAG=$O/move.flag O
dbus-run-session -- bash -c '
Xvfb :99 -screen 0 1920x1080x24 >/dev/null 2>&1 & XP=$!; sleep 1
/usr/libexec/at-spi-bus-launcher --launch-immediately >/dev/null 2>&1 & sleep 1
python3 tests/move_app.py >/dev/null 2>&1 & TP=$!; sleep 3
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
waitr() { n=$1; for i in $(seq 60); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 1; }
( sleep 20; n=$(nrender); echo "point save" > $O/fifo; waitr $n; cp $O/oracle.json $O/oracle_before.json
  import_png() { python3 -c "import subprocess;subprocess.run([\"import\",\"-window\",\"root\",\"$1\"])" 2>/dev/null; }
  import_png $O/shot_before.png
  touch $MOVE_FLAG; sleep 2; cp $O/oracle.json $O/oracle_after_move.json
  n=$(nrender); echo "@retry" > $O/fifo; waitr $n; import_png $O/shot_after_retry.png
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; kill $TP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "render cursor|control |refus" $O/stdout.txt | cut -c1-200
python3 - <<PY
import json,re
O="$O"; L=[tuple(map(int,m)) for m in re.findall(r"render cursor at \((\d+), (\d+)\)", open(O+"/stdout.txt",errors="ignore").read())]
b=json.load(open(O+"/oracle_before.json")); a=json.load(open(O+"/oracle_after_move.json")); print("oracle before",b,"after",a,"renders",L)
inr=lambda p,r: r[0]<=p[0]<=r[0]+r[2] and r[1]<=p[1]<=r[1]+r[3]
print("ASSERT oracle says the button really moved:", (not b["moved"]) and a["moved"] and b["rect"]!=a["rect"])
print("ASSERT first render inside the ORIGINAL rect:", len(L)>=1 and inr(L[0],b["rect"]))
print("ASSERT retry render inside the MOVED rect (and not the old one):", len(L)>=2 and inr(L[-1],a["rect"]) and not inr(L[-1],b["rect"]))
PY
