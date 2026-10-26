# TEST-ONLY (PYTHONPATH, run_stale_perceive.sh only): (1) wraps tiptour_linux.perception.ocr so ONE call after $O/arm_stall exists blocks until $O/release (max 30s), logging thread; (2) wraps LocalPerceptionTargetCache.update to log every call that reaches the cache (time, thread, n elements) to $O/cache_updates.txt. No product change.
import os, sys, time, threading
O = os.environ.get("O")
if O and os.environ.get("TIPTOUR_TEST_STALL") == "1":
    sys.path.insert(0, os.getcwd())
    from tiptour_linux import perception as _p
    from tiptour_linux import target_cache as _tc
    _o = _p.ocr; _st = {"done": False}; _lk = threading.Lock()
    def _ocr(*a, **k):
        go = False
        with _lk:
            if not _st["done"] and os.path.exists(O + "/arm_stall"): _st["done"] = True; go = True
        if go:
            open(O + "/stall_events.txt", "a").write("%.3f ocr STALLED thread=%s\n" % (time.time(), threading.current_thread().name))
            t0 = time.time()
            while not os.path.exists(O + "/release") and time.time() - t0 < 30: time.sleep(0.05)
            open(O + "/stall_events.txt", "a").write("%.3f ocr RELEASED after %.2fs\n" % (time.time(), time.time() - t0))
        return _o(*a, **k)
    _p.ocr = _ocr
    _u = _tc.LocalPerceptionTargetCache.update
    def _upd(self, elements, *a, **k):
        open(O + "/cache_updates.txt", "a").write("%.3f cache.update thread=%s n=%d\n" % (time.time(), threading.current_thread().name, len(elements)))
        return _u(self, elements, *a, **k)
    _tc.LocalPerceptionTargetCache.update = _upd
