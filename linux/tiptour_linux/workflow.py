"""Teaching-mode post-click validator (analogue of Mac WorkflowRunner.captureAccessibilityFingerprint + post-click validator).

Mac: before arming, hash role/title/value of <=120 AX nodes of the focused window (0.15s budget); after the user's click, poll up to
5 x 80ms for a different hash; unchanged -> pause(.postClickStateUnchanged).
Linux deviations (honest): AT-SPI fingerprint covers visible clickable controls (role, name, rounded rect, cap 400) of the APP that owns the
armed target (not only its focused window: other windows of the same app can still change it); settle window is longer (6 x 250ms) because Chrome's AT-SPI tree updates slowly; 'pause' = keep the pointer
and record an event (no retry/skip UI). Like the Mac, a harmless click that changes no AX state (e.g. a no-op button) reads as 'unchanged'.
"""
import hashlib, threading, time


def scope_app(targets, point):
    """App (AT-SPI application name) of the smallest visible control whose rect contains the armed point; None when unknown."""
    best = None
    for t in targets or []:
        x, y, w, h = t["rect"]
        if x <= point[0] <= x + w and y <= point[1] <= y + h and (best is None or w * h < best[0]):
            best = (w * h, t.get("app") or "")
    return best[1] or None if best else None


def items_of(targets, app, cap=400):
    return sorted((t["role"], t["label"][:80]) for t in targets or [] if (t.get("app") or "") == app)[:cap] if app else []  # Mac AX fingerprint = role|title|value, GEOMETRY EXCLUDED (WorkflowRunner.swift:1376-1465): a control that merely MOVES must read unchanged. VALUE is not available from the AT-SPI target list yet (known gap)


def diff_items(a, b):
    sa, sb = set(a), set(b)
    return sorted(sa - sb)[:6], sorted(sb - sa)[:6]


def fingerprint_of(targets, app, cap=400):
    """Hash of the target APP's visible clickable controls only: a change in an unrelated app must not certify the click."""
    if not app:
        return None
    items = sorted((t["role"], t["label"][:80]) for t in targets or [] if (t.get("app") or "") == app)[:cap]
    if not items:
        return None
    return hashlib.sha1(repr(items).encode()).hexdigest()


def fingerprint(all_targets, app, timeout=2.0):
    try:
        return fingerprint_of(all_targets(timeout=timeout), app)
    except Exception:
        return None


def validate_changed(pre, fp_fn, attempts=6, sleep_s=0.25, sleep=time.sleep):
    """True when a post-click fingerprint differs from pre within the settle window. pre None -> (None) not validatable."""
    if pre is None:
        return None
    for _ in range(attempts):
        post = fp_fn()
        if post is not None and post != pre:
            return True
        sleep(sleep_s)
    return False


def stable_pre(items_a, items_b):
    """Two pre-click snapshots taken ~0.4s apart. Items present in only one are NOISE (Chrome's AT-SPI tree wobbles: 18 vs 19 targets seen on an idle page)."""
    a, b = set(items_a), set(items_b)
    return a & b, a ^ b


def changed_vs_pre(stable, noise, post_items):
    """True when the post-click item set (minus known noise) differs from the stable pre set."""
    return (set(post_items) - noise) != stable


def validate_items(stable, noise, post_fn, attempts=6, sleep_s=0.25, sleep=time.sleep, trigger=None, reads=None, deadline_s=20.0):
    """Returns (verdict, ok_reads, failed_reads). verdict: True changed / False unchanged (needs >=1 successful read) / None unavailable (no stable baseline or ALL post reads failed)."""
    if not stable:
        return None, 0, 0
    ok = bad = 0
    last = None
    _end = time.monotonic() + deadline_s  # wall-time bound: slow walks (0.8s..7s seen) must not stretch the window indefinitely
    for _ in range(attempts):
        if time.monotonic() > _end: break
        post = post_fn()
        if reads is not None:  # per-read evidence (SENSITIVE: control labels); written only to the run's evidence dir, never to the log
            pp_ = set(post or [])
            reads.append({"n": len(pp_), "removed": [list(map(str, x)) for x in sorted(stable) if x not in pp_][:6], "added": [list(map(str, x)) for x in sorted(pp_ - noise) if x not in stable][:6]} if post else {"n": 0, "failed": True})
        if post:
            ok += 1
            if changed_vs_pre(stable, noise, post):
                # a difference counts only when the SAME difference is seen on two successive reads (a single read can be a partial/wobbling Chrome tree)
                sig = frozenset(set(post) - noise) ^ frozenset(stable)
                if last == sig:
                    if trigger is not None:  # diff of the EXACT confirming read
                        pp = set(post)
                        trigger.update(removed=[x for x in sorted(stable) if x not in pp][:4], added=[x for x in sorted(pp - noise) if x not in stable][:4], read_no=ok)
                    return True, ok, bad
                last = sig
            else:
                last = None
        else:
            bad += 1
        sleep(sleep_s)
    return (False if ok else None), ok, bad


class ClickValidator:
    trig = None
    """Mac WorkflowRunner post-click validator analogue, restructured so arming never waits for the baseline.
    Baseline (two app-scoped snapshots 0.4s apart) runs in a thread started at arm time. A click that arrives before the baseline is ready is
    UNVERIFIED (post-click state is never used as the baseline). Verdict values: changed | unchanged_paused | unavailable:<reason>."""

    def __init__(self, walk_all, walk_app, point, app_hint=None, attempts=6, sleep_s=0.25, gap_s=0.4, sleep=time.sleep):
        self.walk_all, self.walk_app, self.point, self.app_hint = walk_all, walk_app, point, app_hint
        self.attempts, self.sleep_s, self.gap_s, self.sleep = attempts, sleep_s, gap_s, sleep
        self.ready = threading.Event(); self.done = threading.Event()
        self.scope = None; self.stable = set(); self.noise = set(); self.baseline_error = None
        self.verdict = None; self.detail = {}; self._threads = []; self.sample = None; self.trig = {}; self.reads = []

    def start_baseline(self):
        t = threading.Thread(target=self._baseline, daemon=True); self._threads.append(t); t.start()

    def _baseline(self):
        try:
            self.scope = self.app_hint
            if self.scope:
                try: t1 = self.walk_app(self.scope)
                except Exception: t1 = []
            else:
                full = self.walk_all(); self.scope = scope_app(full, self.point); t1 = full  # no AT-SPI control at the point -> scope None -> unavailable
            if not self.scope:
                self.baseline_error = "no_atspi_control_at_target_point"; return
            a = items_of(t1, self.scope)
            tries = 0
            while not a and tries < 3:  # Chrome builds its AT-SPI tree lazily: an empty first read is a failed read, not a baseline
                tries += 1; self.sleep(self.gap_s)
                try: a = items_of(self.walk_app(self.scope), self.scope)
                except Exception: a = []
            self.sleep(self.gap_s)
            b = items_of(self.walk_app(self.scope), self.scope)
            tries = 0
            while not b and tries < 3:
                tries += 1; self.sleep(self.gap_s)
                try: b = items_of(self.walk_app(self.scope), self.scope)
                except Exception: b = []
            self.stable, self.noise = stable_pre(a, b) if (a and b) else (set(), set())
            if not self.stable: self.baseline_error = "empty_baseline"
        except Exception as e:
            self.baseline_error = "baseline_read_failed:" + type(e).__name__
        finally:
            self.ready.set()

    def on_click(self):
        """Call at the hit. Never blocks: spawns the verdict thread."""
        was_ready = self.ready.is_set()
        t = threading.Thread(target=self._verdict, args=(was_ready,), daemon=True); self._threads.append(t); t.start()

    def _post(self):
        try:
            return items_of(self.walk_app(self.scope), self.scope)
        except Exception:
            return None

    def _verdict(self, was_ready):
        try:
            if not was_ready:
                self.verdict = "unavailable:click_before_baseline_ready"
            elif self.baseline_error:
                self.verdict = "unavailable:" + self.baseline_error
            else:
                v, ok, bad = validate_items(self.stable, self.noise, self._post, self.attempts, self.sleep_s, self.sleep, trigger=self.trig, reads=self.reads)
                self.detail = {"ok_reads": ok, "failed_reads": bad, "noise_items": len(self.noise), "stable_items": len(self.stable)}
                if v:
                    self.sample = (self.trig.get('removed', []), self.trig.get('added', []))
                    self.detail['trigger_read'] = self.trig.get('read_no')
                self.verdict = "changed" if v else ("unchanged_paused" if v is False else "unavailable:all_post_reads_failed")
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
