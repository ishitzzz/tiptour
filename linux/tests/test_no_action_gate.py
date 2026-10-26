import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tiptour_linux.highlight import no_action_requested as n
yes = ["What text is selected inside the area I highlighted? Quote it exactly, do not point yet.", "what does this say? don't click anything", "Read the highlighted text", "just tell me what it says", "Describe what is written here", "no action, only quote it"]
no = ["Where is the Save button?", "point to the highlighted text", "click this", "How do I save this?", "show me where to change the email", "rewrite this", "what should I click to save?", "Which text should I click?", ""]
bad = [u for u in yes if not n(u)] + [u for u in no if n(u)]
print("FAIL", bad) if bad else print("ok", len(yes) + len(no))
assert not bad
# pid gate (build_context)
from tiptour_linux.highlight import build_context
pts = [(100, 100), (300, 120), (300, 200)]
for w in (None, {"pid": "0", "rect": (0, 0, 10, 10)}, {"pid": None, "rect": (0, 0, 10, 10)}):
    c = build_context(pts, lambda p, w=w: w, lambda *a, **k: (_ for _ in ()).throw(AssertionError("probe must not run")))
    assert c["atspi_status"].startswith("unavailable"), c
c = build_context(pts, lambda p: {"pid": "7", "rect": (0, 0, 10, 10)}, lambda *a, **k: (None, None)); assert c["atspi_status"] == "ok"
print("pid gate ok")
from tiptour_linux.highlight import action_matches_intent as m
assert m("rightClick", "right click the Save button") and m("rightClick", "open the context menu on this")
assert not m("rightClick", "open the settings") and not m("rightClick", "what text is selected? do not point")
assert not m("doubleClick", "click Save") and m("doubleClick", "double-click the icon") and m("click", "click Save")
assert not m("click", "where is Save?") and not m("click", "click it, no action")
print("action intent ok")
# DOM selection fallback in build_context: never overrides an AT-SPI selection; failure is recorded, not guessed
win = lambda p: {"pid": "7", "title": "t", "rect": (0, 0, 10, 10)}
dom = lambda rect, pid: ({"text": "abc", "app": "browser tab", "role": "DOM selection", "source": "cdp_dom"}, "ok")
c = build_context(pts, win, lambda *a, **k: (None, None), selection_probe=dom); assert c["text_selection"]["source"] == "cdp_dom"
c = build_context(pts, win, lambda *a, **k: (None, {"text": "T", "app": "x", "role": "heading"}), selection_probe=dom); assert c["text_selection"]["text"] == "T"
c = build_context(pts, win, lambda *a, **k: (_ for _ in ()).throw(TimeoutError()), selection_probe=dom); assert c["atspi_status"].startswith("unavailable") and c["text_selection"]["source"] == "cdp_dom"
c = build_context(pts, win, lambda *a, **k: (None, None), selection_probe=lambda r, p: (None, "none: x")); assert c["text_selection"] is None and c["dom_selection_status"].startswith("none")
from tiptour_linux.highlight import prompt
assert "browser page text selection" in prompt(build_context(pts, win, lambda *a, **k: (None, None), selection_probe=dom))
print("dom selection fallback unit ok")
from tiptour_linux.highlight import point_authorized as pa, inside_intersection_point as ip
assert pa("point to the highlighted heading") and pa("where is this?") and not pa("quote the selected text, do not point") and not pa("rewrite this")
assert ip((26, 169, 366, 64), (44, 187, 1512, 28)) == (218, 201)
assert ip((26, 169, 366, 64), (500, 500, 50, 50)) is None and ip((26, 169, 366, 64), (390, 169, 100, 64)) is None
print("inside-intersection unit ok")
from tiptour_linux.highlight import suppressed_payload as sp
r = sp("q", {"text_selection": {"text": "A", "source": "cdp_dom"}}); assert r["selected_text"] == "A" and "DOM" in r["selected_text_source"] and "AT-SPI" not in r["selected_text_source"] and "accessibility_selected_text" not in r
r = sp("q", {"text_selection": {"text": "B", "app": "x", "role": "heading"}}); assert "AT-SPI" in r["selected_text_source"]
r = sp("q", {"text_selection": None, "atspi_status": "unavailable: probe exceeded 6s", "dom_selection_status": "none: x"}); assert "selected_text" not in r and "unavailable" in r["selected_text_note"] and "none: x" in r["selected_text_note"]
r = sp("q", None); assert "selected_text" not in r and r["ok"] is True
print("suppressed payload unit ok")
