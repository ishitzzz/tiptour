# TEST-ONLY (loaded via PYTHONPATH by run_stalled_capture.sh only): wraps tiptour_linux.capture.grab so ONE grab after $O/arm_stall exists blocks (in whatever thread calls it) until $O/release exists (max 25s). Records enter/leave in $O/stall_events.txt. No product code change.
import os, time, threading
O = os.environ.get("O")
if O and os.environ.get("TIPTOUR_TEST_STALL") == "1":
    import sys; sys.path.insert(0, os.getcwd())
    from tiptour_linux import capture as _c
    _orig = _c.grab; _st = {"done": False}; _lk = threading.Lock()
    def _grab(*a, **k):
        go = False
        with _lk:
            if not _st["done"] and os.path.exists(O + "/arm_stall"): _st["done"] = True; go = True
        if go:
            open(O + "/stall_events.txt", "a").write("%.3f grab STALLED thread=%s\n" % (time.time(), threading.current_thread().name))
            t0 = time.time()
            while not os.path.exists(O + "/release") and time.time() - t0 < 25: time.sleep(0.05)
            open(O + "/stall_events.txt", "a").write("%.3f grab RELEASED after %.2fs\n" % (time.time(), time.time() - t0))
        return _orig(*a, **k)
    _c.grab = _grab
