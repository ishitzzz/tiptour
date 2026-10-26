#!/bin/bash
# REAL Gemini Live model (free-tier key from the tiptour-linux project only), owned page in real Chrome on virtual X11, real YOLO/OCR/AT-SPI, point-only (--act OFF), TEXT turns typed through the serve FIFO (no real mic/speech).
# Turn 1 asks to point at a control; turn 2 refers back to turn 1 ("the same control you just pointed to") to observe context continuity within ONE live session. Model output is nondeterministic: results are RECORDED, only the oracle comparison is computed.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
KEYFILE=${KEYFILE:?path of the single key file}
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_KEYS_GLOB=$KEYFILE TIPTOUR_DEBUG_LOG=1 TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
waitr() { n=$1; for i in $(seq 60); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
( sleep 25
  n=$(nrender); echo "Point to the Open settings button." > $O/fifo; sleep 25; echo "$(nrender)" > $O/r1.txt
  echo "Point to the same control you just pointed to, again." > $O/fifo; sleep 25; echo "$(nrender)" > $O/r2.txt
  TIPTOUR_USE_CDP=1 python3 - > $O/oracle_rect.json <<PY
import json,subprocess
from tiptour_linux import cdp_resolver
g=subprocess.run(["xdotool","getdisplaygeometry"],capture_output=True,text=True).stdout.split(); size=(int(g[0]),int(g[1]))
st,h=cdp_resolver.resolve_ex("Open settings", size); print(json.dumps({"status":st,"rect":h[0]["rect"] if h else None}))
PY
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording" ; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log (no keys are logged by the app; scan below)"; grep -a -E "render cursor|refus|session|reconnect|closed|error|Error|turn" $O/stdout.txt | cut -c1-200 | head -40
echo "renders after turn1: $(cat $O/r1.txt) after turn2: $(cat $O/r2.txt)"
python3 - <<PY
import json,re
O="$O"; L=[tuple(map(int,m)) for m in re.findall(r"render cursor at \((\d+), (\d+)\)", open(O+"/stdout.txt",errors="ignore").read())]
o=json.load(open(O+"/oracle_rect.json")); r=o.get("rect"); print("oracle",o,"renders",L)
inr=lambda p: bool(r) and r[0]<=p[0]<=r[0]+r[2] and r[1]<=p[1]<=r[1]+r[3]
print("RESULT per render inside oracle rect:", [inr(p) for p in L])
PY
