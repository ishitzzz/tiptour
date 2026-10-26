#!/bin/bash
# Ask target chooser, real X11 (Xvfb+xfwm4): focus window B at press, preview preset to insert into app A's WM_CLASS (via settings file; the combo click itself is NOT driven).
cd /home/sandbox/tiptour/linux
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_MIC_SOURCE=tt_in.monitor TIPTOUR_VOSK_MODEL=/tmp/vosk-model/vosk-model-small-en-us-0.15 ENTRY_DUMP=$O/entryA.txt ENTRY_DUMP_B=$O/entryB.txt DISPLAY=:79
export TIPTOUR_CONFIG_DIR=$O/cfg; mkdir -p $TIPTOUR_CONFIG_DIR
Xvfb :79 -screen 0 1280x800x24 >/dev/null 2>&1 & XP=$!; sleep 1
dbus-launch xfwm4 >/dev/null 2>&1 & WP=$!; sleep 2
python3 tests/target_entry.py & TA=$!; sleep 1.2
python3 tests/target_entry2.py & TB=$!; sleep 1.5
A=$(xdotool search --name owned-entry-target | head -1); B=$(xdotool search --name owned-entry-B | head -1)
xdotool windowmove $A 700 50; xdotool windowmove $B 700 300; sleep .5
CLS=$(xprop -id $A WM_CLASS | sed 's/.*= //; s/"//g; s/.*, //'); echo "A=$A B=$B class_of_A=$CLS class_of_B=$(xprop -id $B WM_CLASS | sed 's/.*, //; s/"//g')" > $O/events.txt
echo "no preset: the combo is driven by click+keys" >> $O/events.txt
xdotool windowfocus $B; xdotool mousemove 800 380 click 1; sleep .3
packaging/tiptour-linux ask > $O/stdout.txt 2>&1 & AP=$!; sleep 3
echo "active at press: $(xdotool getactivewindow) (B=$B)" >> $O/events.txt
xdotool keydown ctrl keydown alt keydown shift; sleep .4; paplay -d tt_in /tmp/speech/q_point.wav; sleep .6; xdotool keyup shift keyup alt keyup ctrl; sleep 6
PW=$(xdotool search --name 'TipTour Ask preview' | head -1); xdotool windowmove $PW 20 20; sleep .5
eval $(xwininfo -id $PW | awk '/Absolute upper-left X/{print "X="$4} /Absolute upper-left Y/{print "Y="$4} /Width:/{print "WIDTH="$2} /Height:/{print "HEIGHT="$2}'); BY=$((Y+HEIGHT-21))
import -window root $O/preview_chooser.png
CY=$((BY-40)); xdotool mousemove $((X+WIDTH/2)) $CY click 1; sleep .8; import -window root $O/combo_open.png
xdotool key Down; sleep .3; xdotool key Return; sleep .8; import -window root $O/combo_selected.png
echo "settings after combo: $(cat $TIPTOUR_CONFIG_DIR/settings.json | tr -d '\n ')" >> $O/events.txt
xdotool mousemove $((X+5*WIDTH/8)) $BY click 1; sleep 2; import -window root $O/after_insert_A.png
echo "entry A: [$(cat $O/entryA.txt)]  entry B: [$(cat $O/entryB.txt)]" >> $O/events.txt
# ambiguity: second window of A's class -> must refuse
python3 tests/target_entry.py & TA2=$!; sleep 1.5
xdotool mousemove $((X+5*WIDTH/8)) $BY click 1; sleep 2; import -window root $O/ambiguous_refused.png
echo "after 2nd window of class A: entry A: [$(cat $O/entryA.txt)] entry B: [$(cat $O/entryB.txt)]" >> $O/events.txt
kill $AP $TA $TB $TA2 $WP $XP 2>/dev/null
