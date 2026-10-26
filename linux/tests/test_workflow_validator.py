import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tiptour_linux.workflow import fingerprint, fingerprint_of, scope_app, validate_changed
T = [{"app": "A", "role": "push button", "label": "Save", "rect": [10, 10, 50, 20]}]
f1 = fingerprint(lambda timeout: T, 'A')
T2 = T + [{"app": "A", "role": "push button", "label": "Confirm", "rect": [10, 40, 50, 20]}]
f2 = fingerprint(lambda timeout: T2, 'A')
assert f1 and f2 and f1 != f2 and f1 == fingerprint(lambda timeout: list(T), 'A')
assert fingerprint(lambda timeout: [], 'A') is None
seq = iter([f1, f1, f2])
assert validate_changed(f1, lambda: next(seq), sleep=lambda s: None) is True
assert validate_changed(f1, lambda: f1, sleep=lambda s: None) is False
assert validate_changed(None, lambda: f1) is None
print("workflow validator unit ok (pure logic, fake AT-SPI data; real AT-SPI run is separate)")

# scope: an unrelated app changing must not change the fingerprint of the target app
U = T + [{"app": "B", "role": "push button", "label": "Other", "rect": [300, 10, 50, 20]}]
U2 = U + [{"app": "B", "role": "push button", "label": "New in B", "rect": [300, 40, 50, 20]}]
assert fingerprint_of(U, "A") == fingerprint_of(U2, "A") and fingerprint_of(U, "B") != fingerprint_of(U2, "B")
assert scope_app(U, (20, 15)) == "A" and scope_app(U, (5000, 5)) is None and fingerprint_of(U, None) is None
print("scope unit ok")

from tiptour_linux.workflow import stable_pre, validate_items, ClickValidator
import threading, time
A=[("b","Save",(1,1,2,2)),("b","wobble",(5,5,2,2))]; B=[("b","Save",(1,1,2,2))]
st,no=stable_pre(A,B); assert st=={("b","Save",(1,1,2,2))} and no=={("b","wobble",(5,5,2,2))}
nos=lambda s: None
assert validate_items(st,no,lambda:A,sleep=nos)[0] is False
assert validate_items(st,no,lambda:B+[("b","Confirm",(9,9,2,2))],sleep=nos)[0] is True
assert validate_items(set(),set(),lambda:B)[0] is None
assert validate_items(st,no,lambda:None,sleep=nos)[0] is None          # ALL post reads failed -> unavailable, never 'unchanged'
seq=iter([None,None,A,A,A,A]); assert validate_items(st,no,lambda:next(seq),sleep=nos)[0] is False  # some reads ok, none changed
def T(app,label,r=(10,10,50,20)): return {"app":app,"role":"push button","label":label,"rect":list(r)}
base=[T("A","Save")]
def mk(walk_app, hint="A", **kw): 
    v=ClickValidator(lambda: base, walk_app, (20,15), app_hint=hint, gap_s=0.01, sleep_s=0.01, **kw); return v
v=mk(lambda n: base); v.start_baseline(); v.ready.wait(2); v.on_click(); assert v.join(3)=="unchanged_paused", v.verdict
cur=[base]; v=mk(lambda n: cur[0]); v.start_baseline(); v.ready.wait(2); cur[0]=base+[T("A","Confirm",(10,40,50,20))]; v.on_click(); assert v.join(3)=="changed"
gate=threading.Event()
def slow(n): gate.wait(3); return base
v=mk(slow); v.start_baseline(); v.on_click(); r=v.join(3); assert r.startswith("unavailable:click_before_baseline"), r   # click before baseline: unverified, post-click never becomes the baseline
gate.set()
state=["ok"]
def flaky(n):
    if state[0]=="fail": raise TimeoutError("x")
    return base
v=mk(flaky); v.start_baseline(); v.ready.wait(2); state[0]="fail"; v.on_click(); assert v.join(3)=="unavailable:all_post_reads_failed", v.verdict
v=ClickValidator(lambda: base, lambda n: base, (900,900), app_hint=None, gap_s=0.01); v.start_baseline(); v.ready.wait(2); v.on_click(); assert v.join(3)=="unavailable:no_atspi_control_at_target_point", v.verdict
v=ClickValidator(lambda: base, lambda n: (time.sleep(5) or base), (20,15), app_hint="A"); v.start_baseline(); v.ready.wait(0.1); v.on_click(); assert v.join(0.3).startswith("unavailable:click_before") or v.join(0.3)=="pending_at_shutdown"
empties=iter([[],[],base,base,base,base,base])
v=mk(lambda n: next(empties)); v.start_baseline(); v.ready.wait(3); v.on_click(); assert v.join(3)=="unchanged_paused", v.verdict   # empty first reads retried, not treated as baseline
v=mk(lambda n: []); v.start_baseline(); v.ready.wait(3); v.on_click(); assert v.join(3)=="unavailable:empty_baseline"
print("stable/noise + ClickValidator unit ok (pure logic, injected walkers)")

# transient single-read wobble must not read 'changed'; a persistent identical difference must
from tiptour_linux.workflow import validate_items as _vi
_st = frozenset({("b", "A", (1, 1, 1, 1)), ("b", "B", (2, 2, 2, 2))})
_w = iter([set(_st) - {("b", "B", (2, 2, 2, 2))}] + [set(_st)] * 6)
assert _vi(_st, frozenset(), lambda: next(_w), sleep=lambda s: None)[0] is False
_p = iter([set(_st) | {("b", "C", (3, 3, 3, 3))}] * 6)
assert _vi(_st, frozenset(), lambda: next(_p), sleep=lambda s: None)[0] is True
print("transient-wobble confirmation unit ok")
