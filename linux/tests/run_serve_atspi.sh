cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
export TIPTOUR_DEBUG_ATSPI=1 ACCESSIBILITY_ENABLED=1 TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
export TIPTOUR_KEYS_GLOB='/home/sandbox/.vault/gemini-*/password'
dbus-run-session -- bash -c '
O=/tmp/sv4; mkdir -p $O; rm -f $O/fifo
. tests/browser_env.sh http://localhost:8765/index.html $O
( sleep 10; xdotool mousemove 150 376; xdotool keydown ctrl keydown shift
  for p in "250 376" "350 380" "440 390" "440 430" "350 432" "250 430" "150 428" "150 390"; do xdotool mousemove $p; sleep 0.2; done
  xdotool keyup shift keyup ctrl
  sleep 30; echo "Point to the highlighted field." > $O/fifo
  sleep 16; echo "@quit" > $O/fifo ) &
SUB=$!
python3 -m tiptour_linux.app --highlight --serve $O/fifo --hold 2 --out $O > $O/stdout.txt 2>&1
wait $SUB 2>/dev/null; kill $FP $CP $XP' 2>&1 | grep -v -E "dbus-daemon|xfconf|bus can|x11grab|:99|keyring|prompter|Warning"
grep -E "accessibility|region" /tmp/sv4/highlight-prompt-0.txt
