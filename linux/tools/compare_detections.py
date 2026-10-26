"""Greedy-match two detection dumps (mac vs linux); report count diff, max conf diff, max box offset (px)."""
import sys, json
a, b = (json.load(open(p))["detections"] for p in sys.argv[1:3]); used = set(); worst_c = worst_p = 0; miss = 0
for d in a:
    best = None
    for j, e in enumerate(b):
        if j in used: continue
        off = max(abs(d[k] - e[k]) for k in "xywh")
        if best is None or off < best[0]: best = (off, j, abs(d["conf"] - e["conf"]))
    if best is None or best[0] > 10: miss += 1; continue
    used.add(best[1]); worst_p = max(worst_p, best[0]); worst_c = max(worst_c, best[2])
print(f"mac={len(a)} linux={len(b)} unmatched_mac={miss} unmatched_linux={len(b)-len(used)} max_box_offset_px={worst_p:.2f} max_conf_diff={worst_c:.4f}")
