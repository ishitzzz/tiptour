"""Owned test window that covers a given screen rect (stands in for 'another app overlapping the target'). usage: overlap_window.py x y w h seconds"""
import sys, time
from Xlib import display, X
x, y, w, h, secs = map(int, sys.argv[1:6])
d = display.Display(); s = d.screen()
win = s.root.create_window(x, y, w, h, 0, s.root_depth, X.InputOutput, X.CopyFromParent, background_pixel=0x3366cc)
win.set_wm_name("ownedOverlap"); win.set_wm_class("ownedOverlap", "ownedOverlap"); win.map(); d.sync()
t0 = time.time()
while time.time() - t0 < secs:
    while d.pending_events(): d.next_event()
    time.sleep(0.05)
