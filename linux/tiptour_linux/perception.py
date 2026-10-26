"""Local perception: YOLO icon boxes + OCR text, and refineCoordinate port of
NativeElementDetector.swift (containing-box + OCR label confirm, then label-matched box within 200px,
else None => caller keeps raw Gemini coordinates). OCR: tesseract (Linux stand-in for Apple Vision;
not identical to Vision accuracy)."""
import csv, io, subprocess, tempfile, os
from PIL import Image

STOP = {"the","a","an","this","that","these","those","button","icon","menu","bar","tab","panel","item","option","link","field","input","box","area","section","row","cell"}

def ocr(img: Image.Image, min_conf=40):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.png"); img.convert("RGB").save(p)
        tsv = subprocess.run(["tesseract", p, "-", "--psm", "11", "tsv"], capture_output=True, text=True).stdout
    lines = {}
    for r in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        t = (r.get("text") or "").strip()
        if not t or float(r["conf"]) < min_conf: continue
        k = (r["block_num"], r["par_num"], r["line_num"]); x, y, w, h = (int(r[c]) for c in ("left", "top", "width", "height"))
        e = lines.setdefault(k, {"words": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h, "conf": []})
        e["words"].append(t); e["x0"] = min(e["x0"], x); e["y0"] = min(e["y0"], y); e["x1"] = max(e["x1"], x + w); e["y1"] = max(e["y1"], y + h); e["conf"].append(float(r["conf"]))
    out = []
    for e in lines.values():
        b = [e["x0"], e["y0"], e["x1"] - e["x0"], e["y1"] - e["y0"]]
        out.append({"label": " ".join(e["words"]), "bbox": b, "center": [b[0] + b[2] / 2, b[1] + b[3] / 2], "conf": sum(e["conf"]) / len(e["conf"]) / 100, "source": "ocr"})
    return out

def _norm(t):
    low = t.lower(); raw = [w for w in "".join(c if c.isalnum() else " " for c in low).split()]
    m = [w for w in raw if w not in STOP]; return low, set(m or raw)

def strict_match(query, label):
    q, l = query.strip(), label.strip()
    if not q or not l: return False
    ql, ll = q.lower(), l.lower(); nq, nl = _norm(q), _norm(l)
    if ql == ll or nq[0] == nl[0]: return True
    if len(ql) >= 3 and len(ll) >= 3 and (ll in ql or ql in ll): return True
    shared = {w for w in nl[1] & nq[1] if len(w) >= 3}
    if not shared: return False
    if len(nq[1]) > 1: return len(shared) == len(nq[1])
    return True

def _inter(a, b): return not (a[0] + a[2] < b[0] or b[0] + b[2] < a[0] or a[1] + a[3] < b[1] or b[1] + b[3] < a[1])
def _contains(b, p): return b[0] <= p[0] <= b[0] + b[2] and b[1] <= p[1] <= b[1] + b[3]

def refine_coordinate(hint, label, yolo, ocr_el):
    if not yolo: return None
    def labels(box): return [o["label"] for o in sorted([o for o in ocr_el if _inter(box["bbox"], o["bbox"])], key=lambda o: -o["bbox"][2] * o["bbox"][3]) if o["label"].strip()]
    conf = [b for b in yolo if _contains(b["bbox"], hint) and any(strict_match(label, l) for l in labels(b))]
    if conf:
        b = min(conf, key=lambda b: b["bbox"][2] * b["bbox"][3]); return dict(b, rule="containing_box_label_confirmed")
    best = None
    for b in yolo:
        d = ((b["center"][0] - hint[0]) ** 2 + (b["center"][1] - hint[1]) ** 2) ** .5
        if d > 200: continue
        if any(strict_match(label, o["label"]) for o in ocr_el if _inter(b["bbox"], o["bbox"]) or _contains(b["bbox"], o["center"])):
            if best is None or d < best[0]: best = (d, b)
    return dict(best[1], rule="label_matched_box_within_200px") if best else None
