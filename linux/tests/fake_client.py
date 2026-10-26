"""Local stand-in for the Gemini Live client (TEST ONLY, no network, no model). Use: TIPTOUR_CLIENT_FACTORY=fake_client:make PYTHONPATH=linux/tests
It is NOT a model: answers are canned. It exists to exercise capture/commit/AT-SPI/overlay paths and to verify the toolCall/toolResponse wire locally.
With TIPTOUR_FAKE_TOOLCALL=1 it replies to a user utterance containing 'quote' with a click toolCall and records the toolResponse to $TIPTOUR_FAKE_LOG."""
import json, os

class Fake:
    def __init__(self, on_event, loop, log): self.on_event, self.loop, self.log, self.ctx_seen = on_event, loop, log, 0
    def _args_for(self, t):  # TIPTOUR_FAKE_STEPS='{"save":"Save changes"}': utterance keyword -> label (point_2d is a deliberately rough placeholder; resolvers must bind the real element)
        m = json.loads(os.environ.get("TIPTOUR_FAKE_STEPS", "{}"))
        for k, lab in m.items():
            if k in t.lower(): return {"steps": [{"point_2d": ([248, 56] if "staleb" in t.lower() else [500, 500]), "label": lab, "type": "click"}]}  # staleb: model point is ON the real target (frame px 107,268)
        return {"steps": [{"point_2d": [186, 109], "label": "Account preferences (test page)", "type": "click"}]}
    async def send_context(self, t): pass
    async def send_text(self, t):
        self.log("FAKE send_text %d chars" % len(t))
        if os.environ.get("TIPTOUR_FAKE_TOOLCALL") == "1" and t.startswith("user focus highlight context"):
            self.ctx_seen += 1
            if self.ctx_seen > 1: return  # the per-utterance context re-send does not complete a turn (like the real model)
        if os.environ.get("TIPTOUR_FAKE_TOOLCALL") == "1" and os.environ.get("TIPTOUR_FAKE_TRIGGER", "quote") in t.lower() and not t.startswith("user focus"):
            self.loop.call_later((float(os.environ.get("TIPTOUR_FAKE_DELAY", "8")) if "stale" in t.lower() else 0.1), self.on_event, "toolCall", {"id": "fake1", "name": "submit_workflow_plan", "args": self._args_for(t)})
        else: self.loop.call_later(0.1, self.on_event, "turnComplete", {})
    async def send_screenshot(self, j): pass
    async def send_audio(self, p): pass
    async def tool_response(self, id, name, response):
        open(os.environ.get("TIPTOUR_FAKE_LOG", "/tmp/fake_toolresp.json"), "w").write(json.dumps(response))
        if os.environ.get("TIPTOUR_FAKE_LATE") == "1":  # protocol-shape test: the answer to turn 1 arrives AFTER the 12s wait, i.e. during the next ask
            self.loop.call_later(0.1, self.on_event, "turnComplete", {}); self.loop.call_later(float(os.environ.get("TIPTOUR_FAKE_LATE_S", "15")), self.on_event, "outputTranscript", "(canned) STALE answer from turn 1"); self.loop.call_later(float(os.environ.get("TIPTOUR_FAKE_LATE_S", "15")) + 0.2, self.on_event, "turnComplete", {})
        elif os.environ.get("TIPTOUR_FAKE_EARLY_TC") == "1":  # protocol-shape test: a turnComplete arrives BEFORE the spoken answer
            self.loop.call_later(0.1, self.on_event, "turnComplete", {}); self.loop.call_later(1.5, self.on_event, "outputTranscript", "(canned) late answer"); self.loop.call_later(1.7, self.on_event, "turnComplete", {})
        else:
            self.loop.call_later(0.1, self.on_event, "outputTranscript", "(canned) reply after tool response"); self.loop.call_later(0.2, self.on_event, "turnComplete", {})
    async def close(self): pass

def make(on_event, loop, log): return Fake(on_event, loop, log)
