import sys; sys.path.insert(0, ".")
from tiptour_linux.ask import SessionGate, is_ask_chord, insert_draft, Clipboard
from tiptour_linux import highlight as h
g = SessionGate(); a = g.begin(); assert a == 1 and g.begin() is None
assert g.begin_finish() == 1 and g.begin() is None  # busy while finishing
assert g.may_publish(1); g.cancel(); assert not g.may_publish(1)  # cancelled while finishing: stale
g.finished(); b = g.begin(); assert b == 3
g.cancel(); assert g.phase == "idle" and g.begin_finish() is None
assert is_ask_chord(h.CTRL | h.ALT | h.SHIFT) and not is_ask_chord(h.CTRL | h.ALT) and not is_ask_chord(h.CTRL | h.SHIFT) and not is_ask_chord(h.CTRL | h.ALT | h.SHIFT | h.SUPER)
assert insert_draft(Clipboard(), "x", None).startswith("refused")
print("ask core tests ok")
