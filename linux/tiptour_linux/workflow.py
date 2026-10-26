"""Teaching-mode post-click validator: port of Mac WorkflowRunner.captureAccessibilityFingerprint + shouldBypassPostClickValidator + the post-click compare.

Mac (6e97782 WorkflowRunner.swift:1376-1465): an ORDERED preorder walk of the target app's FOCUSED WINDOW, role|title|value(<=120 chars) per node, <=120 nodes, depth<8, 0.15s budget,
hashed (order and duplicate counts matter); a pre-click snapshot is taken at arm time, after the click the state is polled and a different hash = effect confirmed, unchanged = pause.
Ported here: focused (AT-SPI ACTIVE) window only, ordered role|title|value triples, same walk order, duplicates preserved, value truncation, the Mac bypass (rightClick, or the NEXT step is
keyboardShortcut/pressKey/type/setValue/scroll), and "favor a false pause over a wrong advance".
Linux deviations (explicit, measured): (1) node/depth/time caps. Mac 120/8/0.15s. On Chromium via AT-SPI the 120/depth-8 walk stops inside the browser chrome BEFORE the page controls, so it cannot see a page change at all (measured run 1026-1606-fp: the page's first control is node 136 of 229). Default here is 400 nodes / depth 40 / 0.15s (Mac time budget kept: a 229-node walk measures ~0.08s); a read cut by the time budget is treated as a FAILED read (never compared). TIPTOUR_FP_NODES/DEPTH/BUDGET_S restore the Mac constants. (2) VOLATILE nodes: AT-SPI exposes live text that changes without any user action (Chromium's tab name carries "Memory usage - N MB"). While the pointer is armed and idle the validator keeps sampling; any node position whose triple changes between two consecutive idle samples (same node count) is masked to its role in the compare. Generic, no label/pattern list. A volatile node that has not yet ticked during the idle window can still read as a false 'changed' (residual). Real structural changes (node count changes) are never masked. (3) 'pause' = keep the pointer and record an event + on-screen panel.
"""
import threading, time
from collections import Counter

MAC_NODES, MAC_DEPTH, MAC_BUDGET_S = 120, 8, 0.15
BYPASS_NEXT = ("keyboardShortcut", "pressKey", "type", "setValue", "scroll")


def bypass_validator(step, next_step):
    """Mac shouldBypassPostClickValidator: rightClick, or the following step is a key/type/setValue/scroll action (the click may be an AX-level no-op)."""
    if (step or {}).get("type") == "rightClick": return True
    return bool(next_step) and (next_step or {}).get("type") in BYPASS_NEXT


def scope_app(targets, point):
    """App (AT-SPI application name) of the smallest visible control whose rect contains the armed point; None when unknown."""
    best = None
    for t in targets or []:
        x, y, w, h = t["rect"]
        if x <= point[0] <= x + w and y <= point[1] <= y + h and (best is None or w * h < best[0]):
            best = (w * h, t.get("app") or "")
    return best[1] or None if best else None


def mask_triples(triples, volatile):
    """Ordered list; a volatile node position keeps only its role (title and value masked)."""
    return [(t.split("|", 1)[0] if i in volatile else t) for i, t in enumerate(triples)]


def learn_volatile(prev, cur, volatile):
    """Two consecutive IDLE samples: positions whose triple changed with the same node count are volatile. A different node count is structure, not noise."""
    if prev is not None and len(prev) == len(cur):
        volatile.update(i for i in range(len(cur)) if prev[i] != cur[i])


def changed(base, post, volatile):
    """Ordered compare (duplicates and order matter, like the Mac hash of the joined triples) after masking volatile positions."""
    if len(base) != len(post): return True
    return mask_triples(base, volatile) != mask_triples(post, volatile)


def diff_counts(base, post):
    a, b = Counter(base), Counter(post)
    return sorted((a - b).elements())[:6], sorted((b - a).elements())[:6]


class ClickValidator:
    """Arm-time baseline thread (never blocks arming): resolves the app, then keeps sampling the focused-window fingerprint while idle until the click. A sample that finishes after the click
    is discarded. A click before two good samples exist is UNVERIFIED (post-click state is never the baseline). Verdicts: changed | unchanged_paused | unavailable:<reason>.
    walk_fp(app) -> {"triples": [...], "truncated": bool}."""
    trig = None

    def __init__(self, walk_all, walk_fp, point, app_hint=None, attempts=6, sleep_s=0.25, gap_s=0.4, sleep=time.sleep, max_idle_samples=200):
        self.walk_all, self.walk_fp, self.point, self.app_hint = walk_all, walk_fp, point, app_hint
        self.attempts, self.sleep_s, self.gap_s, self.sleep, self.max_idle = attempts, sleep_s, gap_s, sleep, max_idle_samples
        self.ready = threading.Event(); self.done = threading.Event(); self.clicked = threading.Event()
        self.scope = None; self.base = None; self.volatile = set(); self.baseline_error = None; self.idle_samples = 0
        self.verdict = None; self.detail = {}; self._threads = []; self.sample = None; self.trig = {}; self.reads = []

    @property
    def stable(self): return self.base or []
    @property
    def noise(self): return self.volatile

    def _read(self):
        try:
            d = self.walk_fp(self.scope)
            return None if (not d or d.get("truncated") or not d.get("triples")) else d["triples"]
        except Exception:
            return None

    def start_baseline(self):
        t = threading.Thread(target=self._baseline, daemon=True); self._threads.append(t); t.start()

    def _baseline(self):
        try:
            self.scope = self.app_hint
            if not self.scope:
                try: self.scope = scope_app(self.walk_all(), self.point)
                except Exception: self.scope = None
            if not self.scope:
                self.baseline_error = "no_atspi_control_at_target_point"; self.ready.set(); return
            prev = None; good = 0; tries = 0
            while not self.clicked.is_set() and self.idle_samples < self.max_idle:
                cur = self._read()
                if self.clicked.is_set(): break  # finished after the click: discard
                self.idle_samples += 1
                if cur is None:
                    tries += 1
                    if good < 2 and tries >= 6: self.baseline_error = "empty_baseline"; break
                else:
                    learn_volatile(prev, cur, self.volatile); prev = cur; self.base = cur; good += 1
                    if good >= 2: self.ready.set()
                self.sleep(self.gap_s)
            if good < 2 and not self.baseline_error and not self.clicked.is_set(): self.baseline_error = "empty_baseline"
        except Exception as e:
            self.baseline_error = "baseline_read_failed:" + type(e).__name__
        finally:
            self.ready.set()

    def on_click(self):
        """Call at the hit. Never blocks: spawns the verdict thread."""
        was_ready = self.ready.is_set() and self.base is not None and self.idle_samples >= 2
        self.clicked.set()
        t = threading.Thread(target=self._verdict, args=(was_ready,), daemon=True); self._threads.append(t); t.start()

    def _verdict(self, was_ready):
        try:
            if not was_ready:
                self.verdict = "unavailable:click_before_baseline_ready"
            elif self.baseline_error:
                self.verdict = "unavailable:" + self.baseline_error
            else:
                base = list(self.base); ok = bad = 0; last = None; end = time.monotonic() + 20.0; v = None
                for _ in range(self.attempts):
                    if time.monotonic() > end: break
                    post = self._read()
                    if post is None:
                        bad += 1; self.reads.append({"n": 0, "failed": True})
                    else:
                        ok += 1; rem, add = diff_counts(base, post)
                        self.reads.append({"n": len(post), "removed": rem, "added": add})
                        if changed(base, post, self.volatile):
                            sig = (len(post), tuple(mask_triples(post, self.volatile)))
                            if last == sig:  # the SAME post state on two successive reads (one read can be a partial tree)
                                self.trig.update(removed=rem[:4], added=add[:4], read_no=ok); v = True; break
                            last = sig
                        else: last = None
                    self.sleep(self.sleep_s)
                self.detail = {"ok_reads": ok, "failed_reads": bad, "volatile_nodes": len(self.volatile), "idle_samples": self.idle_samples, "baseline_nodes": len(base)}
                if v: self.sample = (self.trig.get("removed", []), self.trig.get("added", [])); self.detail["trigger_read"] = self.trig.get("read_no")
                self.verdict = "changed" if v else ("unchanged_paused" if ok else "unavailable:all_post_reads_failed")
        except Exception as e:
            self.verdict = "unavailable:verdict_error:" + type(e).__name__
        finally:
            self.done.set()

    def join(self, timeout=8.0):
        """Bounded wait; returns the verdict or 'pending_at_shutdown'."""
        self.done.wait(timeout)
        return self.verdict if self.done.is_set() else "pending_at_shutdown"


class PlanTargetMatcher:
    """Port of WorkflowRunner.activationMatchesCurrentPlanTarget (Swift :1284). An app activation pauses the plan ONLY if the activated app is unrelated to the plan's target.
    OS mapping (the only differences): Mac bundleIdentifier -> X11 app id = lowercase 'wm_class_instance.wm_class_class'; Mac localizedName -> lowercase WM_CLASS class name.
    planTargetAppBundleID is cached on the first match, like the Swift. Seed: the app of the window the target was armed on (Linux has no running-app lookup by the plan's app hint)."""
    def __init__(self, plan_app=None, step_type=None, step_label=None, seed_app_id=None):
        self.plan_app = plan_app; self.step_type = step_type; self.step_label = step_label; self.target_id = seed_app_id
    def matches(self, name, app_id):
        if app_id and self.target_id and app_id == self.target_id: return True
        names = [t for t in ((self.plan_app or "").strip().lower(), (self.step_label or "").strip().lower() if self.step_type == "openApp" else "") if t]
        n = (name or "").lower() or None; b = (app_id or "").lower() or None
        hit = any((n == t) or (n is not None and t in n) or (b is not None and t in b) for t in names)
        if hit: self.target_id = app_id
        return hit
