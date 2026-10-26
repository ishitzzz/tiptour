for cfg in "A_default:" "B_nowarm:TIPTOUR_NO_WARM=1" "C_nostream:TIPTOUR_STREAM=0" "D_both_off:TIPTOUR_NO_WARM=1 TIPTOUR_STREAM=0"; do
  name=${cfg%%:*}; envs=${cfg#*:}
  pkill Xvfb; pkill -f chrome; pkill xfwm4; pkill ffmpeg; sleep 2
  export AB_OUT=/tmp/ab-$name AB_DELAY=30 AB_ENV="$envs"
  timeout 100 bash /tmp/serve5_local.sh > /dev/null 2>&1
  echo "== $name ($envs)" >> /tmp/ab-summary.txt
  grep -E "commit:|atspi-worker _probe|FAKE" /tmp/ab-$name/stdout.txt | cut -c1-220 >> /tmp/ab-summary.txt
done
echo DONE >> /tmp/ab-summary.txt
