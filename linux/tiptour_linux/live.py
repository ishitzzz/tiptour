"""Gemini Live client (port of GeminiLiveClient.swift wire protocol)."""
import asyncio, base64, json, websockets
from .keypool import classify, mask

MODEL = "models/gemini-3.1-flash-live-preview"
URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key="

import os as _os
# The Mac prompt text, verbatim (prompts/mac_system_prompt.verbatim.txt). Linux applies ONLY these explicit OS deltas (old -> new); anything else differing is a bug (tests/test_prompt_fidelity.py).
PROMPT_OS_DELTAS = [
    ("You are TipTour, a macOS menu bar voice companion.", "You are TipTour, a Linux desktop voice companion."),
    # create_note drives Apple Notes: macOS-only, no Linux equivalent is built; the tool is not declared on Linux, so its instructions are removed too.
    ("For creating an Apple Notes note with supplied content, use create_note(title, body). It is the only supported multi-action convenience tool.\n", ""),
]
# USER-AUTHORIZED DELTAS (not OS deltas; Ishit, voice notes 19:30 and 19:31 IST 26 Oct, relayed by main): the Mac prompt/schema allow exactly ONE step per submit_workflow_plan. The user chose that one spoken request may carry a multi-step task (no one-step clamp, no invented step cap) and that the assistant first classifies one-step vs several, proposes the plan (what, in what order), and executes ANY plan (one step or several) only after the user's explicit yes. The app, not this prompt, enforces that (app-owned proposal/approval gate).
USER_PROMPT_DELTAS = [
    ("with exactly ONE step, then wait for the next user utterance.",
     "as follows. First decide whether the request needs one step or several. For a natural task request, infer the necessary actions from the user goal and current screen; the user need not name click, type, or key presses. Submit the proposed plan (one step or all necessary steps in order) now using submit_workflow_plan so the app can display it for review. Submitting is only a proposal, not execution. Ground the plan in the current screenshot and named app. A task may span applications: use the native openApp step to launch the named application, never simulate the desktop launcher with clicks, search typing or Enter. Include explicit openApp steps using their destination app names, followed by the necessary ordered actions for that app. The top-level app is the current foreground source app. The app will verify each opened destination before fresh target resolution, retaining this entire approved sequence and original limits. Do not ask the user to split the task into separate commands. If the user requests a new document, include the destination app New document shortcut after openApp and before typing, because launching may activate an existing nonblank document. Do not guess destination coordinates from the source screenshot; use exact target labels or focusedElement when appropriate. Include prerequisites: typing writes to the verified focused editable field and does not focus a field from coordinates, so first propose clicking the intended field unless current app context proves it is already focused. Do not invent a search term or substitute browser in-page Find for website article search. Represent Enter as a separate pressKey step, never as newline text or backslash-n in a type value. Typing plain text alone does not submit a form. Prefer the stable Enter key after a website search query when a search button label is ambiguous. Do not reopen the app or navigate away when the requested page is already open. Explain what you propose and in what order, then ask the user to confirm the displayed plan. NEVER act right away: the app holds every action until the user says yes to that exact displayed plan. Do not require a conversational yes before submitting this nonexecuting proposal. If the user changes the plan, submit a revised proposal for a new yes. After submitting, wait for the next user utterance."),
]
USER_SCHEMA_DELTA_NOTE = "steps: maxItems 1 removed; tool/steps descriptions distinguish nonexecuting proposals from app-approved execution"
def build_system_prompt():
    text = open(_os.path.join(_os.path.dirname(__file__), "prompts", "mac_system_prompt.verbatim.txt"), encoding="utf-8").read()
    for old, new in PROMPT_OS_DELTAS + USER_PROMPT_DELTAS:
        assert old in text, "OS delta no longer matches the Mac prompt: %r" % old[:40]
        text = text.replace(old, new, 1)
    return text
SYSTEM_PROMPT = build_system_prompt()

# Tool declaration = the Mac submitWorkflowPlanTool, verbatim (prompts/mac_tool_schema.verbatim.json, extracted from GeminiLiveClient.swift by tools/extract_mac_tool_schema.py).
# OS delta: the Mac also declares create_note (Apple Notes, macOS-only); it is NOT declared on Linux and its prompt paragraph is removed (PROMPT_OS_DELTAS).
import json as _json
TOOL = _json.load(open(_os.path.join(_os.path.dirname(__file__), "prompts", "mac_tool_schema.verbatim.json"), encoding="utf-8"))["submitWorkflowPlanTool"]
def _apply_user_schema_delta(tool):
    t = _json.loads(_json.dumps(tool)); st = t["parameters"]["properties"]["steps"]
    assert st.get("maxItems") == 1, "schema delta no longer matches"
    del st["maxItems"]
    assert "Submit exactly one CUA action step" in t["description"] and st["description"].startswith("Exactly one step.")
    t["description"] = t["description"].replace("Submit exactly one CUA action step", "Propose a CUA action plan for app review (one step, or several steps; the app executes only after user confirmation)", 1).replace("Never submit a chained sequence; wait for the next screen/user turn before the next action.", "The app holds the plan until the user confirms it.", 1)
    st["description"] = st["description"].replace("Exactly one step.", "One proposed step, or several necessary proposed steps in order; app confirmation is required before execution.", 1)
    t['parameters']['properties']['requestRelation'] = {
        'type': 'string', 'enum': ['continue', 'separate', 'ambiguous'],
        'description': 'Nonexecuting interpretation of the latest words versus the prior task supplied by the app. Continue for anaphoric modifiers, refinements or restatements; separate only for an independent new goal; ambiguous when uncertain. This grants no permission and cannot remove prior limits. The app reviews any separate-task boundary with the user.'}
    return t
TOOL = _apply_user_schema_delta(TOOL)

class ConnectError(Exception):
    def __init__(self, kind, msg, retry_after=None):
        super().__init__(msg); self.kind = kind; self.retry_after = retry_after

KEEPALIVE_INTERVAL_S = 25 * 60  # Mac GeminiLiveClient.swift keepAlivePingInterval, verbatim value

class LiveClient:
    def __init__(self, on_event):
        self.ws = None; self.on_event = on_event; self.ready = asyncio.Event(); self._rx = None; self._ka = None  # _ka = Mac keepAlivePingTask
    async def connect(self, key, system_prompt=SYSTEM_PROMPT, voice="Kore"):
        try:
            self.ws = await websockets.connect(URL + key, max_size=None, open_timeout=15)
        except websockets.InvalidStatus as e:
            ra = e.response.headers.get("Retry-After")
            raise ConnectError(classify(status=e.response.status_code), "handshake HTTP %d" % e.response.status_code, float(ra) if ra and ra.isdigit() else None)
        except Exception as e:
            raise ConnectError("transient", type(e).__name__)
        setup = {"setup": {"model": MODEL,
          "generationConfig": {"responseModalities": ["AUDIO"], "mediaResolution": "MEDIA_RESOLUTION_MEDIUM",
             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
          "systemInstruction": {"parts": [{"text": system_prompt}]},
          "inputAudioTranscription": {}, "outputAudioTranscription": {},
          "contextWindowCompression": {"triggerTokens": 104857, "slidingWindow": {"targetTokens": 52428}},
          "tools": [{"functionDeclarations": [TOOL]}]}}
        await self.ws.send(json.dumps(setup))
        self._rx = asyncio.create_task(self._recv())
        try:
            await asyncio.wait_for(self.ready.wait(), 10)
        except asyncio.TimeoutError:
            code = self.ws.close_code
            raise ConnectError(classify(close_code=code), "no setupComplete (close %s)" % code)
        # Mac startKeepAlivePingLoop(): cancel any prior ping task (reconnects), then ping on a fixed cadence.
        if self._ka: self._ka.cancel()
        self._ka = asyncio.create_task(self._keepalive())
    async def _keepalive(self):
        # Mac: sleep interval, skip unless still setupComplete, send a no-op clientContent empty user turn (turnComplete=false), keep looping on send failure.
        try:
            while True:
                await asyncio.sleep(KEEPALIVE_INTERVAL_S)
                if not self.ready.is_set(): return
                try:
                    await self._send({"clientContent": {"turns": [{"role": "user", "parts": [{"text": ""}]}], "turnComplete": False}})
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass
    async def _recv(self):
        try:
            async for raw in self.ws:
                m = json.loads(raw if isinstance(raw, str) else raw.decode())
                if "setupComplete" in m: self.ready.set(); self.on_event("setupComplete", None)
                if "toolCall" in m:
                    for c in m["toolCall"].get("functionCalls", []): self.on_event("toolCall", c)
                sc = m.get("serverContent")
                if sc:
                    for p in (sc.get("modelTurn") or {}).get("parts", []):
                        if "inlineData" in p: self.on_event("audio", base64.b64decode(p["inlineData"]["data"]))
                    if "inputTranscription" in sc: self.on_event("inputTranscript", sc["inputTranscription"].get("text", ""))
                    if "outputTranscription" in sc: self.on_event("outputTranscript", sc["outputTranscription"].get("text", ""))
                    if sc.get("interrupted"): self.on_event("interrupted", None)
                    if sc.get("turnComplete"): self.on_event("turnComplete", None)
        except Exception as e:
            self.on_event("closed", repr(e)[:120])
        if self._ka: self._ka.cancel(); self._ka = None  # Mac: the ping task cancels the moment the WebSocket goes away
        self.on_event("closed", getattr(self.ws, "close_code", None))
    async def _send(self, o): await self.ws.send(json.dumps(o))
    async def send_text(self, t): await self._send({"realtimeInput": {"text": t}})
    async def send_context(self, t):
        """Seed context WITHOUT starting a model turn (clientContent, turnComplete=false; the Mac keepalive uses the same shape). realtimeInput text is treated as a user turn and makes the model answer."""
        await self._send({"clientContent": {"turns": [{"role": "user", "parts": [{"text": t}]}], "turnComplete": False}})
    async def send_history(self, turns):
        """Rehydrate a FRESH connection with the prior conversation text (clientContent, turnComplete=false, the same provider shape send_context already uses). turns = [(role, text)] with role user|model."""
        await self._send({"clientContent": {"turns": [{"role": r, "parts": [{"text": t}]} for r, t in turns], "turnComplete": False}})
    async def send_screenshot(self, jpeg): await self._send({"realtimeInput": {"video": {"data": base64.b64encode(jpeg).decode(), "mimeType": "image/jpeg"}}})
    async def send_audio(self, pcm16): await self._send({"realtimeInput": {"audio": {"data": base64.b64encode(pcm16).decode(), "mimeType": "audio/pcm;rate=16000"}}})
    async def tool_response(self, id, name, response): await self._send({"toolResponse": {"functionResponses": [{"id": id, "name": name, "response": response}]}})
    async def close(self):
        if self._ka: self._ka.cancel(); self._ka = None  # Mac disconnect(): keepAlivePingTask?.cancel()
        if self.ws: await self.ws.close()

def pool_index(pool, k):
    return 1 + [e["key"] for e in pool.keys].index(k)

async def connect_with_pool(pool, client_factory, log=print):
    """Bounded failover: each ready key tried once per round, 2 rounds."""
    tried_total = 0
    for rnd in range(2):
        tried = set()
        while True:
            k = pool.acquire(exclude=tried)
            if not k: break
            tried.add(k); tried_total += 1
            c = client_factory()
            try:
                await c.connect(k); pool.success(k); log("connected (key #%d of %d)" % (pool_index(pool, k), len(pool.keys))); return c, k
            except ConnectError as e:
                log("key #%d failed: %s (%s)" % (pool_index(pool, k), e.kind, e))
                if e.kind == "request_error": raise
                pool.report(k, e.kind, e.retry_after)
    nr = pool.next_retry()
    raise RuntimeError("no usable key; keys=%d next_retry_in=%s" % (len(pool.keys), None if nr is None else int(nr - __import__("time").time())))
