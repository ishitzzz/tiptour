#!/bin/bash
# Ask harness real-X11 test: virtual mic (tt_in) + synthetic speech, owned GTK entry as the insert target. NOT a physical mic/keyboard.
cd /home/sandbox/tiptour/linux
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_MIC_SOURCE=tt_in.monitor TIPTOUR_VOSK_MODEL=/tmp/vosk-model/vosk-model-small-en-us-0.15 ENTRY_DUMP=$O/entry.txt DISPLAY=:77
Xvfb :77 -screen 0 1280x800x24 >/dev/null 2>&1 & XP=$!; sleep 1
dbus-launch xfwm4 >/dev/null 2>&1 & WP=$!; sleep 2
python3 tests/target_entry.py & TP=$!; sleep 1.5
xdotool search --name owned-entry-target | head -1 > $O/target_wid.txt
xdotool windowfocus $(cat $O/target_wid.txt); xdotool mousemove 300 200 click 1; sleep .3
packaging/tiptour-linux ask > $O/stdout.txt 2>&1 & AP=$!; sleep 3
echo "active at press: $(xdotool getactivewindow) target: $(cat $O/target_wid.txt)" > $O/events.txt
xdotool keydown ctrl keydown alt keydown shift; sleep .4
paplay -d tt_in ${WAV:-/tmp/speech/q_quote.wav}; sleep .6
xdotool keyup shift keyup alt keyup ctrl; sleep 6
import -window root $O/preview.png 2>/dev/null || python3 -c "from PIL import ImageGrab;ImageGrab.grab().save('$O/preview.png')"
echo "windows: $(xdotool search --name 'TipTour Ask preview' | head -1)" >> $O/events.txt
# click buttons by position found via xdotool geometry
PW=$(xdotool search --name 'TipTour Ask preview' | head -1)
eval $(xwininfo -id $PW | awk '/Absolute upper-left X/{print "AX="$4} /Absolute upper-left Y/{print "AY="$4} /Width:/{print "WIDTH="$2} /Height:/{print "HEIGHT="$2}'); X=$AX; Y=$AY; echo "preview abs $X,$Y ${WIDTH}x${HEIGHT}" >> $O/events.txt
BY=$((Y+HEIGHT-21))
# GTK-path negatives. (a) multi-format previous clipboard (html+text owner): Copy text must refuse before overwriting
python3 tests/clip_multi_holder.py & HP=$!; sleep 1.5
xdotool mousemove $((X+WIDTH/8)) $BY click 1; sleep .8; import -window root $O/gtk_multi_refused.png
echo "after Copy text with multi-format clipboard: html still there=$(xclip -selection clipboard -o -t text/html 2>/dev/null | head -c 30)" >> $O/events.txt
kill $HP 2>/dev/null; sleep 1
xdotool mousemove $((X+WIDTH/8)) $BY click 1; sleep .8   # Copy text (single/empty previous)
echo "clip text after Copy text: $(xclip -selection clipboard -o -t UTF8_STRING)" >> $O/events.txt
# (b) user copies something between Copy and Insert: Insert must refuse cleanly (GTK callback), entry stays empty
printf stolen-by-user | xclip -selection clipboard -i; sleep .5
xdotool mousemove $((X+5*WIDTH/8)) $BY click 1; sleep 1.5; import -window root $O/gtk_changed_refused.png
echo "entry after refused Insert: [$(cat $O/entry.txt)]" >> $O/events.txt
xdotool mousemove $((X+3*WIDTH/8)) $BY click 1; sleep .5   # Copy image
xclip -selection clipboard -o -t image/png > $O/clip_image.png 2>/dev/null; echo "clip image bytes: $(stat -c %s $O/clip_image.png)" >> $O/events.txt
xdotool mousemove $((X+5*WIDTH/8)) $BY click 1; sleep 2   # Insert draft
python3 -c "from PIL import ImageGrab;ImageGrab.grab().save('$O/after_insert.png')"
echo "entry text: $(cat $O/entry.txt)" >> $O/events.txt
kill $AP $TP $WP $XP 2>/dev/null; sleep .5; cd /tmp/runs 2>/dev/null; true
