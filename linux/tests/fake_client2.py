"""TEST-ONLY extension of fake_client: besides the first toolCall (id fake1, now with an explicit `goal` from TIPTOUR_FAKE_GOAL1), schedules EXTRA toolCalls in the same turn:
TIPTOUR_FAKE_EXTRA='[{"id":"fake2","delay":0.4,"goal":"G2","labels":["Open settings"],"types":["click"]}]' (delay seconds after the FIRST tool_response is sent). Unique ids/goals/labels let the oracle correlate cancel / old advance / new render."""
import os, json
import fake_client as _f

_VS = {"n": 1, "ready": True}
class Fake2(_f.Fake):
    async def tool_response(self, id, name, response):
        await super().tool_response(id, name, response)
        if id == "fake1" and os.environ.get("TIPTOUR_FAKE_TOOLCALL") == "1":  # extras are timed from the FIRST tool_response (Linux has just rendered step 1; the default fake turnComplete follows 0.2s later), so delay<=0.15 lands BEFORE turnComplete and inside the 650ms observe hold
            for e in json.loads(os.environ.get("TIPTOUR_FAKE_EXTRA", "[]")):
                if e.get("transcript"): self.loop.call_later(float(e.get("delay", 0.1)), self.on_event, "inputTranscript", e["transcript"]); continue  # TEST-ONLY: an input transcript chunk mid-turn
                args = {"goal": e.get("goal", ""), "steps": [{"point_2d": [500, 500], "label": l, "type": (e.get("types") or ["click"] * 9)[i]} for i, l in enumerate(e["labels"])]}
                self.loop.call_later(float(e.get("delay", 0.1)), self.on_event, "toolCall", {"id": e["id"], "name": "submit_workflow_plan", "args": args})
    async def send_screenshot(self, j):  # TEST-ONLY voice ordering simulation: the app sends the ask-start screenshot of a voice turn; then TIPTOUR_FAKE_VOICE_SCRIPT events fire (toolCall BEFORE the transcript, etc.)
        # one script per voice TURN: script N+1 fires at the first screenshot after script N's turnComplete was delivered (extra mid-turn screenshots do not consume scripts)
        if not hasattr(self, "_vs_n"): self._vs_n = _VS["n"]; self._vs_ready = _VS["ready"]  # script progress survives a fresh client (per-PTT reconnect)
        if not self._vs_ready: return
        sc = os.environ.get("TIPTOUR_FAKE_VOICE_SCRIPT" + ("" if self._vs_n == 1 else str(self._vs_n)))
        if sc:
            self._vs_ready = False; self._vs_n += 1; _VS["n"] = self._vs_n; _VS["ready"] = False
            for e in json.loads(sc):
                if e.get("transcript") is not None: self.loop.call_later(float(e.get("delay", 0.1)), self.on_event, "inputTranscript", e["transcript"]); continue
                if e.get("output") is not None: self.loop.call_later(float(e.get("delay", 0.1)), self.on_event, "outputTranscript", e["output"]); continue  # TEST-ONLY: MODEL-side text (must never act as the user's answer)
                if e.get("ltype"):  # TEST-ONLY: a late callback (origin epoch captured, an off edge runs before its delivery)
                    self.loop.call_later(float(e.get("delay", 0.1)), self.on_event, "__late", (e["ltype"], e.get("ltext", {}) if e["ltype"] == "inputTranscript" else {})); continue
                if e.get("closed"): self.loop.call_later(float(e.get("delay", 0.1)), self.on_event, "closed", "test close"); continue  # TEST-ONLY: socket closed (taints the session)
                if e.get("unknown_tool"): self.loop.call_later(float(e.get("delay", 0.1)), self.on_event, "toolCall", {"id": e["id"], "name": e["unknown_tool"], "args": {"x": 1, "label": "Open settings", "point_2d": [500, 500]}}); continue
                if e.get("turnComplete"): self.loop.call_later(float(e.get("delay", 0.1)), lambda: ((setattr(self, "_vs_ready", True), _VS.__setitem__("ready", True)), self.on_event("turnComplete", {}))); continue
                args = {"goal": e.get("goal", ""), "steps": [{"point_2d": [500, 500], "label": l, "type": (e.get("types") or ["observe"] * 9)[i]} for i, l in enumerate(e["labels"])]}
                self.loop.call_later(float(e.get("delay", 0.1)), self.on_event, "toolCall", {"id": e["id"], "name": "submit_workflow_plan", "args": args})
    def _args_for(self, t):
        a = super()._args_for(t)
        if os.environ.get("TIPTOUR_FAKE_GOAL1") and isinstance(a, dict): a = {**a, "goal": os.environ["TIPTOUR_FAKE_GOAL1"]}
        gm = json.loads(os.environ.get("TIPTOUR_FAKE_GOALS", "{}"))  # keyword in the utterance -> explicit goal (later-utterance gate tests)
        for k, g in gm.items():
            if k in t.lower() and isinstance(a, dict): a = {**a, "goal": g}
        return a

def make(on_event, loop, log): return Fake2(on_event, loop, log)
