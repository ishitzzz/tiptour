"""Compare where the overlay tip landed (px from the model's point) with the real widget rect."""
import json, sys
rects = json.load(open("/tmp/target-rects.json")); res = json.load(open(sys.argv[1] + "/results.json"))
targets = sys.argv[2:]; ok = True
for r, name in zip(res, targets):
    x, y = r["tool"]["px"]; rx, ry, w, h = rects[name]
    inside = rx <= x <= rx + w and ry <= y <= ry + h
    d = ((x - (rx + w / 2)) ** 2 + (y - (ry + h / 2)) ** 2) ** .5
    print("%-12s src=%s model_px=%s tip=(%d,%d) rect=%s inside=%s dist_from_center=%.0fpx reply=%r" % (name, r["tool"]["source"], r["tool"]["model_px"], x, y, rects[name], inside, d, r["reply"]))
    ok &= inside
print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
