"""Owns the X11 CLIPBOARD with two formats (text/html + UTF8_STRING) for 15 s, via python-xlib, to test multi-format refusal."""
import time
from Xlib import X, display, Xatom
from Xlib.protocol import event
d = display.Display(); w = d.screen().root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
CB, TG, HT, UT = (d.intern_atom(n) for n in ("CLIPBOARD", "TARGETS", "text/html", "UTF8_STRING"))
data = {HT: b"<b>rich</b>", UT: b"plain rich"}
w.set_selection_owner(CB, X.CurrentTime); d.flush(); end = time.time() + 15
while time.time() < end:
    while d.pending_events():
        e = d.next_event()
        if e.type == X.SelectionRequest:
            prop = e.property or e.target
            if e.target == TG: e.requestor.change_property(prop, Xatom.ATOM, 32, [TG, HT, UT])
            elif e.target in data: e.requestor.change_property(prop, e.target, 8, data[e.target])
            else: prop = X.NONE
            n = event.SelectionNotify(time=e.time, requestor=e.requestor, selection=e.selection, target=e.target, property=prop); e.requestor.send_event(n); d.flush()
    time.sleep(0.02)
