cd "${TT_TREE:-/home/sandbox/tiptour/linux}"
export TIPTOUR_KEYS_GLOB='/home/sandbox/.vault/gemini-*/password'
O=/tmp/sv3; mkdir -p $O; rm -f $O/fifo
. tests/browser_env.sh https://en.wikipedia.org/wiki/Neural_network_\(machine_learning\) $O
R=$(python3 - <<'PY'
from tiptour_linux import cdp_resolver as c
ts=[t for t in c.all_targets() if not t.get("off") and t["role"] in ("a","button") and t["label"].lower() in ("donate","create account","log in")]
import json
xs=[t["rect"] for t in ts]
print(json.dumps({"n":len(ts),"labels":[t["label"][:20] for t in ts],"x0":min(r[0] for r in xs),"y0":min(r[1] for r in xs),"x1":max(r[0]+r[2] for r in xs),"y1":max(r[1]+r[3] for r in xs)}))
PY
)
echo "REGION $R" > $O/region.txt
read X0 Y0 X1 Y1 < <(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(int(d['x0'])-8,int(d['y0'])-8,int(d['x1'])+8,int(d['y1'])+8)")
( sleep 8; xdotool mousemove $X0 $Y0; xdotool keydown ctrl keydown shift
  for p in "$((X0+60)) $Y0" "$((X0+140)) $Y0" "$X1 $Y0" "$X1 $Y1" "$((X1-80)) $Y1" "$((X0+60)) $Y1" "$X0 $Y1" "$X0 $((Y0+3))"; do xdotool mousemove $p; sleep 0.2; done
  xdotool keyup shift keyup ctrl
  sleep 14; echo "Point to the highlighted button." > $O/fifo
  sleep 16; python3 -c "from PIL import ImageGrab; ImageGrab.grab().save('$O/after.png')"
  echo "@quit" > $O/fifo ) &
SUB=$!
python3 -m tiptour_linux.app --highlight --serve $O/fifo --hold 3 --out $O 2>&1 | grep -E "highlight|serve|result|refus|toolCall|cdp" | cut -c1-500
wait $SUB 2>/dev/null; sleep 1
kill $FP $CP $XP 2>/dev/null
