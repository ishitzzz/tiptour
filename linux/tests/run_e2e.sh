#!/bin/bash
# Real Linux (virtual X11 via Xvfb + AT-SPI bus): real Gemini Live, real screenshots, real overlay.
# Usage: VERIFY="Save Cancel" tests/run_e2e.sh --ask "..." --ask "..."   (TIPTOUR_USE_ATSPI=0 for model-only)
cd "$(dirname "$0")/../.."
rm -rf "${OUT:-/tmp/tiptour-run}"
: "${TIPTOUR_KEYS_GLOB:?set TIPTOUR_KEYS_GLOB to a glob of files, one Gemini API key per file}"; export TIPTOUR_KEYS_GLOB
export TIPTOUR_GIR_PATH=${TIPTOUR_GIR_PATH:-/home/sandbox/atspi-root/usr/lib/x86_64-linux-gnu/girepository-1.0}
export DISPLAY=:99 OUT=${OUT:-/tmp/tiptour-run} GTK_A11Y=atspi
export TARGET SEED
dbus-run-session -- bash -c '
Xvfb :99 -screen 0 1920x1080x24 >/dev/null 2>&1 & XP=$!; sleep 1
/usr/libexec/at-spi-bus-launcher --launch-immediately >/dev/null 2>&1 &
sleep 1
python3 linux/tests/${TARGET:-target_app.py} $SEED >/dev/null 2>&1 & TP=$!; sleep 3
(cd linux && python3 -m tiptour_linux.app --out "$OUT" "$@")
cp /tmp/target-rects.json "$OUT/rects.json"; cd linux; python3 tests/verify.py "$OUT" ${VERIFY:-Save}; RC=$?
kill $TP $XP 2>/dev/null; exit $RC' _ "$@" 2>&1 | grep -v -E 'dbus-daemon|Warning|from gi.repo'
