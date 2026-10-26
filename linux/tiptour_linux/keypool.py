"""Gemini key pool: port of TipTour/Voice/GeminiKeyPool.swift failure policy.
Keys are loaded from files/env, never printed (masked last 4 only)."""
import random, time, threading

def mask(k): return "…" + k[-4:]

def classify(status=None, close_code=None, text=""):
    t = (text or "").lower()
    if status == 429 or close_code == 1011 or "quota" in t or "resource_exhausted" in t:
        return "rate_limited"
    if status == 402: return "billing"
    if status in (401, 403) or close_code == 1008: return "rejected"
    if status in (400, 404): return "request_error"
    return "transient"

class KeyPool:
    def __init__(self, keys, clock=time.time):
        self.keys = [{"key": k, "until": 0.0, "parked": False, "n429": 0, "ntrans": 0} for k in keys]
        self.clock = clock; self.lock = threading.Lock()
    def acquire(self, exclude=()):
        now = self.clock()
        with self.lock:
            for e in self.keys:
                if e["parked"] or e["key"] in exclude or e["until"] > now: continue
                return e["key"]
        return None
    def next_retry(self):
        with self.lock:
            c = [e["until"] for e in self.keys if not e["parked"] and e["until"] > self.clock()]
            return min(c) if c else None
    def success(self, key):
        with self.lock:
            for e in self.keys:
                if e["key"] == key: e["n429"] = e["ntrans"] = 0
    def report(self, key, kind, retry_after=None):
        with self.lock:
            for e in self.keys:
                if e["key"] != key: continue
                if kind == "rate_limited":
                    e["n429"] += 1
                    back = min(20 * 2 ** (e["n429"] - 1), 3600)
                    e["until"] = self.clock() + (retry_after or back * random.uniform(0.8, 1.2))
                elif kind in ("billing", "rejected"):
                    e["parked"] = True
                elif kind == "transient":
                    e["ntrans"] += 1
                    if e["ntrans"] >= 3:
                        e["until"] = self.clock() + min(5 * 2 ** (e["ntrans"] - 3), 60)
    def status(self):
        now = self.clock()
        return [(mask(e["key"]), "parked" if e["parked"] else ("cooling %ds" % (e["until"] - now) if e["until"] > now else "ready")) for e in self.keys]
