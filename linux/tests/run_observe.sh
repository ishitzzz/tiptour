#!/bin/bash
# Mac WorkflowRunner.swift:913-921 observe parity: a labelled .observe step DISARMS the click detector, points, and after 650ms auto-advances (never waits for a click). Owned page, real Chrome + AT-SPI + YOLO/OCR, FAKE model, plan of 2 observe steps. Asserts: both steps render in their own CDP-oracle rects, no click armed, plan completes, step-1 -> step-2 render gap < 3.5s.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_DEBUG_LOG=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1
export TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_TYPES=observe,observe TIPTOUR_FAKE_STEPS='{"open":["Open settings","No-op action"]}'
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export O TIPTOUR_LOG_MS=1
dbus-run-session -- bash -c '
EXPECT_IDS=open,noop EXPECT_TITLE="Teach Test" . tests/browser_env.sh http://localhost:8765/teach.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
waitr() { n=$1; for i in $(seq 80); do [ $(nrender) -gt $n ] && break; sleep 0.5; done; sleep 2; }
( sleep 25
  echo "point open" > $O/fifo; waitr 0; echo $(nrender) > $O/r1.txt
  sleep 5; echo $(nrender) > $O/r2.txt; echo $(nrender) > $O/r3.txt
  TIPTOUR_USE_CDP=1 python3 - > $O/oracle_rects.json <<PY
import json,subprocess
from tiptour_linux import cdp_resolver
g=subprocess.run(["xdotool","getdisplaygeometry"],capture_output=True,text=True).stdout.split(); size=(int(g[0]),int(g[1]))
o={}
for lab in ("Open settings","No-op action"):
    st,h=cdp_resolver.resolve_ex(lab, size); o[lab]=h[0]["rect"] if h else None
print(json.dumps(o))
PY
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording" ; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== log"; grep -a -E "render cursor|control |advance|refus" $O/stdout.txt | cut -c1-200
python3 - <<PY
import json,re
O="$O"; L=[tuple(map(int,m)) for m in re.findall(r"render cursor at \((\d+), (\d+)\)", open(O+"/stdout.txt",errors="ignore").read())]; o=json.load(open(O+"/oracle_rects.json")); log=open(O+"/stdout.txt",errors="ignore").read()
inr=lambda p,r: bool(r) and r[0]<=p[0]<=r[0]+r[2] and r[1]<=p[1]<=r[1]+r[3]
r=[int(open(O+"/r%d.txt"%i).read() or 0) for i in (1,2,3)]
print("renders",L,"counts",r,"oracle",o)
import datetime
ts=[l.split()[0] for l in log.splitlines() if "render cursor at" in l]
def sec(s): h,m,r=s.split(":"); return int(h)*3600+int(m)*60+float(r)
gap=sec(ts[1])-sec(ts[0]) if len(ts)>=2 else 99
print("render gap step1->step2 (s):", round(gap,3))
print("ASSERT 3 observe auto-advance does not wait for the whole live turn: step 2 renders within 3.5s of step 1 (650ms + fresh capture/perception/resolve), not ~6s:", gap < 3.5)
ce=open(O+"/click_events.json").read()
print("ASSERT 1 observe plan [Open settings, No-op action]: step1 rendered in its rect, then WITHOUT any click ~650ms later step 2 rendered in the No-op rect:", len(L)==2 and inr(L[0],o["Open settings"]) and inr(L[1],o["No-op action"]) and "observe step pointed; advancing after 650ms" in log)
print("ASSERT 2 no click detector armed for observe steps (two observe events, no target_clicked/pointer_guard), and the plan completes after the last step:", ce.count("pointed_no_arm")==2 and "target_clicked" not in ce and "pointer_guard" not in ce and "no next step, plan complete" in log)
PY
