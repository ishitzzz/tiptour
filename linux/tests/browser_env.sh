#!/bin/bash
# Source-able: starts Xvfb :99, a fresh real Chrome (new profile, CDP on 9222) on a public URL, and an ffmpeg recording.
# usage: . browser_env.sh URL OUTDIR
# one run at a time on :99/9222: hold a lock for this shell's lifetime; refuse (do NOT touch the other run's X server) if busy
[ "${TT_X99_OWNED:-0}" = 1 ] || { exec 9>/tmp/tt-x99.lock; flock -n 9; } || { echo "display :99 busy (another run holds /tmp/tt-x99.lock); refusing to start" >&2; exit 3; }
URL=$1; OUTDIR=$2; mkdir -p "$OUTDIR"; rm -f /tmp/.X99-lock /tmp/.X11-unix/X99; rm -rf /tmp/chrome-prof
export DISPLAY=:99 GTK_A11Y=atspi ACCESSIBILITY_ENABLED=1
Xvfb :99 -screen 0 1920x1080x24 >/dev/null 2>&1 9>&- & XP=$!; sleep 1
[ "${WM:-1}" = 1 ] && { xfwm4 --compositor=off >/dev/null 2>&1 9>&- & sleep 2; }
/usr/libexec/at-spi-bus-launcher --launch-immediately >/dev/null 2>&1 9>&- &
sleep 1
google-chrome --no-sandbox --disable-gpu --user-data-dir=/tmp/chrome-prof --no-first-run --no-default-browser-check \
  --remote-debugging-port=9222 --window-position=${POS:-0,0} --window-size=${WIN:-1600,1000} --force-renderer-accessibility "$URL" >/dev/null 2>&1 9>&- & CP=$!
ffmpeg -loglevel error -y -f x11grab -framerate ${REC_FPS:-5} -video_size 1920x1080 -i :99 -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$OUTDIR/recording.mp4" 9>&- & FP=$!
sleep 8
[ -n "${PF_OPEN_EXTRA:-}" ] && { curl -s -X PUT "http://127.0.0.1:9222/json/new?$PF_OPEN_EXTRA" >/dev/null; sleep 2; }  # test hook: negative preflight (second/wrong tab)
# optional: EXPECT_URL / EXPECT_TITLE -> verify the REAL loaded page before any test runs; stop the stage on mismatch (no model_box fallback going green)
if [ -n "${EXPECT_TITLE:-}" ]; then python3 tests/page_preflight.py "$OUTDIR" "${EXPECT_URL:-http://localhost:8765/}" "$EXPECT_TITLE" 25 "${EXPECT_IDS:-}" || { echo "PAGE PREFLIGHT FAILED" > "$OUTDIR/PAGE_PREFLIGHT_FAILED"; pkill -x chrome; pkill -x Xvfb; exit 4; }; fi
