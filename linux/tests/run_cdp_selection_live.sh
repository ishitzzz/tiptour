#!/bin/bash
# needs the owned controls page served: (cd /tmp/ctl && python3 -m http.server 8765 &)
cd "$(dirname "$0")/.."
dbus-run-session -- bash -c 'O=/tmp/cdpsel-$(date +%H%M%S); . tests/browser_env.sh http://localhost:8765/index.html $O; sleep 4; python3 tests/test_cdp_selection_live.py; rc=$?; kill $FP $CP $XP 2>/dev/null; exit $rc'
