"""LocalPerceptionTargetCache: port of TipTour/Perception/LocalPerceptionTargetCache.swift (base 6e97782).
Same structure and numbers as the Mac source: 60 s TTL, OCR label enrichment for unlabeled detections, label scoring
(100 exact / 92 normalized / 72 substring / fuzzy 68,54 / word coverage 58,42), source bonus + confidence*4 - proximity penalty (<=8),
currentTargets(limit=160) sorted by source priority then confidence with marks = index+1, target ids "source:label:x1:y1:x2:y2".
OS translation (the ONLY deliberate difference): Mac global coordinates have a BOTTOM-LEFT origin (y flipped with displayFrame.height);
X11 global coordinates have a TOP-LEFT origin, so the y flip is not applied. Rects are (x, y, w, h)."""
import math, re, threading, time

STOP_WORDS = {"the", "a", "an", "this", "that", "these", "those", "button", "icon", "menu", "bar", "tab", "panel", "item", "option",
              "link", "field", "input", "box", "area", "section", "row", "cell", "click", "press", "open", "choose", "select"}
TTL_MS = 60_000

def source_priority(source): return 4 if source == "ocr" else 1

def normalize(text):
    low = text.lower(); raw = re.findall(r"[^\W_]+", low)
    meaningful = [w for w in raw if w not in STOP_WORDS]
    return low, set(meaningful if meaningful else raw)

def edit_distance(a, b):
    if not a: return len(b)
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
        prev = cur
    return prev[len(b)]

def fuzzy_single_word_score(q, l):
    if min(len(q), len(l)) < 4 or max(len(q), len(l)) > 16: return None
    d = edit_distance(q, l)
    if d == 1: return 68
    if d == 2 and max(len(q), len(l)) >= 8: return 54
    return None

def label_match_score(query, label):
    q = query.strip(); l = label.strip()
    if not q or not l: return None
    ql, ll = q.lower(), l.lower(); nq_full, nq_words = normalize(q); nl_full, nl_words = normalize(l)
    if ql == ll: return 100
    if nq_full == nl_full: return 92
    if len(ql) >= 5 and len(ll) >= 5 and (ql in ll or ll in ql): return 72
    if len(nq_words) == 1 and len(nl_words) == 1:
        f = fuzzy_single_word_score(next(iter(nq_words)), next(iter(nl_words)))
        if f is not None: return f
    shared = {w for w in (nq_words & nl_words) if len(w) >= 3}
    if not shared: return None
    if len(nq_words) > 1 and len(shared) < len(nq_words): return None
    coverage = len(shared) / max(len(nq_words), 1)
    if coverage >= 1.0: return 58
    if coverage >= 0.5: return 42
    return None

class Candidate:
    __slots__ = ("rect", "label", "source", "confidence")
    def __init__(self, rect, label, source, confidence): self.rect = rect; self.label = label; self.source = source; self.confidence = confidence
    @property
    def center(self): return (self.rect[0] + self.rect[2] / 2.0, self.rect[1] + self.rect[3] / 2.0)

def _intersect_area(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1]); x2 = min(a[0] + a[2], b[0] + b[2]); y2 = min(a[1] + a[3], b[1] + b[3])
    return max(0, x2 - x1) * max(0, y2 - y1)

def parse_candidates(elements):
    out = []
    for e in elements:
        bb = e.get("bbox")
        if not (isinstance(bb, (list, tuple)) and len(bb) == 4): continue
        x1, y1, x2, y2 = bb
        rect = (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        if not (rect[2] > 4 and rect[3] > 4): continue
        out.append(Candidate(rect, e.get("label") or "", e.get("source") or "yolo", float(e.get("conf") or 0)))
    return out

def best_ocr_label(c, ocr):
    ex = (c.rect[0] - 10, c.rect[1] - 8, c.rect[2] + 20, c.rect[3] + 16)
    scored = []
    for o in ocr:
        ia = _intersect_area(ex, o.rect); oa = max(1, o.rect[2] * o.rect[3]); overlap = ia / oa
        dist = math.hypot(c.center[0] - o.center[0], c.center[1] - o.center[1])
        if not (overlap > 0.25 or dist < max(c.rect[2], c.rect[3]) * 0.9): continue
        inside = c.rect[0] <= o.center[0] <= c.rect[0] + c.rect[2] and c.rect[1] <= o.center[1] <= c.rect[1] + c.rect[3]
        scored.append(((1000 if inside else 0) + overlap * 800 - dist * 0.8, o))
    scored.sort(key=lambda t: -t[0])
    if not scored: return None
    best = scored[0][1]
    near = [o for _, o in scored[:3] if abs(o.center[1] - best.center[1]) < max(14, best.rect[3] * 0.8)]
    near.sort(key=lambda o: o.rect[0])
    joined = " ".join(o.label for o in near).strip()
    return joined or None

def enrich_labels(cands):
    ocr = [c for c in cands if c.source == "ocr" and c.label.strip()]
    out = []
    for c in cands:
        if c.label.strip(): out.append(c); continue
        lab = best_ocr_label(c, ocr)
        out.append(Candidate(c.rect, lab, c.source, c.confidence) if lab else c)
    return out

class LocalPerceptionTargetCache:
    def __init__(self, clock=time.time): self._lock = threading.Lock(); self._snap = None; self._clock = clock
    def update(self, elements, image_size, display_frame):
        cands = enrich_labels(parse_candidates(elements))
        with self._lock: self._snap = (cands, image_size, display_frame, self._clock())
    def clear(self):
        with self._lock: self._snap = None
    def _fresh(self):
        with self._lock: s = self._snap
        if not s: return None, 0
        age = int((self._clock() - s[3]) * 1000)
        return (s if age < TTL_MS else None), age
    # --- coordinate maps (top-left origin on X11; see module docstring)
    @staticmethod
    def px_to_global(px, py, image_size, df):
        x = max(0, min(px, image_size[0])); y = max(0, min(py, image_size[1]))
        return (x * (df[2] / max(image_size[0], 1)) + df[0], y * (df[3] / max(image_size[1], 1)) + df[1])
    @classmethod
    def rect_to_global(cls, r, image_size, df):
        tl = cls.px_to_global(r[0], r[1], image_size, df); br = cls.px_to_global(r[0] + r[2], r[1] + r[3], image_size, df)
        return (min(tl[0], br[0]), min(tl[1], br[1]), abs(br[0] - tl[0]), abs(br[1] - tl[1]))
    @staticmethod
    def global_to_px(gx, gy, image_size, df):
        return ((gx - df[0]) * (image_size[0] / max(df[2], 1)), (gy - df[1]) * (image_size[1] / max(df[3], 1)))
    @staticmethod
    def box2d(r, image_size):
        c = lambda v: max(0, min(1000, int(math.floor(v + 0.5) if v >= 0 else -math.floor(-v + 0.5))))  # Swift .rounded() = half AWAY from zero (Python round() is banker's)
        return [c(r[1] * 1000 / max(image_size[1], 1)), c(r[0] * 1000 / max(image_size[0], 1)),
                c((r[1] + r[3]) * 1000 / max(image_size[1], 1)), c((r[0] + r[2]) * 1000 / max(image_size[0], 1))]
    @staticmethod
    def target_id(c):
        r = c.rect; return ":".join([c.source, c.label, str(int(r[0])), str(int(r[1])), str(int(r[0] + r[2])), str(int(r[1] + r[3]))])
    def resolve(self, label, prefer_near_global_point=None):
        s, age = self._fresh()
        if not s: return None
        cands, image_size, df, _ = s
        anchor = self.global_to_px(*prefer_near_global_point, image_size, df) if prefer_near_global_point else None
        best = None; best_score = None
        for c in cands:
            ls = label_match_score(label, c.label)
            if ls is None: continue
            pen = min(math.hypot(c.center[0] - anchor[0], c.center[1] - anchor[1]) / 120.0, 8.0) if anchor else 0
            sc = ls + source_priority(c.source) + min(c.confidence, 1.0) * 4.0 - pen
            if best_score is None or sc > best_score: best, best_score = c, sc   # Swift max(by:) keeps the later element on ties only if strictly greater; first max kept here
        if not best: return None
        g = self.rect_to_global(best.rect, image_size, df)
        return {"label": best.label or label, "source": best.source, "global_point": (g[0] + g[2] / 2, g[1] + g[3] / 2), "global_rect": g,
                "display_frame": df, "cache_age_ms": age, "normalized_box_2d": self.box2d(best.rect, image_size)}
    def current_targets(self, limit=160):
        s, age = self._fresh()
        if not s: return []
        cands, image_size, df, _ = s
        ordered = sorted([c for c in cands if c.label.strip()], key=lambda c: (-source_priority(c.source), -c.confidence))[:limit]
        out = []
        for i, c in enumerate(ordered):
            g = self.rect_to_global(c.rect, image_size, df)
            out.append({"id": self.target_id(c), "mark": i + 1, "label": c.label, "source": c.source, "confidence": c.confidence,
                        "screenshot_box": [c.rect[0], c.rect[1], c.rect[0] + c.rect[2], c.rect[1] + c.rect[3]],
                        "normalized_box_2d": self.box2d(c.rect, image_size), "global_center": [g[0] + g[2] / 2, g[1] + g[3] / 2],
                        "global_box": [g[0], g[1], g[0] + g[2], g[1] + g[3]], "display_frame": list(df), "cache_age_ms": age})
        return out
    def fresh_target_count(self): return len(self.current_targets())
