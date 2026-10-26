#!/bin/bash
# Real fresh Chrome on Xvfb, owned fixtures only, NO app, NO model. Exercises the page preflight: 1 positive + 3 negative (error page, wrong page/title, required control missing).
cd /home/sandbox/tiptour/linux
B=${RUN_DIR:?base dir}; [ -e $B ] && { echo exists; exit 2; }; mkdir -p $B
run() { # name url title ids expected_rc
  local O=$B/$1; mkdir -p $O
  RUN_O=$O RUN_URL=$2 RUN_TITLE=$3 RUN_IDS=$4 PF_OPEN_EXTRA=$6 TT_X99_OWNED=1 dbus-run-session -- bash -c '
    export O=$RUN_O; . tests/clean_env.sh
    EXPECT_IDS=$RUN_IDS EXPECT_TITLE=$RUN_TITLE . tests/browser_env.sh $RUN_URL $O
    echo reached_after_preflight > $O/REACHED; pkill -INT -x ffmpeg; sleep 1; pkill -x chrome; pkill -x xfwm4; kill $XP; true' > $O/out.txt 2>&1
  local got=PASS_THROUGH; [ -f $O/PAGE_PREFLIGHT_FAILED ] && got=STOPPED
  echo "$1 expected=$5 got=$got why=$(python3 -c "import json;d=json.load(open('$O/page_preflight.json'));print(d.get('why'),d.get('seen'))" 2>&1 | cut -c1-200)" | tee -a $B/RESULTS.txt
  pkill -x ffmpeg; sleep 3; pkill -x Xvfb; sleep 1
}
run pos http://localhost:8765/teach.html "Teach Test" open,noop PASS_THROUGH
run neg_error_page http://localhost:8999/teach.html "Teach Test" open,noop STOPPED
run neg_wrong_page http://localhost:8765/index.html "Teach Test" open,noop STOPPED
run neg_wrong_tab http://localhost:8765/teach.html "Teach Test" open,noop STOPPED http://localhost:8765/index.html
run neg_missing_control http://localhost:8765/teach.html "Teach Test" open,nonexistent_ctl STOPPED
