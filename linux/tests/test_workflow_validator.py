"""Pure-logic unit tests of the Mac-ported validator (injected walkers; NOT a real-app test)."""
import sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tiptour_linux.workflow import (ClickValidator, bypass_validator, mask_triples, learn_volatile, changed, diff_counts, scope_app)
B = ["frame|Win|", "push button|Next|Next", "tab|T - Memory usage - 23.4 MB|", "push button|Next|Next"]
# order + duplicate counts matter
assert changed(B, B[::-1], set()) and changed(B, B[:3] + ["push button|Other|Other"], set()) and changed(B, B[:3], set())
assert diff_counts(["a", "a", "b"], ["a", "b"]) == (["a"], [])  # duplicate COUNT preserved (a set collapse would see no change)
# a moved control (geometry is not in the triple) is unchanged
assert not changed(B, list(B), set())
# volatile learning: same node count + changed triple -> masked; structure change is never masked
v = set(); learn_volatile(B, B[:2] + ["tab|T - Memory usage - 23.7 MB|"] + B[3:], v); assert v == {2}
assert not changed(B, B[:2] + ["tab|T - Memory usage - 24.1 MB|"] + B[3:], v)
assert changed(B, B[:2] + ["tab|OTHER PAGE|"] + B[3:], v) is False  # masked position stays masked (residual: a real change AT a volatile node is invisible -> false pause, never a wrong advance)
assert changed(B, B + ["push button|Added|"], v)
v2 = set(); learn_volatile(B, B[:3], v2); assert v2 == set()  # length change is structure
# bypass (Mac shouldBypassPostClickValidator)
assert bypass_validator({"type": "rightClick"}, None) and bypass_validator({"type": "click"}, {"type": "type"}) and bypass_validator({"type": "click"}, {"type": "scroll"})
assert not bypass_validator({"type": "click"}, {"type": "click"}) and not bypass_validator({"type": "click"}, None) and not bypass_validator({"type": "click"}, {"type": "observe"})
assert scope_app([{"rect": [0, 0, 100, 100], "app": "A"}], (5, 5)) == "A" and scope_app([], (5, 5)) is None
# ClickValidator end to end with injected walkers
def mk(seq, **kw):
    it = iter(seq); last = [None]
    def fp(_a):
        try: last[0] = next(it)
        except StopIteration: pass
        return {"triples": last[0], "truncated": False} if last[0] is not None else None
    return ClickValidator(lambda: [{"rect": [0, 0, 9, 9], "app": "A"}], fp, (1, 1), app_hint="A", gap_s=0.01, sleep_s=0.01, **kw)
def run(pre, post):
    v = mk(list(pre) + list(post)); v.start_baseline(); t0 = time.time()
    while v.idle_samples < len(pre) and time.time() - t0 < 3: time.sleep(0.005)
    # freeze sampler by marking click; the sampler reads the sequence, so feed post only after the click
    v.on_click(); v.done.wait(5); return v
# post identical to pre -> unchanged_paused
v = run([B, B, B], [B] * 8); assert v.verdict == "unchanged_paused", v.verdict
# slow counter that ticked during idle -> masked -> unchanged
C = lambda s: B[:2] + ["tab|T - Memory usage - %s MB|" % s] + B[3:]
v = run([C("23.4"), C("23.5"), C("23.5")], [C("23.6")] * 8); assert v.verdict == "unchanged_paused", (v.verdict, v.detail)
# counter that had NOT ticked while idle -> residual false 'changed' (documented)
v = run([C("23.4"), C("23.4"), C("23.4")], [C("23.6")] * 8); assert v.verdict == "changed", v.verdict
# real change (a control replaced) -> changed on two successive reads
v = run([B, B, B], [B[:3] + ["push button|Review|"]] * 8); assert v.verdict == "changed", v.verdict
# single wobble read then back -> not changed
v = run([B, B, B], [B + ["x|y|"]] + [B] * 8); assert v.verdict == "unchanged_paused", v.verdict
# click before two good samples -> unavailable
v = mk([B]); v.on_click(); v.done.wait(3); assert v.verdict.startswith("unavailable"), v.verdict
# all post reads fail -> unavailable, never unchanged
v = run([B, B, B], [None] * 8); assert v.verdict.startswith("unavailable"), v.verdict
print("validator unit ok (pure logic, injected walkers)")
