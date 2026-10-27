"""Thread-safe local gesture ownership. Tokens never confer user approval."""
import concurrent.futures
import threading

class Owner:
    def __init__(self):
        self.lock = threading.RLock(); self.epoch = 0; self.closed = False; self.blocked = False
        self.visible = False; self.jobs = {}; self.context = None; self.cancel = None
        self.suppressed = 0; self.points = []
    def valid(self, token):
        with self.lock: return not self.closed and token == self.epoch and not self.blocked
    def invalidate(self, close=False, retire_context=True):
        with self.lock:
            if self.cancel and not self.cancel.done(): self.cancel.set_result(None)
            if retire_context: self.context = None
            self.epoch += 1; self.blocked = True; self.visible = False; self.closed |= close
            for f in self.jobs.values():
                if not f.done(): f.set_result((None, False))
            self.jobs.clear()
    def released(self):
        with self.lock:
            if not self.closed: self.blocked = False
    def begin(self):
        with self.lock:
            if self.closed or self.blocked: return None
            self.invalidate(); self.blocked = False; self.visible = True
            self.cancel = concurrent.futures.Future(); self.points = []
            return self.epoch
    def job(self, token):
        with self.lock:
            if not self.valid(token): return None
            f = concurrent.futures.Future(); self.jobs[token] = f; return f
    def publish(self, token, value):
        with self.lock:
            f = self.jobs.get(token)
            if self.valid(token) and f and not f.done(): f.set_result(value); return True
            return False
    def take(self, token):
        with self.lock: return self.jobs.get(token)

    def cancellation(self, token):
        with self.lock:
            if self.valid(token): return self.cancel
            f = concurrent.futures.Future(); f.set_result(None); return f
    def commit(self, token, context):
        with self.lock:
            if not self.valid(token): return False
            self.context = context; return True
    def committed(self):
        with self.lock: return self.context
    def bind(self, fn):
        with self.lock: return fn(self.context)
