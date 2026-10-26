#!/bin/bash
# Saved target app is NOT open: opening Ask must keep the saved preference, and Insert must fail closed (no fallback to another app). Real Xvfb+xfwm4, owned entry B only.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_MIC_SOURCE=tt_in.monitor TIPTOUR_VOSK_MODEL=/tmp/vosk-model/vosk-model-small-en-us-0.15 ENTRY_DUMP=$O/entryB.txt DISPLAY=:81 TIPTOUR_CONFIG_DIR=$O/cfg
mkdir -p $TIPTOUR_CONFIG_DIR; python3 -m tiptour_linux.settings set askTargetWmClass Closed_app.py > $O/events.txt
Xvfb :81 -screen 0 1280x800x24 >/dev/null 2>&1 & XP=$!; sleep 1
dbus-launch xfwm4 >/dev/null 2>&1 & WP=$!; sleep 2
python3 tests/target_entry.py & TB=$!; sleep 1.5
B=$(xdotool search --name owned-entry-target | head -1); xdotool windowfocus $B; xdotool mousemove 300 200 click 1; sleep .3
packaging/tiptour-linux ask > $O/stdout.txt 2>&1 & AP=$!; sleep 3
xdotool keydown ctrl keydown alt keydown shift; sleep .4; paplay -d tt_in /tmp/speech/q_point.wav; sleep .6; xdotool keyup shift keyup alt keyup ctrl; sleep 6
PW=$(xdotool search --name 'TipTour Ask preview' | head -1); xdotool windowmove $PW 20 20; sleep .5
eval $(xwininfo -id $PW | awk '/Absolute upper-left X/{print "X="$4} /Absolute upper-left Y/{print "Y="$4} /Width:/{print "WIDTH="$2} /Height:/{print "HEIGHT="$2}'); BY=$((Y+HEIGHT-21))
import -window root $O/preview_closed.png
echo "settings after opening preview: $(tr -d '\n ' < $TIPTOUR_CONFIG_DIR/settings.json)" >> $O/events.txt
xdotool mousemove $((X+5*WIDTH/8)) $BY click 1; sleep 2; import -window root $O/insert_refused.png
echo "entry (must stay empty): [$(cat $O/entryB.txt)]" >> $O/events.txt
echo "settings after refused insert: $(tr -d '\n ' < $TIPTOUR_CONFIG_DIR/settings.json)" >> $O/events.txt
kill $AP $TB $WP $XP 2>/dev/null
