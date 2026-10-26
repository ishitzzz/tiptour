cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
export LOAD=${LOAD:-0} GI_TYPELIB_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0 ACCESSIBILITY_ENABLED=1 GTK_A11Y=${GA:-atspi} TIPTOUR_GIR_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
dbus-run-session -- bash -c '
. tests/browser_env.sh http://localhost:8765/index.html /tmp/ptt
sleep 3
timeout 80 python3 /tmp/probe_thread_test.py > /tmp/ptt-out.txt 2>&1
kill $FP $CP $XP' >/dev/null 2>&1
