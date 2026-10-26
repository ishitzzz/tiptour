cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
export GI_TYPELIB_PATH=$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0
dbus-run-session -- bash -c '
. tests/browser_env.sh http://localhost:8765/index.html /tmp/ptt
sleep 6
H=$(xdotool getwindowpid $(xdotool search --onlyvisible --class chrome | head -1)); echo hint=$H
for i in 1 2 3 4 5 6; do python3 -m tiptour_linux.atspi_resolver --probe "[150,380,290,50]" $H 5 2>&1 | cut -c1-200; sleep 5; done
time python3 -m tiptour_linux.atspi_resolver --probe "[150,380,290,50]" $H 5 2>&1 | cut -c1-300
kill $FP $CP $XP' > /tmp/dbgsub.out 2>&1
