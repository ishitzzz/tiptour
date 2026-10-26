#!/bin/bash
# REAL Gemini Live (original Live model, text turns), owned 5-step wizard, PAGE-AWARE harness v3. The harness is a user who FOLLOWS the pointer: it asks only for a control that is on the page now (except the one deliberate ask while step 2 is loading), and it clicks the rendered point ONLY when that point lies inside the oracle rect of the expected control (a wrong pointer = no click, recorded, one re-ask). It never clicks based on plan type. Moved-target edge: after step 3 renders, the harness waits for the control to move and then clicks the OLD point (blank owned page area) as a misclick before re-asking. Oracle = CDP rects (wizard_oracle.py). Per-ask timing lines are in stdout.txt (TIPTOUR_LOG_MS=1) and script_events.txt.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
KEYFILE=${KEYFILE:?path of the single key file}
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_LOG_MS=1 TIPTOUR_KEYS_GLOB=$KEYFILE TIPTOUR_DEBUG_LOG=1 TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0 REC_FPS=${REC_FPS:-30} WIZ_OFF=$O/wiz_off.json
if [ -n "$DRY" ]; then  # bounded dry-run of the PROCEDURE only: FAKE model (never counted as a Gemini result)
  export TIPTOUR_TEST_MODE=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests TIPTOUR_FAKE_TOOLCALL=1 TIPTOUR_FAKE_TRIGGER=point TIPTOUR_FAKE_TYPES=${FAKE_TYPES:-click} TIPTOUR_FAKE_STEPS='"'"'{"start order":"Start order","choose size":"Choose size","add toppings":"Add toppings","review order":"Review order","place test":"Place test order"}'"'"'
fi
export O
dbus-run-session -- bash -c '
EXPECT_IDS=s1 EXPECT_TITLE="Wizard Test" . tests/browser_env.sh http://localhost:8765/wizard.html $O
nrender() { grep -a -c "render cursor at" $O/stdout.txt; }
lastpx() { grep -a "render cursor at" $O/stdout.txt | tail -1 | sed -E "s/.*at \(([0-9]+), ([0-9]+)\).*/\1 \2/"; }
lasttype() { grep -a "toolCall args" $O/stdout.txt | tail -1 | grep -a -o "\"type\": \"[a-zA-Z]*\"" | tr "\n" "," ; }
now() { date +%T.%N | cut -c1-12; }
ev() { echo "$(now) $1" >> $O/script_events.txt; }
W() { python3 tests/wizard_oracle.py "$@"; }
pagelog() { W log; }
has() { pagelog | grep -c "\"$1\""; }
waitlog() { for i in $(seq ${2:-60}); do [ $(has "$1") -ge 1 ] && return 0; sleep 0.5; done; return 1; }
INSIDE=0
ask() { n=$(nrender); ev "ASK[$2] $1 | page: $(pagelog)"; echo "$1" > $O/fifo; for i in $(seq 120); do [ $(nrender) -gt $n ] && break; sleep 0.5; done
  if [ $(nrender) -gt $n ]; then sleep 3.5; P=$(lastpx); T=$(lasttype); R=$(W rect $2); ev "RENDER at $P plans=$T oracle_rect($2)=$R"
    INSIDE=$(python3 - "$P" "$R" <<PY
import sys,json
p=sys.argv[1].split(); r=json.loads(sys.argv[2]) if sys.argv[2] not in ("","null") else None
print(1 if r and len(p)==2 and r[0]<=int(p[0])<=r[0]+r[2] and r[1]<=int(p[1])<=r[1]+r[3] else 0)
PY
); ev "INSIDE expected control rect: $INSIDE"
  else P=""; INSIDE=0; ev "NO RENDER within 60s (model answered without pointing or stalled)"; fi; }
userclick() { if [ "$INSIDE" = 1 ]; then set -- $P; xdotool mousemove $1 $2; sleep 0.3; xdotool click 1; ev "USER CLICK at $1 $2 (inside expected rect)"; else ev "NO USER CLICK (pointer not on the expected control)"; fi; sleep 2; }
stepdone() { waitlog "step$1" 6 && ev "page reached step$1" && return 0; ev "page did NOT reach step$1: $(pagelog)"; return 1; }
( sleep 20; W calib >> $O/script_events.txt
  # step 1
  ask "Point to the Start order button." s1; userclick; stepdone 2 || { ask "Point to the Start order button." s1; userclick; stepdone 2; }
  # EDGE: deliberate ask while step 2 is still loading (control not on the page yet)
  ev "EDGE deliberate ask while step 2 loading"; ask "Point to the Choose size button." s2; ev "EDGE result: inside=$INSIDE (control absent => any render is a model/resolver guess)"
  [ -n "$P" ] && ev "EDGE render was NOT clicked"; waitlog "s2 shown late" 40; sleep 1
  ask "Point to the Choose size button." s2; userclick; stepdone 3 || { ask "Point to the Choose size button." s2; userclick; stepdone 3; }
  # step 3: ask right away, wait for the control to MOVE, misclick the old point, re-ask
  ask "Point to the Add toppings button." s3; waitlog "s3 moved" 30; sleep 1
  if [ -n "$P" ]; then set -- $P; xdotool mousemove $1 $2; sleep 0.3; xdotool click 1; ev "MISCLICK (stale point after the control moved) at $1 $2"; sleep 2; fi
  ev "page after misclick: $(pagelog)"; ask "Point to the Add toppings button." s3; userclick; stepdone 4 || { ask "Point to the Add toppings button." s3; userclick; stepdone 4; }
  # step 4: disabled decoy + the real enabled button
  ask "Point to the Review order button." s4; userclick; stepdone 5 || { ask "Point to the Review order button." s4; userclick; stepdone 5; }
  # step 5
  ask "Point to the Place test order button." s5; userclick; stepdone 6 || { ask "Point to the Place test order button." s5; userclick; stepdone 6; }
  ev "FINAL page: $(pagelog)"
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -X faulthandler -m tiptour_linux.app --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1; echo "app exit code $?" > $O/app_exit.txt
wait $SUB 2>/dev/null; pkill -INT -f "x11grab.*$O/recording" ; sleep 1; pkill -f "x11grab.*$O/recording"; kill $CP $XP 2>/dev/null; true' >/dev/null 2>&1
echo "== script events"; cat $O/script_events.txt
