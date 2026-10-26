# Linux port: current status (bundle25). Experimental, X11 only, NOT a full port, NOT pushed.
Base: upstream 6e97782. Python/GTK3. Evidence classes: LIVE = real Gemini + real Chrome on a virtual X11 display (Xvfb + xfwm4), xdotool-simulated input, owned or public pages; LOCAL = real app/Chrome with a canned fake client (tests/fake_client.py, not a model); UNIT = tests with fakes; OPEN = not done. Everything LIVE is a small number of runs on one machine. Historical checkpoints: tests/EVIDENCE_LOG.md (contains superseded statements).

## What works (with evidence class)
| Capability | Status |
|---|---|
| Gemini Live wire, serve mode (one session, context resend per utterance, commit-before-utterance FIFO) | LIVE |
| Screen capture, overlay cursor (click-through), "?"-marked unconfirmed raw-model points, refusals with no cursor (ambiguous, off-screen, wrong foreground, changed window, outside highlight/window) | LIVE |
| Grounding order AT-SPI, CDP DOM, YOLO+OCR refine, raw box | LIVE (AT-SPI flaky, see gaps). YOLO11m weights converted from the repo's CoreML package; numerical identity vs CoreML unverified (no Mac run). OCR is tesseract, weaker than Apple Vision |
| Ctrl+Shift highlight: trail, commit, fresh screenshot + context prompt (region as normalized box_2d, window title/pid) | LIVE with xdotool-simulated chord only |
| Browser DOM selection fallback (bound to foreground pid, single focused tab, title prefix, dpr 1, at least one range rect intersecting the highlight) | LIVE n=1 quote turn (selection set via CDP, not by a user) + 6/6 local binding tests + auditor negatives; input/textarea and iframes not covered |
| AT-SPI text selection / element context | LIVE when the probe works; unreliable at ~70s idle (see gaps) |
| Answer-only intent gate: "do not point / quote / what text" never gets a cursor, click or workflow, whatever the model calls; response is ok:true suppressed_no_action with the user question and the selected text only when actually read (source labelled) | LIVE (2 real catches); regex guard, not semantic |
| Early turnComplete tolerance for answer-only turns (wait up to 20s, TIPTOUR_ANSWER_WAIT_S) and tainted-session replacement (fresh session, stale events dropped) | LIVE n=1 (answer ~11s after the call); taint replacement LOCAL only |
| Inside-overlap point: unique cdp_dom element overlapping the highlight by >=4px, point-authorized request => point inside the overlap | LOCAL + UNIT |
| 60Hz sampler not blocked by a stuck probe | LOCAL (fake slow probe) |
| Voice-first loop (`--voice`): Ctrl+Alt toggle, mic streaming, input transcript feeds the gates, spoken replies played, interruption flush, mic stop on toggle/quit | LIVE with VIRTUAL audio devices + synthetic (Gemini TTS) speech, n=2 runs (second quiet-log). NEVER a physical mic, speakers or real keyboard. Follow-up turns without a second press work (mic stays open) |
| Key pool failover | UNIT; a real 429 failover was never observed |
| --act (click/type) with per-step intent gate | UNIT only. OFF by default, NEVER run live. actions.py unrun |

## Deliberate divergences from Mac
AT-SPI instead of macOS AX; CDP with own scoring instead of the cua library; tesseract instead of Vision; X11 only (no Wayland), single display, dpr 1 only (fails closed); 1fps stream paused while the cursor is visible; point-only by default; 6s AT-SPI probe budget with UNAVAILABLE instead of guessing; mic capture and playback via parec/paplay (virtual-audio tested only), no menu-bar UI; tool schema reduced (no create_note).

## Known reliability gaps
1. AT-SPI in-process probe at ~70s idle was UNAVAILABLE in 3 of the last 4 real runs (4.8 to 6.0s vs the 6s budget). The warm-up only fixes startup. One isolated-subprocess local run was 0.07s (n=1; default NOT changed).
2. First 15-30s after Chrome starts can report UNAVAILABLE.
3. One real quote answer, selection carried by the DOM fallback; model still attempts a tool call first on that question (gate absorbs it).
4. Single FIFO commit worker can delay later commits behind a stuck in-flight D-Bus call.
5. Real runs: owned page, one machine, virtual X11, simulated input. No physical Linux, no real keyboard/mouse, no Electron/Qt/GTK-native apps, no HiDPI/multi-monitor, no occlusion/z-order beyond foreground checks.
6. Voice: transcripts can lag a toolCall (waits <=3.7s, then refuses to act); stale per-turn frames for follow-up voice turns (the 1fps stream and the identity guard are the mitigations); the first real run showed spurious model turns when a context text was resent per voice turn (fixed, not re-observed since).
7. Out of contract: unexpected audio/transcript arriving after a DEFINITIVE turnComplete (not a timeout) is not handled and could be attributed to the next turn; only timed-out/closed turns taint and replace the session. The 20s TIPTOUR_ANSWER_WAIT_S knob is an env tunable (default 20, not a user setting).
8. The 3s os._exit watchdog after Gtk.main is only a fallback; the auditor's exit-124 was the harness (ffmpeg surviving), not an app hang; the app exits cleanly and writes results.

## Not ported
Local target cache + continuity; ask harness, clipboard handoff, scribble; JEV/TypeSafe (+OpenRouter); tutorials/Elorian; radial input, text-command chords, menu-bar UI, settings, onboarding; local harness server 127.0.0.1:19474; Wayland; Windows (not started).

## Release hygiene
- Keys: files only via TIPTOUR_KEYS_GLOB; final key-prefix scan clean (see bundle report). 
- Logs: default trace/stdout carry no titles/labels/utterances; TIPTOUR_DEBUG_LOG=1 and TIPTOUR_DEBUG_ATSPI* are explicit debug opt-ins. --out artifacts are test outputs and sensitive.
- Test seams: TIPTOUR_CLIENT_FACTORY needs TIPTOUR_TEST_MODE=1; fakes live in tests/.
- Setup/Chrome accessibility and licenses: README.md (detector weights AGPL-3.0 per the model metadata inside MIT repo: owner decision needed).
- Tests: tests/ (unit: test_no_action_gate.py, test_atspi_worker.py, test_scope_guard.py, test_keypool.py; live local: test_cdp_selection_live.py via run_cdp_selection_live.sh, run_inapp_*_fake.sh, run_inapp_selection_real.sh needs keys).

## Claimable slice today
On X11 + Chrome with CDP: Ctrl+Shift highlight to selection-aware quote (text + voice) and the guarded pointing loop work with real Gemini, with refusals and no-action behavior verified on a small number of runs. Everything else is UNIT/LOCAL/OPEN. Full port: not ready.

## Update: Ask harness (LOCAL-REAL, virtual audio)
Ask chord + capture + offline Vosk transcript + GTK preview + Copy text/image + focus-checked draft insert: ran in Xvfb with xfwm4, virtual mic, synthetic speech, owned GTK entry (run 1026-0537-ask-virtual-2). Not ported: scribble, settings, tray, target-app chooser, AX focused-element check (X active window id instead), clipboard changeCount (hash read-back instead). Launcher/.desktop exist, untested on a real desktop. Vosk transcription differs from the Mac SFSpeech.

## Update 5:45: clipboard policy, stale frame, echo, interruption
- Ask clipboard: snapshot all previous targets before first stage; restore only if clipboard still exactly ours; multi-format previous clipboards restore ONE format (image/png > text > other) and report "partial"; empty previous clipboard cannot be cleared on X11 (reported); changes by others before or during paste are refused/left untouched with a clean message (REAL xclip/xdotool/GTK entry, run 1026-0544-ask-insert-neg-4, 9 cases). Not tested: GTK button path for the refusal message (source only), Wayland.
- Voice stale frame: after the transcript, a fresh capture is compared with the frame pinned at turn start (>3% of pixels changed => refuse, TIPTOUR_STALE_FRAME_MAX). Window identity alone did not catch same-page content change. Synthetic-image unit test only for the refusal; the real voice run showed 0.0% on an unchanged page (pointing still worked). Caret-size change counted as unchanged.
- Echo: voice start logs a warning if the source is the sink's monitor; speaker-to-mic ACOUSTIC echo is NOT checked or cancelled. Supported setups: headphones, or module-echo-cancel with TIPTOUR_MIC_SOURCE/TIPTOUR_AUDIO_SINK set. The virtual tests use a monitor on a separate sink (tt_in for mic, tt_out for reply) so no loop exists.
- Interruption: Player.flush on a virtual sink dropped queued audio (6s queued, 0.8s audible; run 1026-0541-interrupt-stale-1). The model-side interrupted event path stays unexercised live.
- results.json audio_bytes is now per turn (audio_bytes_cumulative kept).
- Spoken ack: the Mac asks for a spoken acknowledgement only for the highlight prompt (shouldAskForAcknowledgement); no post-pointing ack was added.

## Update 5:50 (supersedes the 5:45 clipboard and stale-frame lines)
- Clipboard is now NO-LOSS or refuse: if the previous clipboard holds more than one distinct format (text aliases count once, e.g. html+text) or cannot be read, Copy/Insert refuse BEFORE overwriting (REAL test with a python-xlib owner of text/html + UTF8_STRING, run 1026-0549-ask-insert-neg-6, 10/10). Single-format previous text or image is restored exactly (hash read-back not re-verified after restore). Empty previous clipboard: staged data stays (X11 cannot clear), reported. Consequence: copying from rich sources (browsers) blocks the Ask copy/insert until the clipboard is single-format; this is a usability cost, not a fix.
- Stale check now also compares a 180x180 crop around the pointed target (>6% refuses) besides the whole frame (>3%). Both are HEURISTICS on pixels, not proof the target element is the same: a recolored or same-size swapped control can pass. Synthetic tests only for refusal (moved 80x30 button: frame 0.3%, target 7.7%); real run 1026-0550 checks no false positive on an unchanged page.

## Update 5:55: evidence hygiene and GTK-path negatives
- Runs from 0552 on write TREE_MANIFEST.txt (sorted sha256 of every linux/ file excl. __pycache__), tested-tree.tgz (exact bytes at run start) and ENV_TIPTOUR.txt; tests/clean_env.sh strips tuning/test envs first. Earlier runs keep their old git-diff CODE_VERSION or none: historical, not retro-pinned. MANIFEST.txt's code_version line is NOT the tested tree.
- REAL GTK button path (run 1026-0552-ask-virtual-4, and via the launcher wrapper 1026-0553-ask-virtual-5-launcher): multi-format clipboard -> Copy text refuses before overwriting (html intact); clipboard changed between Copy and Insert -> Insert refuses cleanly, entry stays empty; retry works. Status label now wraps. Superseded note added to 1026-0536-ask-virtual-1.
- Settings file (3 live keys + 1 stored-unused) added; autopilot not exposed. Real voice run 1026-0550 (pre-settings code): target-level stale check 0.0%/0.0%, pointing intact.

## Update 5:58: target chooser, settings window, tray
- Target chooser functional (REAL Xvfb+xfwm4, owned GTK entries A and B, run 1026-0556-ask-target-1): focus B at press, settings preset to A's WM_CLASS, Insert -> text lands in A, B stays empty; a second window of A's class -> refused as ambiguous. The combo-box click itself was not driven (preset via settings file). Window titles are read locally for the chooser only; the chooser lists class names, not titles.
- Settings window: REAL screenshot + toggle persisted (run 1026-0558-settings-gui-2; 0557 crashed, superseded). Settings apply on the next launch only.
- Tray: code exists, not verified (no tray host). .desktop file untested on a real desktop. Mac menu-bar panel, onboarding and permission UI are not ported.

## Update 6:05: combo fix, current-tree regression, inventory
- Ask chooser: the saved target is no longer rewritten when Ask opens (handler connected after construction); a saved app that is not open is shown as "NOT OPEN" and Insert fails closed (REAL run 1026-0604-ask-target-closed-1: settings unchanged, entry empty, "has 0 matching windows"). The combo was driven by click+keys in 1026-0601-ask-target-3 and in the regression.
- Consolidated regression on one tree: /tmp/runs/1026-0605-ALL-regression-2 (units, stale/interrupt, insert negatives 10/10, Ask GTK flow, target A/B, closed target, real voice). Every stage is a separate process/X server; Ask and voice were not run together in one session. Docs (this file, README, MAC_FEATURE_INVENTORY.md) were edited after the snapshot; code was not.
- In that regression's voice run the model spoke an unprompted description ("voice turn, no transcript", 369122 bytes, no tool call) right after the toggle, before any synthetic question. Refusal/no-action held; it is a behavior to understand, not a pass. Quote turn was spoken (153630 bytes); pointing turn found the checkbox via AT-SPI (AT-SPI worked this time, unlike earlier idle runs).
- MAC_FEATURE_INVENTORY.md lists remaining Mac areas with user impact.

## Update 6:20: voice context, quit, chooser filter
- Cause of the unprompted spoken description at toggle: the app itself re-sent the highlight context as a realtimeInput text turn at voice start (the Mac does not; it re-sends on the first input transcript of an utterance). Removed. A variant that re-sent on first transcript (Mac-faithful) was run once: toggle quiet, but the mid-utterance text split the quote answer across two turns (1026-0611-REAL-voice-ctxfix-1, valid, superseded). Current behavior (deviation from the Mac, deliberate): the context is seeded at voice start with clientContent turnComplete=false so no model turn is triggered. REAL n=1 (1026-0615-REAL-voice-seed-1, virtual audio, synthetic speech): quiet toggle (first result is the question turn), quote answered in one turn with audio (196802 bytes), point turn stale 0.0%/0.0% and cursor via atspi. n=1 only; not a proof the seed is used by the model.
- @quit during a live voice turn used to hang (fake-client test 1026-0618-clean-exit-2 timed out, marked); fixed (reader injects voice_stop, mic/player closed on shutdown). App clean exit test 1026-0620-clean-exit-3 (fake client, mic live via the real chord): exit 0, watchdog not fired, no leftover parec/paplay. Fake client, not a model session.
- Harness teardown (ffmpeg/Xvfb/chrome surviving) now cleaned by the voice script itself; that is harness hygiene, separate from the app's own exit above.
- Chooser lists only _NET_WM_WINDOW_TYPE_NORMAL windows.
- Text command (Control+K): the Mac sends it to JEV (TypeSafe direct or OpenRouter, needs a JEV key; OpenRouter input tokens are billed), NOT to Gemini Live. A faithful port needs that provider and is outside the free-tier-only constraint; a Gemini-based typed popup would be a different product behavior. Radial input (Ctrl+Opt+Cmd wheel: speak/type/highlight) only dispatches to those modes; "type" depends on the same JEV path.

## Update 06:45 - Teaching-mode click detector (Mac ClickDetector.swift analogue), point-only
- clickdetect.py: listen-only. XInput2 RawButtonPress hook (X11 only; Wayland unsupported) with a ~100 Hz XQueryPointer polling fallback. Rect (+6px inflate) or 40px point tolerance, 0.18s post-hit grace, one-shot, re-armed per tool call, disarmed on refusal. Position is read right after the event (small race if the pointer moves). Only button 1 fires; XI2 raw events do not say which window got the click.
- Measured here (Xvfb, xdotool = synthetic input, NOT physical): polling backend caught 0/20 back-to-back press+release clicks; XI2 backend 20/20. Button 3 held then button 1 fires; button already held at arm time does not fire.
- app.py: after pointing arms the detector; a click on the target dismisses the pointer (Mac: one-step plan completes -> stop()). Mac post-click AX-fingerprint validator, retry/skip UI, multi-step plans and autopilot are NOT ported (the Linux prompt, like the Mac one, submits exactly one step per turn).
- Real run 1026-0643-click-detect-5 (real Chrome, owned page, fake model = canned toolcalls, xdotool clicks): far click miss, target click hit, wrong-button click miss, correct click hit, re-armed target ignores click on the old target. App-level token-mismatch callback path is only exercised by that re-arm case, not by a true race.
- Harness root cause found: 8 run scripts used `wait %1`, which in browser_env.sh waits on the chrome job, not the test subshell. Replaced with `wait $SUB`. Verified on run_click_detect.sh only (clean exit); the other 7 scripts are patched but not re-run.

## Correction 06:50 - click detector measurements and lifecycle
- The earlier "polling 0/20" figure came from an ad-hoc inline test with no shipped script. The shipped measurement (tests/measure_click_backends.sh, run 1026-0650-click-backend-measure-1, Xvfb, synthetic xdotool, 20 back-to-back clicks, re-armed each time): poll backend 1/20, XI2 backend 20/20, errors [], thread_starts 1. Use these numbers only.
- The "poll" label on turn 1 of run 0643 was a bug of mine, not a restart: backend was pre-set to "poll" before XI2 selection finished, so the first report read it early. Fixed (assigned after the decision; start() waits for it). Run 1026-0647-click-detect-6-winid: all four turns xi2-raw. click_events.json now records errors, thread_starts, backend. The thread body is wrapped: a death is recorded, not silent.
- Window identity at press (topmost top-level under pointer == the one pinned at arm; focus may stay or move TO the pinned window, never to a third) is ADDITIVE vs the Mac tap, which checks coordinates only. Tested with plain Xlib windows (overlap, focus move, click-to-focus, control) in tests/test_clickdetect_windows.py (no WM: real WM focus/stacking behaviour is only covered by the Chrome+xfwm4 run where the target hit).
- Stale token: tests/test_click_stale_token.py is a UNIT simulation of the race window (plan replaced, old arm not yet disarmed, press arrives -> ignored). Not a timing race on live threads.
- clean_env.sh strips TIPTOUR_CLICK_DETECT/BACKEND and TIPTOUR_FAKE_* now.

## Update 07:12 - post-click validator, live stale refusal, real-WM overlap negative (point-only, --act OFF)
- workflow.py: AT-SPI fingerprint (visible clickable controls, all apps, role+name+rounded rect, cap 400) before arming; after a hit, poll 6 x 250ms for a different hash. Unchanged -> pointer kept, event "unchanged_paused" (no retry/skip UI). Mac: focused-window AX nodes (<=120, 0.15s) and 5 x 80ms. A harmless no-op click reads as "unchanged" on both. Skipped for rightClick and when no fingerprint is available (event says "unavailable").
- Real runs (real Chrome + AT-SPI + xdotool on an owned page, fake model = canned toolcalls):
  - 1026-0706-click-validate-2: T1 "Open settings" click -> validator changed -> dismissed. T2 "No-op action" click -> unchanged_paused, pointer kept. T3a target moved during an 8s model delay: label resolves live, pointer follows to the new location (this is NOT a refusal; stale guard read 0.5%). T3b target removed + region repainted, model point on the old target: REFUSED (frame 5%, around target 12%), no cursor, no arm. (Run 0703-click-validate-1 earlier iteration, superseded.)
  - 1026-0712-click-overlap-wm-2 (xfwm4): an owned top-level window covering the armed target; click at the target point -> miss-window-changed; same click after it closed -> hit. Screenshot shows the overlap. Run 0709-...-1 is INVALID (WM ignored the window position, no overlap), kept with NOTE_SUPERSEDED.txt. Limitation seen: the pointer overlay stays drawn on top of the covering window.
  - Real-WM focus-to-a-third-window negative is NOT covered (a click on the target cannot move focus to a third window under click-to-focus); only plain-Xlib no-WM unit coverage exists.
- Bookkeeping: the idle open voice listener closed by toggle-off is no longer recorded as an empty "(voice turn, no transcript)" result (run 1026-0701-REAL-voice-bookkeeping-1: 3 results, log line "idle voice listening ended by toggle-off"). That run's tree predates the validator edit.
- Still open: multi-step plan advancement (Mac prompt is single-step; steps array unused), retry/skip UI, run_all.sh does not yet include the validate/overlap runs.

## Update 07:35 - validator scoping, arm-before-pointer, honest unavailable (point-only, --act OFF)
- Arming now happens BEFORE the pointer is drawn (Mac: arm first, then fly). Earlier builds armed after drawing: a fast click could be missed. Cost: the pointer appears after the pre-snapshots (~1-3s later).
- Validator is scoped to the APP owning the armed target (AT-SPI app name of the smallest control containing the point), not the focused window. Two pre-snapshots 0.4s apart; items in only one are noise (Chrome idle tree measured 18 vs 19 targets). Status values: changed (effect confirmed), unchanged_paused (pointer kept, no retry/skip UI), unavailable (effect UNVERIFIED, never reported as confirmed). Reads are guarded; failures are recorded.
- Real-run results on the unrelated-app test (a second GTK app mutates its controls at click time; page button is a no-op): run 4 unchanged_paused (correct), run 5 changed (WRONG: Chrome tree noise, before the noise filter), run 6/7 unchanged_paused, run 3 and 11 unavailable (pre snapshot TimeoutError even at 5s, AT-SPI walk of all apps too slow under load), run 8/9/10 invalid or died (pre too slow / armed late / validator thread died on a 1.5s timeout, fixed). NO run yet shows the final stable/noise+armed-first build passing end to end. The validator is therefore NOT proven reliable here; "unavailable" occurs in about 2 of 8 runs.
- Not built: pause on app switch while armed/paused, hiding the pointer when a window covers the target, retry/skip pause UI.

## Post-click validator (Linux analogue of the Mac WorkflowRunner fingerprint) - limits, not a pass
- Scope: the APP owning the armed target (Mac: focused window, <=120 nodes; Linux: app, cap 400). Needs an AT-SPI control at the target point, else verdict "unavailable".
- Baseline: two app-scoped snapshots 0.4s apart, started in a background thread at arm time (arming/drawing never wait). Items in only one snapshot are NOISE. Click before baseline ready -> "unavailable:click_before_baseline_ready" (post state is never the baseline). "Ready" means two snapshots agreed, not that the app had settled.
- Post: 6 reads x 250ms. "changed" needs the SAME difference on 2 successive reads (a single partial/wobbling Chrome tree read is not enough); diff logged from the confirming read. "unchanged_paused" needs >=1 successful read; all reads failed -> "unavailable". Unavailable/unchanged are never reported as verified success.
- Bias: noise filtering and duplicate items bias toward "unchanged"; a harmless no-op reads "unchanged" on both platforms. Shutdown does a bounded join and records "pending_at_shutdown".
- Not built: pause on unrelated app switch while armed/paused, hiding the pointer when a window covers the target, retry/skip UI for "unchanged".

## Pointer guard and pause controls (Linux additions; the Mac has no equivalent window-identity guard)
- Display isolation: tests/browser_env.sh holds a non-blocking flock; a second run refuses (exit 3) instead of killing the first run's X server.
- Guard (0.4s poll against the identity pinned at arm time): another window topmost at the target -> pointer hidden (reversible); it is shown again only if the SAME control (label + rect within 8px) still exists in the same app. Unverifiable sources (CDP / model box / no app) never resume.
- Focus moved to a third window -> explicit pause: pointer hidden, detector disarmed, NO auto-resume (like the Mac). Resume requires the @retry control with the target window in front, or asking again.
- Terminal states (hit, refusal, skip, pause, target changed) set hidden and clear covered; a queued show callback re-checks token + terminal state under a lock at execution.
- @retry (only after unchanged_paused or an app-switch pause; fails closed if the target can't be re-verified) and @skip are FIFO control commands, not model turns. There is NO on-screen retry/skip button UI yet.
- Unproven: end-to-end retry after a real paused verdict on the final tree (run 4 baseline timed out; run 3 retried before the verdict).

## Current truth (update, harness + isolation) - still "full port not ready", no push
- Native AT-SPI is read ONLY in bounded child subprocesses by default (a native heap-corruption crash, exit 134, was seen in the old in-process worker; the corruptor is not proven). One child at a time, killpg+reap on timeout, count/ms/rc stats only. TIPTOUR_ATSPI_ISOLATED=0 is the old unsafe path. The overlay's own GTK a11y bridge stays in-process.
- Validator is best-effort/unverified, never proof. Measured on the owned page only; "unavailable" is a normal outcome.
- Pause: skip clears the current target; second skip / retry-after-skip are refused; app switch = explicit pause with no auto-resume. Controls are FIFO commands (@retry/@skip). There is NO on-screen pause UI yet.
- Harness: run_all.sh owns /tmp/tt-x99.lock for the whole run; a runner dying leaves orphan stage processes (not yet handled); runs cannot outlive the agent run in this sandbox. STAGES.tsv: RAN/SKIPPED/FAILED. FINISHED never means pass. Exit 0 is not semantic: tests/assert_click_stages.py checks expected labels/verdicts offline on a sealed run (passes on run 14, fails on invalid run 13).
- Not yet: page-content (URL/title/marker) preflight of the loaded Chrome page; resumable immutable-tree runner; voice-real result audit (run 13 voice used a possibly-dead test server and is unaudited).

## On-screen pause panel + page preflight (b46)
- New PausePanel (overlay.py): Retry/Skip buttons shown next to the pointer after `unchanged_paused` and on app-switch pause; hidden on skip/retry/new tool call. Own WM_CLASS (ignored by the click detector). Buttons call the same retry/skip control path as the FIFO @retry/@skip (which remain internal test hooks).
- Tested ONCE, run /tmp/runs/1026-1052-panel-1 (Xvfb + xfwm4 + real Chrome on the owned teach page, fake model, synthetic xdotool clicks on the real button pixels; panel visible in 1_panel_after_noop.png; Retry click re-armed, Skip click dismissed). X11 virtual only; not a physical desktop, not Wayland, not Mac-pixel-compared. Panel look is my own (Mac pause UI not matched).
- Click-stage scripts now check the REAL loaded Chrome page via CDP (URL prefix + title) and abort the stage on mismatch (page_preflight.json). Preflight was exercised only on the valid-page path in this run; the failing path is not exercised.
- tests/assert_click_stages.py now checks ordered events and exact counts; rc=0 on sealed reg14, rc=1 on invalid reg13.
- (b47) Page preflight now also requires: exactly one page tab, tab visible (active), loaded, and the fixture's required control ids present with non-zero boxes. Exercised in /tmp/runs/1026-1059-preflight-cases-2 (real fresh Chrome, owned fixtures, no app/model): positive passes; error page, wrong page, extra/wrong tab, missing control all STOP the stage. This covers only the owned teach/index fixtures, not arbitrary sites.
- (b47) Panel buttons carry a plan token; a click/queued click from an earlier target or pause episode is refused ("stale panel"); the app-switch panel show re-checks the token when it runs. Token refusal is code-reviewed only, not exercised in a run.

## Test-harness commit (pinned/resumable runner) - TARGETED-TESTED ONLY
Separate commit; not part of the product. tests/run_all.sh now copies the tree to RUN/pin/linux and runs every stage from that copy; RESUME=<run dir> skips stages already RAN rc=0, never reruns non-click (possible model) stages without ALLOW_MODEL_RERUN=1, and records a dead runner's stage as ORPHANED (dir kept). A watchdog takes the stage's process group down if the runner is killed hard.
Exercised only with ONLY_STAGES=click_pause (no model calls): fresh pinned run rc=0; resume skipped the done stage; kill -9 of the runner left 0 live stage processes; orphan bookkeeping checked on a synthetic fixture dir. The FULL suite has NOT been run on this runner. An earlier version had bugs (resume rewrote STAGES.tsv; zombie runner looked alive) - fixed, runs marked with NOTE files.
