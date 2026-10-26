#!/bin/bash
# App-specific clean-exit check (no model, no browser): fake client, --voice, mic toggled ON with the real Ctrl+Alt chord, then @quit while the mic is live.
# Records exit status, wall time to exit, whether the 3 s watchdog fired, and leftover parec/paplay children.
cd /home/sandbox/tiptour/linux
O=${RUN_DIR:?new unique dir}; [ -e $O ] && { echo exists; exit 2; }; mkdir -p $O
. tests/clean_env.sh; tools/snapshot_tree.sh $O
export TIPTOUR_TEST_MODE=1 TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=$PWD/tests:$PWD TIPTOUR_MIC_SOURCE=tt_in.monitor TIPTOUR_AUDIO_SINK=tt_out DISPLAY=:83
Xvfb :83 -screen 0 1280x800x24 >/dev/null 2>&1 & XP=$!; sleep 1
mkfifo $O/fifo
python3 -m tiptour_linux.app --voice --serve $O/fifo --out $O > $O/stdout.txt 2> $O/stderr.txt & AP=$!; sleep 4
xdotool keydown ctrl keydown alt; sleep .4; xdotool keyup alt keyup ctrl; sleep 2
echo "parec running before quit: $(pgrep -f 'parec --format' | wc -l)" > $O/events.txt
T0=$(date +%s.%N); echo "@quit" > $O/fifo
wait $AP; RC=$?; T1=$(date +%s.%N)
echo "exit code $RC after $(python3 -c "print(round($T1-$T0,2))") s" >> $O/events.txt
echo "watchdog fired: $(grep -c WATCHDOG $O/stderr.txt)" >> $O/events.txt
sleep 1; echo "parec/paplay left after exit: $(pgrep -f 'parec --format|paplay --raw' | wc -l)" >> $O/events.txt
kill $XP 2>/dev/null; cat $O/events.txt
