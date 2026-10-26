# Controlled regression (NO model, NO browser): the auditor's case. Region = top-right Donate/Create account/Login strip,
# resolved target = "$2.75" banner button 216px below it. Pure-function check of the guard; not an accuracy test.
import sys; sys.path.insert(0, "..")
from tiptour_linux.highlight import outside_scope, refers_to_highlight
region = (1318, 40, 260, 60)
below = (1440, 100 + 216)
inside = (1400, 70)
assert outside_scope("Point to the highlighted button", region, below)
assert not outside_scope("Point to the highlighted button", region, inside)
assert not outside_scope("Where is the donation amount?", region, below)       # unrelated ask is not locked
assert outside_scope("click this area's button", region, below)
assert not refers_to_highlight("point to the search box")
from tiptour_linux.highlight import outside_window
ctx = {"window": {"title": "A", "rect": [0, 0, 800, 600]}}
assert outside_window("point to the highlighted button", ctx, (900, 100))
assert not outside_window("point to the highlighted button", ctx, (100, 100))
assert not outside_window("open the taskbar menu", ctx, (900, 100))   # unrelated ask may leave the window
print("scope guard regression OK")
