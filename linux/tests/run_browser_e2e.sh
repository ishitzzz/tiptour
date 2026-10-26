#!/bin/bash
# Real Chrome (fresh profile) on a public page inside the Xvfb desktop + real Gemini Live + recording.
# usage: URL=... VERIFY="search login diagram" tests/run_browser_e2e.sh --ask ... (needs TIPTOUR_KEYS_GLOB)
: "${TIPTOUR_KEYS_GLOB:?set TIPTOUR_KEYS_GLOB}"; export TIPTOUR_KEYS_GLOB
export TIPTOUR_GIR_PATH=${TIPTOUR_GIR_PATH:-$HOME/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0}
export OUT=${OUT:-/tmp/brun} URL=${URL:-https://en.wikipedia.org/wiki/Neural_network_(machine_learning)}
cd "$(dirname "$0")/.."; HERE=$(pwd)
dbus-run-session -- bash -c '
. tests/browser_env.sh "$URL" "$OUT"
python3 -m tiptour_linux.app --out "$OUT" "$@"
kill $FP 2>/dev/null; wait $FP 2>/dev/null
python3 tests/verify_browser.py "$OUT" $VERIFY; RC=$?
kill $CP $XP 2>/dev/null; exit $RC' _ "$@" 2>&1 | grep -v -E 'dbus-daemon|ERROR|Warning|from gi.repo|xfconf|bus'
