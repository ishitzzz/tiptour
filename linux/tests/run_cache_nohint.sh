#!/bin/bash
# Local-perception CACHE resolution through the real app: owned page, real Chrome + real YOLO/OCR on a real screenshot, fake model (canned toolcall with a step WITHOUT any point_2d/box_2d (label only: Mac tier 3)), AT-SPI and CDP resolvers DISABLED so only
# the cache/refine path can bind the label. Oracle for "points at the right control": the CDP resolver's screen rect for the same label (independent of the cache). Point-only, --act OFF. NOT a real-model test.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_STEPS='{"open":"Open settings"}' TIPTOUR_USE_ATSPI=0 TIPTOUR_USE_CDP=0 TIPTOUR_FAKE_NOPOINT=1
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
lastpx() { grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/"; }
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
( sleep 25
  n=$(nrender); echo "point open" > $O/fifo; for i in $(seq 80); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2
  echo "$(lastpx)" > $O/render_px.txt
  TIPTOUR_USE_CDP=1 python3 - > $O/oracle_rect.json <<PY
import json,subprocess
from tiptour_linux import cdp_resolver
g=subprocess.run(["xdotool","getdisplaygeometry"],capture_output=True,text=True).stdout.split(); size=(int(g[0]),int(g[1]))
st,h=cdp_resolver.resolve_ex("Open settings", size); print(json.dumps({"status":st,"rect":h[0]["rect"] if h else None}))
PY
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -x ffmpeg; sleep 1; pkill -x ffmpeg; pkill -x chrome; pkill -x xfwm4; kill $XP; true' >/dev/null 2>&1
echo "== app log"; grep -a -E "perception:|render cursor|target_cache|refus" $O/stdout.txt | cut -c1-200
echo "== render px"; cat $O/render_px.txt; echo "== oracle"; cat $O/oracle_rect.json
python3 - <<PY
import json
px=open("$O/render_px.txt").read().split(); o=json.load(open("$O/oracle_rect.json")); log=open("$O/stdout.txt",errors="ignore").read()
ok=False
if len(px)==2 and o.get("rect"):
    x,y=map(int,px); r=o["rect"]; ok = r[0]<=x<=r[0]+r[2] and r[1]<=y<=r[1]+r[3]
print("ASSERT point inside oracle control rect:", ok); print("ASSERT src=target_cache TIER 3 (label only, no model point) used:", "src target_cache:ocr" in log or "src target_cache:yolo" in log)
PY
