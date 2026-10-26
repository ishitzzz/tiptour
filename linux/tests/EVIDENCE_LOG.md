> HISTORICAL checkpoint log (append-only, written during the port). Early sections contain statements that were later superseded or corrected (e.g. "NOT IMPLEMENTED" rows, an invalid 04:27-04:30 isolated-None result, a wrong claim about the 04:49 run in the first bundle20 note). The current status is in ../PARITY.md.

# Linux port parity matrix (branch feature/linux-port, base 6e97782). Python/GTK3 reimplementation, NOT the Swift app.
Status words: RAN = executed here with output evidence; PORTED = code exists, only partly exercised; OPEN = not done.

| Area (Mac source) | Linux status | Evidence / gap |
|---|---|---|
| Gemini Live wire protocol (GeminiLiveClient) | RAN | real session, text turns, audio reply + transcripts + toolCall; no microphone path, no audio playback |
| Key pool + failover (GeminiKeyPool) | PORTED | offline logic tests (mock/fake clock); real connect via pool used; failover under real 429 not observed |
| submit_workflow_plan tool decl | PORTED | same schema minus macOS-only fields (targetContext, direction/amount/by); create_note not ported (Apple Notes) |
| Screen capture (ScreenCaptureKit) | RAN (X11 only) | PIL ImageGrab on Xvfb; no Wayland, no multi-display, no HiDPI test |
| Overlay cursor (OverlayWindow CursorArrowShape) | PORTED | exact path/colors/size; rotation, breathing, Neko, blur glow (needs compositor) not verified; landing hotspot vs Mac unverified |
| Bubble | PORTED | style from source; no pop-in animation |
| YOLO11m icon detector (CoreML) | RAN, parity OPEN | same weights via MIL->ONNX (sha256 f76a3bf4..eabb60), scaleFill, NMS re-implemented; no Mac reference -> numerical identity UNVERIFIED (see mac-reference/) |
| OCR (Apple Vision accurate, conf>=0.4) | PORTED, different engine | tesseract 2x upscale; weaker on small UI text; RapidOCR untested |
| refineCoordinate snap rules | PORTED | exact rules; exercised on labeled test window (4/4) |
| AX tree (AccessibilityTreeResolver) | PORTED (AT-SPI) | works for GTK test app (Save via AT-SPI); not tested on Electron/Qt/web; AT-SPI typelib extracted locally from jammy .deb |
| Browser DOM/CDP resolver (CUA) | PARTIAL | Generic JS element enumeration over CDP 9222-9230 (not the cua library). Differs from Mac: own scoring (exact 3 / contained label with >=50% length 2 / all tokens 1), no nearest-model-hint choice; >1 distinct best match = ambiguous, falls through and the final source is logged model_box(UNCONFIRMED); binds only when the X11 focused window's PID equals the CDP browser process (xdotool getwindowfocus/getwindowpid vs SystemInfo.getProcessInfo; requires a window manager, tests use xfwm4) and then to the focused visible page (or the single visible page), else fails closed (when gated by a wrong foreground app and the model point lies inside a visible browser window rect, the point is REFUSED rather than drawn; outside it, YOLO/raw still run on the actual screenshot); >1 distinct on-screen DOM or AT-SPI match, or a known DOM target scrolled out of view, REFUSES (no cursor drawn, tool response status not_pointed, results source REFUSED); when no stage knows the target (e.g. diagram images) the raw Gemini point is still drawn and is NOT confirmed; dpr!=1 fails closed; no target-app gating, no iframe/shadow-DOM/transform coverage, X11-only window-origin math (screenX/Y + outer-inner height). |
| Local target cache / exact IDs / continuity | OPEN | |
| Action execution (click/type/scroll) | OPEN | point-only mode only |
| Ask harness, clipboard handoff, scribble | OPEN | |
| JEV/TypeSafe(+OpenRouter) | OPEN | |
| Tutorials / Elorian | OPEN | |
| Hotkeys, push-to-talk, menu bar UI, settings, onboarding | OPEN | |
| Local harness server 127.0.0.1:19474 | OPEN | |
| Windows | NOT STARTED | gated on Linux pass |

## Tests (all need network + Gemini keys in files matching $TIPTOUR_KEYS_GLOB; no keys in repo)
- Offline: `python3 linux/tests/test_keypool.py`
- Convert detector: `python3 linux/tools/mil_to_onnx.py TipTour/UIElementDetector.mlpackage /tmp/uielement.onnx`
- Detector-only: `python3 linux/tools/dump_detections.py /tmp/uielement.onnx linux/mac-reference/icons.png`
- Live e2e (Xvfb+AT-SPI): `VERIFY="Save Cancel Preferences Help" linux/tests/run_e2e.sh --ask "Where is the Save button? Point to it." --ask "Now point to the Cancel button." --ask "Now point to Preferences." --ask "Now point to Help."`
- Label-free random: `TARGET=target_icons.py SEED=1 VERIFY="Delete Print Search" linux/tests/run_e2e.sh --ask "Point to the trash can / delete icon." --ask "Point to the printer icon." --ask "Point to the magnifying glass search icon."`
Tests assert tip inside the real GTK widget rect (rect from GTK geometry, not hardcoded in the app). Mac reference: see mac-reference/dump_detector.swift (untested) then `tools/compare_detections.py mac.json linux.json`.
Licensing facts (not legal advice): detector metadata says Ultralytics YOLO11m, AGPL-3.0; repo license MIT per source; NekoSprites BSD-2 (LICENSE-NEKO.txt).

## Ctrl+Shift focus highlight (source: GlobalHighlightShortcutMonitor.swift, CompanionManager.swift 1816-2030, FocusHighlightContext.swift)
| Piece | Status |
|---|---|
| Held-chord detection (Ctrl+Shift, no Option/Super), >=3px sampling, 12px padded bbox min 4x4, >=2 points | PORTED in highlight.py (X11 XQueryPointer poll, listen-only). Tested ONLY with xdotool-simulated keys/motion on Xvfb, no real keyboard |
| Option present at release = ask-chord provenance (trail stays local) | Detection ported; the local-only handling of the trail exists only as a flag, no harness/provider path ported |
| Hovered window context (title/pid/frame) | PARTIAL: xdotool window under pointer; top-level X window only, no app bundle id |
| Intersected AX element, selected text/range | NOT IMPLEMENTED (AT-SPI Text selection layer absent; element probe is a hook, not wired) |
| Prompt text to Gemini + FRESH screenshot on non-chord release + ack request | Prompt builder ported (highlight.prompt). NOT wired into app.py, not sent to Gemini, not tested live |
| Trail drawn on overlay | NOT IMPLEMENTED |
| Wayland | Not possible with polling; refuses |

## Highlight scope guard (3:10 IST checkpoint)
- Every grounding source (AT-SPI, CDP, YOLO+OCR, raw) is checked against the highlight region when the USER utterance refers to it. Unit-regression only: tests/test_scope_guard.py (no model, no browser; not an accuracy test).
- Live run tests/run_serve_scope.sh (real Chrome + Gemini, virtual X11): model picked "Hide" at an off-screen coordinate; refused as ambiguous by the CDP stage BEFORE the scope guard. Guard not exercised live. Original auditor counterexample not reproduced.
- Not done: filtering candidates to the region before ambiguity, original-window confinement, AT-SPI metadata/selection, varied control types.
- Stream no longer hides a visible cursor every second (flicker/race fix, untested visually by me). Render log line added ("render cursor at").

## Varied controls on an OWNED local page (3:15-3:18 IST; real Chrome + real Gemini; virtual X11; point-only; gesture n/a)
Page: tests/ (served by python http.server; checkbox, role=switch, select, text input, icon-only buttons, Save/Cancel).
Resolver changes: label-associated names (label[for]/aria-labelledby), control-type words ignored, name+descriptive-tail match, label wrapper skipped when it has a control.
Results (tester-only CDP truth + real X pointer): checkbox OK, switch OK, text field OK (one run; an earlier run missed because of label wording), gear (aria-label) OK, Save OK, Cancel OK.
Fail/unconfirmed: country <select> (model label "select country or region" or varying; raw "?" guess, outside), trash icon with NO accessible name (raw "?" guess outside, YOLO+OCR did not refine it).
Verifier bug found and fixed: real_pointer used a querySelector fallback so a container row gave a false MATCH (trash). Earlier "MATCH" values that also reported inside=True are unaffected; any MATCH with inside=False before this fix should be disregarded.
Stream tradeoff: Linux pauses the 1fps stream while the cursor is visible (Mac streams continuously); per-ask frames are captured with the cursor hidden.

## AT-SPI element + text-selection context (3:25 IST)
Implemented: atspi_resolver.probe(rect) -> (element, selection); wired into the Ctrl+Shift context and prompt (element line + "accessibility text selection intersecting the highlight" line).
Real test (tests/atspi_chrome_probe.sh; real Chrome, real AT-SPI bus, X11 virtual; selection set via CDP setSelectionRange, probe called directly, NOT through a Gemini turn):
 - Element: region over the checkbox -> check box "Subscribe to newsletter"; region over email field -> entry "Email address". Empty region -> none.
 - Selection: selected text inside an <input> ("owned world") returned correctly as role=entry.
 - Selection in normal page text (label) is NOT exposed by Chrome at the leaf: the document node reports only the object-replacement char, which is filtered. So selected page text is NOT delivered. Gap.
 - Chrome registers on the a11y bus only with ACCESSIBILITY_ENABLED=1 in its environment (or the screen-reader flag); without it only the window manager appears. A release must set this when it launches the browser, or tell the user to; it is a setup requirement.
 - Not yet exercised end-to-end through a Gemini highlight turn. Not tested: GTK/Qt/Electron apps, probe latency on big trees (max_nodes=4000 cap).
Window confinement: NOT implemented.

## Highlight + AT-SPI through real Gemini turns, window confinement (3:40 IST)
Window confinement: rect-only (highlight-scoped requests must resolve inside the window rect the highlight was painted over). NOT identity safety: overlapping windows are not distinguished. Unit-tested only (tests/test_scope_guard.py).
Live --serve runs on the owned controls page (tests/run_serve_atspi.sh; real Chrome + real Gemini; X11 virtual; gesture simulated):
 - Run 3:35: AT-SPI "1 match" with label "Owned Controls Test" (window title) -> refused by the scope guard (outside region). Real live guard firing, on an AT-SPI source.
 - Run 3:36: AT-SPI element line ("entry Email address") reached the Gemini prompt; Gemini named the email field. Utterance: model returned the PIXEL rect as box_2d (looked normalized) -> mapped wrong -> scope guard refused (no cursor).
 - Fix: prompt now also gives the region as normalized 0-1000 box_2d, explicitly labelled.
 - Run 3:39: with that line, Gemini returned the region box; the vague-label resolver mapped it to the single control in the region (CDP) and the cursor landed inside the email field (293,403 in [159,381,269,36]). BUT the AT-SPI probe returned nothing in that run (no element line; Gemini described the region as page title text). AT-SPI/Chrome availability is FLAKY: the tree was empty on several first queries in the app (a warm-up thread was added; it still returned nothing in the 3:39 run). Cause not isolated.

## Ordering evidence and AT-SPI first-query latency (3:45 IST)
- Commit-time log line: "commit: context built in Ns; element=.. selection=..". Cold AT-SPI probes on Chrome in the app: 12.5s (element NOT found), later run 4.3s (element found). The probe runs on the monitor thread BEFORE the highlight is queued, so a slow probe delays the @highlight turn; a user utterance arriving first is then processed WITHOUT the highlight context (observed at 03:27: point rendered before the highlight was handled; the stale PNG then showed a trail and no cursor). Open: bound the probe (timeout) and/or serialize utterance behind pending commit.
- Fresh external frames (scrot, not the app's own capture) in a 03:44 --serve run: trail gone before point; cursor rendered at the email field at the logged time (frames at 03:44:37.5 before render, 03:44:45.1 and 03:44:50.2 after). Source was atspi(1 match) there.

## Commit ordering/serialization, bounded probe, privacy gating (3:53 IST)
- The @highlight turn is queued BEFORE the context is built; later utterances stay behind it in the FIFO (observed: highlight turn handled before the utterance in 3 consecutive runs).
- Probe is bounded (6s). Expiry sets atspi_status="unavailable: ..." and the prompt tells the model not to infer element/selection from absence. Window is captured at commit before the probe. Unit-tested (no AT-SPI) only.
- AT-SPI init once at import; probes/all_targets serialized by a lock; our own process is skipped; a readiness warm-up polls for a populated "document web" node.
- STILL FAILING live: in-app Chrome probe exceeds 6s in every run since the warm-up was added (selection turn on the owned heading therefore NOT achieved; model got "unavailable"). Hypothesis (unproven): the warm-up readiness search holds the shared lock while Chrome answers slowly, blocking the gesture probe; Chrome tree had only ~247 nodes (browser UI, page document not populated) in those runs.
- Privacy: the 'atspi probe' stderr print (labels/selected text) and 'atspi desktop/walked' lines are now gated behind TIPTOUR_DEBUG_ATSPI. Remaining test-only aids to strip before release: TIPTOUR_TEST_HOOK_CMD + tip.json write; log lines print window titles and tool labels (trace.log) — decide log policy.

## AT-SPI worker redesign (4:06 IST) - STILL NOT RELIABLE IN-APP
- One dedicated AT-SPI worker thread (bounded: 1 pending request, newer supersedes older, expired requests are dropped unstarted; in-flight GDBus calls are NOT cancellable). Walk wall budget, hint-PID-first, own process skipped. Commit context is built on a separate consumer thread (60Hz sampler no longer blocked); the @highlight turn is queued first. Resolver paths (all_targets/resolve) use the same worker with a bounded wait.
- Local harness (GTK window + Chrome, no Gemini; /tmp harness, not in bundle): after a warm-up the probe found "Email address" in 2.4s then 0.02s, resolve 0.03-1.6s, ready at 17s.
- In the real app (same machine, --serve, real Gemini session): first full probe took 9.5s (no warm full probe) / 19s (with warm full probe), _all_targets 7s. The gesture probe exceeded the 6s bound in 4 consecutive runs, so selection/element context was reported "unavailable" and NO positive selection turn was achieved. Cause of the in-app slowdown (vs harness) not isolated: candidates are Chrome busy with the app's 1fps captures/overlay hide-show, and GDBus contention. No claim of a reliable AT-SPI context on Chrome.

## Worker priority + local findings (4:12 IST)
- Warm-up probes are LOW priority: they never supersede a pending real request (they yield) and run in 3s slices. tests/test_atspi_worker.py (local, no Chrome/model) verifies: rapid gestures (superseded older, newest runs, no cross-results), deadline expiry drops a request unstarted, low-priority yields. NOT tested: that the 60Hz sampler keeps running while GDBus is blocked (design only: commit consumer thread).
- Local GTK+Chrome harness (tests/harness_probe_gtk_chrome.*, no model): the FIRST AT-SPI query on Chrome stays slow (>8s, up to ~30s for readiness), regardless of GTK_A11Y=none or the 1fps hide/grab/show load; once Chrome's tree is populated probes are fast (0.02s) or budget-limited (~3.5s). Under the 1fps hide/show load a later probe timed out once (8s) while without the load it did not (one run each: indicative only).
- Honest limit: within roughly the first 15-30s after Chrome starts (or after it first sees an AT-SPI client), the app reports "unavailable". The in-app A/B (warm-up off, streaming off) was NOT run with a model per instruction.

## Correction + latest in-app state (4:21 IST)
- CORRECTION: serve5 harness runs between 3:48 and 4:13 labelled "+35/+40s" actually fired the gesture ~6s after launch (my sed on the sleep did not apply). Their "unavailable" results are NOT evidence about a warm in-app state.
- tests/browser_env.sh now exports ACCESSIBILITY_ENABLED=1 itself (Chrome environ read back from /proc: ACCESSIBILITY_ENABLED=1) and the AT-SPI bus launcher is started before Chrome.
- highlight.py: missing "import sys" turned the debug print into a NameError that was reported as "probe error"; fixed.
- Probe now prunes sized containers that miss the highlight and reports a truncated empty walk as UNAVAILABLE (not "none").
- Runs with the gesture at ~70s after launch: (a) probe 5.6s, atspi=ok but element/selection none (walk was truncated by the budget, status then wrongly "ok"; fixed afterwards), (b) after pruning: still "unavailable: exceeded 6s". No positive in-app selection turn. Variance is high; no claim of reliability.

## Process-isolated AT-SPI (opt-in) and staleness correctness (4:30 IST)
- New: probe_isolated()/targets_isolated(): run libatspi in a fresh subprocess (killable on timeout, a real cancel). Opt-in via TIPTOUR_ATSPI_ISOLATED=1. NOT the default: in my local Chrome test (tests/harness_isolated_probe.sh, no model) the isolated probe returned element=None in 0.04s repeatedly for ~35s after launch, while the in-process worker found the element after its warm-up. Cause not isolated (lazy Chrome children visible to a long-lived client only?). Auditor reported the opposite for a late-aged Chrome; unreconciled.
- Correctness: a hint window PID absent from the AT-SPI registry, an empty hint-app tree, or a browser hint app with no populated "document web" node now raises UNAVAILABLE instead of returning none.
- Unit tests only for the worker queue and scope guard. Warm-up thread is back on by default (TIPTOUR_NO_WARM=1 disables).

## Local in-app 2x2 A/B, NO model (TIPTOUR_LOCAL_NO_MODEL=1 fake client; 4:34-4:40 IST) - tests/ab_local_inapp.sh
Real app modules (GTK overlay, commit worker, AT-SPI worker) + real Chrome on the owned page (heading selected via CDP, simulated Ctrl+Shift gesture 30s after launch). Single run each.
- A default (warm-up on, stream on): atspi=ok, selection=True ("Account preferences (test page)", role=heading) in the prompt; probe 3.2s.
- B warm-up off: unavailable (probe >6s, worker call 8s TimeoutError).
- C stream off, warm on: atspi=ok, selection=True; probe 2.4s.
- D: see summary file.
Conclusion: warm-up is the variable that matters; 1fps stream capture is not. Retraction: the 04:27-04:30 "isolated probe returns none" runs were invalid - the local http.server for the owned page had died with a sandbox restart, so Chrome showed an error page.

## Bundle20 notes (honest status)
- Real Gemini serve turn 04:44 (warm condition: gesture ~70s after launch, warm-up on, selection made via CDP, chord via xdotool): the selected heading text reached the prompt through AT-SPI and the first reply was correct. The follow-up "what text is selected... quote it, do not point" FAILED as a quote: the model attempted submit_workflow_plan instead of answering in words (point-only default; --act off, so nothing could execute).
- Added a USER-intent gate (highlight.no_action_requested): answer-only requests (explicit "do not point/click", or text/quote/describe questions with no action verb) get NO cursor and NO action whatever tool the model calls. Verified live at 04:51 (model attempted a click; suppressed, no cursor). The model still gave no spoken/text quote after the suppressed call (reply empty, audio 0). Quote-answer behaviour remains NOT working. Bounded regex guard, not semantic understanding.
- With --act, execution now also needs matching intent in the user's words (rightClick only for explicit right-click/context menu, etc.). Unit-tested only (tests/test_no_action_gate.py); --act remains untested live and off by default.
- Unknown or 0 window pid now yields atspi_status "unavailable" (no unscoped probe).
- Bounded shutdown: a 3s daemon watchdog calls os._exit after Gtk.main returns. Not reproduced against the auditor's exit-124 hang; in my run results.json was written at quit.
- Removed TIPTOUR_TEST_HOOK_CMD and the tip.json write. TIPTOUR_LOCAL_NO_MODEL (fake client) is still in app.py, env-gated, local test only. TIPTOUR_DEBUG_ATSPI* prints remain env-gated.
- Sampler: 60Hz monitor not blocked by a stuck probe (tests/test_sampler_blocked_probe.py, fake sleep probe, not a real GDBus stall). The single FIFO commit worker can still delay later commits.

## Bundle21 notes (honest status)
- Browser DOM selection fallback (cdp_resolver.selection, used when AT-SPI gives no selection): requires hint pid > 0 == foreground X11 pid == CDP browser process; exactly one visible, document-focused page target whose title prefixes the focused window's title; dpr 1; only text whose range rects intersect the highlight is returned; provenance "cdp_dom" is shown in the prompt as a browser page selection, not as accessibility. Never overrides an AT-SPI selection. Not read: text inside input/textarea (getSelection does not cover it), cross-origin iframes (not validated).
- LIVE local test (real Chrome, no model): tests/test_cdp_selection_live.py 6/6 PASS (positive; region elsewhere; wrong pid; pid 0; pid None; other tab in front => nothing read). Single run.
- In-app local runs with the FAKE client (tests/fake_client.py, canned, not a model), gesture 70s after launch, one run each, unique dirs under /tmp/runs: in-process AT-SPI probe: atspi=ok selection=True but 5.64s (close to the 6s budget); isolated (TIPTOUR_ATSPI_ISOLATED=1): 0.07s, selection=True. n=1 each. Not proof of immunity to registry decay. Default is still in-process.
- DOM fallback in-app (TIPTOUR_USE_ATSPI=0, fake client, 15s): selection=True src=cdp_dom 0.05s.
- Tool-response wire: the suppressed answer-only toolCall now gets ok:true status suppressed_no_action with the user question, an answer-in-words instruction, and selected text only when present. Verified with the fake client only; real Gemini behavior after this response is NOT yet observed.
- Fake client moved to tests/fake_client.py via TIPTOUR_CLIENT_FACTORY (test seam in app.py). The 3s os._exit watchdog is a fallback, not proper cleanup.

## Bundle22 notes
- Inside-overlap point (behind the no-action gate): only when the request is point-authorized (point/show/where/find/locate/which, and NOT answer-only), exactly ONE uniquely bound cdp_dom element resolved, and the element overlaps the highlight by >=4px each way: the cursor goes to the centre of the overlap instead of an outside centre (label gets +inside_highlight_overlap). Otherwise the scope guard still refuses. AT-SPI-bound elements are not covered yet.
- Verified locally with the fake client (canned toolCall, real Chrome, 15s gesture, AT-SPI off): "Point to the highlighted heading" => cursor at (218,201) inside the highlight region (26,169,366,64), heading rect 44,187,1512x28; fresh pixels in the evidence crop. Single run. Real Gemini not run.

## Bundle23 notes
- suppressed_no_action payload now branches on the real source (selected_text + truthful selected_text_source, or a note with the atspi/dom statuses; unit-tested). CDP selection docstring corrected: the whole selection (<=600 chars) is returned when at least one range rect intersects the highlight.
- Serve-loop bug found and fixed: the model's turnComplete can arrive BEFORE its spoken answer to a suppressed tool call; the loop used to stop there and lose the answer. Now, only for answer-only turns, an early turnComplete is ignored for up to 12s while waiting for the answer (no answer in 12s => stop and log). Locally verified with tests/fake_client.py TIPTOUR_FAKE_EARLY_TC=1.
- REAL Gemini quote turn (run 1026-051157-REAL-quote2-waitfix-d70, default config, gesture ~70s after launch, selection set via CDP, chord via xdotool, owned page): AT-SPI unavailable (4.84s, again at the 70s point), DOM fallback provided the selection (src=cdp_dom); prompt labelled it a browser page text selection; the model's first ack was correct; the answer-only quote question got a suppressed rightClick attempt (no cursor, no action) and then a spoken answer quoting "Account preferences (test page)" (266882 audio bytes + transcript). Single run. The model still tries a tool call first on that question. AT-SPI selection at 70s idle remains unreliable (3 of the last 4 real runs unavailable); the DOM fallback is what made this pass.

## Bundle24: tainted-session handling + release inventory
- Events carry a session generation. If a turn does not reach a definitive completion (no answer within TIPTOUR_ANSWER_WAIT_S, default 20s, after a suppressed answer-only tool call; 60s ceiling; socket closed), the session is marked tainted and REPLACED with a fresh one before the next request; events from the replaced session are dropped. Local regression (fake client, answer scheduled after the wait window, cross-turn): second turn got no stale reply and the log shows the session replacement. Fake only; the real service was not made to time out.
- Real-run timing: the real answer arrived ~11s after the suppressed call in the one real success (n=1); default wait raised from 12s to 20s for margin. This does not itself prevent misattribution; the session replacement does.

### Release inventory (NOT a full-port claim)
REAL-tested on Linux X11 (virtual Xvfb + xfwm4, real Chrome, owned/public pages, real Gemini free-tier vault key): point-only pointing with AT-SPI/CDP/YOLO+OCR/raw-box grounding order and "?"-unconfirmed raw guesses; refusals (ambiguous, off-screen, wrong foreground, changed window, outside highlight); Ctrl+Shift highlight with fresh screenshot + context prompt; browser DOM selection fallback (n=1 real quote answer, selection set via CDP, chord via xdotool); answer-only intent gate.
LOCAL/FAKE only: inside-overlap point, tainted-session handling, early-turnComplete wait, A/B probe timing, isolated AT-SPI probe, sampler, fake client wire tests.
UNIT only: action intent for --act, pid gate, regex gates.
NOT done or not verified: --act execution (actions.py unrun), physical Linux machine, Wayland, Windows, multi-monitor/HiDPI (dpr!=1 fails closed), z-order/occlusion beyond foreground checks, AT-SPI selection reliability at idle (flaky), input/textarea selections, iframes, real microphone/PTT audio path, original-look parity items not rechecked this round, log privacy policy for trace.log (window titles/labels), release packaging, no push.
