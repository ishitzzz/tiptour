#!/bin/bash
# REAL X11 clipboard-preservation and negative-insert test. Owned GTK entry only. No model, no key.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export ENTRY_DUMP=$O/entry.txt DISPLAY=:78 OUT=$O
Xvfb :78 -screen 0 1280x800x24 >/dev/null 2>&1 & XP=$!; sleep 1
dbus-launch xfwm4 >/dev/null 2>&1 & WP=$!; sleep 2
python3 tests/target_entry.py & TP=$!; sleep 1.5
xdotool search --name owned-entry-target | head -1 > $O/target_wid.txt
python3 tests/test_ask_insert_real.py > $O/stdout.txt 2>&1
kill $TP $WP $XP 2>/dev/null; cat $O/stdout.txt
