"""Offline logic tests for the Python key pool (no network, fake clock). Mirrors policy in docs/gemini-key-pool.md."""
import sys, asyncio; sys.path.insert(0, "linux")
from tiptour_linux.keypool import KeyPool, classify
from tiptour_linux.live import ConnectError, connect_with_pool
t = [1000.0]; clk = lambda: t[0]
assert classify(status=429) == "rate_limited" and classify(status=402) == "billing" and classify(status=403) == "rejected" and classify(status=400) == "request_error" and classify(status=503) == "transient" and classify(close_code=1011) == "rate_limited" and classify(close_code=1008) == "rejected"
p = KeyPool(["A", "B", "C"], clock=clk)
assert p.acquire() == "A"; p.report("A", "rate_limited", retry_after=60); assert p.acquire() == "B"
p.report("B", "rejected"); assert p.acquire() == "C"; p.report("C", "rate_limited", retry_after=30)
assert p.acquire() is None and abs(p.next_retry() - 1030) < 1
t[0] = 1031; assert p.acquire() == "C"; t[0] = 1061; assert p.acquire() == "A"; assert [s for s in p.status() if "parked" in s[1]]
# failover through connect_with_pool: first key 429, second works
class Fake:
    def __init__(self, bad): self.bad = bad
    async def connect(self, k):
        if k in self.bad: raise ConnectError(self.bad[k], "x")
q = KeyPool(["K1", "K2"], clock=clk); logs = []
c, k = asyncio.run(connect_with_pool(q, lambda: Fake({"K1": "rate_limited"}), lambda m: logs.append(m))); assert k == "K2"
q2 = KeyPool(["K1"], clock=clk)
try: asyncio.run(connect_with_pool(q2, lambda: Fake({"K1": "rate_limited"}), lambda m: None)); raise SystemExit("should fail")
except RuntimeError as e: assert "no usable key" in str(e)
try: asyncio.run(connect_with_pool(KeyPool(["K1", "K2"], clock=clk), lambda: Fake({"K1": "request_error"}), lambda m: None)); raise SystemExit("should raise")
except ConnectError as e: assert e.kind == "request_error"
print("keypool tests OK")
