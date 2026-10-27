# R55 bounded radial Speak dispatch and explicit unsupported options

Opt-in `--radial-input --voice` uses a single radial monitor instead of the separate Ctrl+Alt PTT monitor. It cannot combine with --highlight or --radial-preview. The actual UI says the Ctrl+Alt hotkey is disabled and warns about separate shortcut apps. Speak uses the same owned Gemini voice toggle: both ON and OFF stop pending/approved/running work first. OFF also works while a provider connection is pending because native capture is already active. Type visibly refuses because pinned Mac Type requires JEV; no Gemini substitution. Highlight visibly says unavailable in this configuration because its monitor is disabled; it does not invite an inactive gesture or forge a trail. This is not complete radial input parity.

Pinned Mac Speak captures a hovered app/selection override, stops WorkflowRunner, and toggles voice including pending start. Linux does not implement that selection/context override. Its conservative ON prerequisite is two matching snapshots of an already-focused, mapped, identified hovered client. Topmost own/unknown surfaces and WM frames refuse rather than look through. It never activates another app. These are snapshots of the release point, not a final live-mouse/atomic focus guarantee or persistent voice target binding. No later voice-context or selection binding is claimed.

One daemon target worker owns both snapshots with a 0.4-second deadline. Loop delivery checks the deadline again. A hung native read can still leave the single worker busy, and further ON attempts refuse. Typed ingress, revisioned Confirm/Cancel, Stop and Quit invalidate pending handoffs. Accepted pause controls invalidate after stale-token/redundant refusal rules; stale controls leave newer pending work untouched. Queued GTK status closures check ownership/shutdown before delivery. Existing proposal/revision/Yes gates remain unchanged.

Runtime source f78c796e has actual X radial Type/Highlight refusal without microphone/provider request, Speak ON controlled native Mic/writer and OFF, and ON then OFF during a scripted five-second provider connection with late connection superseded. Both approved-binding ON and active-voice OFF cancel a scripted five-second native binding and leave zero old button effects after six seconds. OFF uses a fresh scripted voice Yes after proposal display; two failed OFF fixture scheduling attempts are retained. Real OS input/GTK effects and controlled PCM pipes do not establish physical microphone, STT or audible playback.

Fresh controlled 180ms second-read cases cover Stop, new request, revisioned Confirm/Cancel and Quit refusing pending ON, while a stale Skip token leaves the pending ON able to start. This is not a measured total 180ms handoff. A positive result held 600ms before loop delivery expires without starting capture. Queued Type/Highlight GTK status held one second then invalidated by Stop/Quit is suppressed. These are explicit test seams, not native hang proofs.

Actual X tests refuse own client, own titlebar outside the client rectangle (coordinate asserted using X translation), missing-PID top client and override-redirect popup; titlebar/popup pixels inspected. Earlier single-window XFWM fixtures lacked a stacking property and safely refused; those failures and a fixture print error remain in evidence. No unsafe fallback to an unordered client list was added.

Fresh 21 offline scripts and GTK TextPanel tests are numeric zero with own PRE. With radial input disabled, approved-binding Quit, blocked provider send, queued provider-shaped tool/audio cancellation, target recapture/typed Yes, provider-menu capture, active tray Stop and controlled-pipe voice cleanup have app/driver zero. Actual Type refusal and Speak starting/listening pixels were inspected; the external XFCE plugin dialog remains. Earlier wrapper timeouts are retained, not clean-shell claims. No new provider/model/key, no physical input/audio device or full Mac/Linux port claim. Native X hangs, non-atomic focus, missing target-selection override, JEV and wider product UI remain open.

## Prior bounded checkpoints

# R54 opt-in radial visual/monitor preview

The pinned Mac GlobalRadialInputShortcutMonitor, RadialInputSwitcherView and CompanionManager define a Control+Option+Command hold, a fixed cursor-centered gesture, 24px deadzone, three angular regions, and last-hover fallback on release. Linux `--radial-preview` implements that visual/monitor/state slice with Ctrl+Alt+Super and no Shift. Speak/Type/Highlight input-mode dispatch is deliberately unconnected. Both the visible footer and release status say preview/no dispatch. This is not the endpoint of the full-port assignment and does not silently route Mac JEV-only Type into Gemini.

The preview cannot coexist with this runtime's --voice or --highlight: sequential modifier presses/releases expose partial chords that can activate those monitors. Both combinations refuse before UI/thread startup. A visible warning asks users to close separate Ask/shortcut apps; this process cannot prevent another process's shortcuts. Actual X tests cover three modifier orders and release overlap. Adding Shift ends the selection and removing Shift starts a new hold, matching the pinned flags-change semantics, not an invented cancel behavior.

The popup does not focus or intercept pointer input, is included in own-window capture exclusion, and has owned monitor stop/join and post-close callback rejection. A native X query exception hides/cancels with an unavailable status; a truly hung native query can still leave the daemon pending. Near-workarea-edge placement refuses while preserving the original gesture center, rather than clipping or moving the wedges. The Linux canvas has overflow padding and a preview footer. Noncomposited desktops use opaque black capsules for readable text; the first alpha fallback was visually illegible and retained as a failed visual. SF icons, shadows, spring/fade animation and composited alpha have not been reproduced or validated.

Runtime source82eb7420 has own-PRE numeric-zero state, actual modifier-monitor and injected-UI tests: wedges/deadzone/last-hover fallback/cancel/all masks; actual X sequential chords/Shift transitions and no callbacks after close; actual native button click through the visible popup and unchanged focus. The clickthrough case stops the monitor and injects GTK transitions, so it is not simultaneous modifier-held clickthrough proof. Edge/error hide and direct close-gate tests also inject transitions. The actual app active-chord Quit/release is a race test, not deterministic delivery of a queued release after Quit.

Fresh actual preview app/driver zero shows Type hover, readable preview footer, release hide/no-dispatch status, provider-bound JPEG own-preview/text exclusion, and active-chord Quit monitor joined. Capture can take the existing logged hide fallback and flicker. External XFCE plugin-dialog pixels remain in evidence; not a clean-host claim. No mode dispatch, physical input-device, real provider, compositor, Wayland or mixed-DPI proof.

The same runtime bytes have 20 offline scripts numeric zero and a fresh GTK TextPanel test numeric zero with own PRE. With preview disabled, fresh approved binding Quit/no late effect, blocked provider send cancellation, queued provider-shaped audio/tool cancellation, provider-menu capture, active tray Stop and controlled-pipe voice cleanup all app/driver/wrapper zero. Recapture first had app/driver zero but a teardown wrapper timeout retained; rerun app/driver/wrapper zero. Controlled voice is scripted-provider/subprocess-pipe evidence, not physical microphone/STT/audible reply. No blanket full-regression or full-product claim.

## Prior bounded checkpoints

# R53 documentation correction and actual tray Stop follow-up

No runtime code changes from accepted R52 commit bd75442eae1dc31dc8fd6594941f947d1047ce1c. The README now removes obsolete no-actions/settings/unused-target/no-host claims, distinguishes the Ask tray from the separately tested runtime tray, and preserves physical-device and full-product limits.

Fresh actual X11 tests on the R52 runtime opened the tray menu during an approved five-second native binding delay. The paired control opened the same menu, dismissed with Escape and refocused the target, then produced the actual button effect. The Stop case activated the actual menu Stop, then refocused the same target: typed_stop_at_ingress was recorded and zero old button effects occurred after six seconds. Both app/driver exits are zero. The popup/focus control matters: absence of the effect is not credited merely to focus loss. Provider responses and binding delay are scripted; OS input and GTK effects are real. This is a bounded active tray Stop case, not every action timing or an atomic OS cancellation guarantee.

Inspected screenshots show the actual three-item tray menu with approved-running state, then Stopped/Pending and running work cancelled with unchanged target. The external XFCE power-plugin crash dialog remains visible and is not an app failure or a clean-host claim. No new physical audio, real provider, complete Mac UI or wider platform evidence.

## Prior bounded checkpoints

# R52 bounded tray controls and owned shutdown

Opt-in `--text-ui` now owns a GTK3 status icon with Open text command, Stop and Quit TipTour. The host must support legacy status icons. This is a small Linux control surface, not the full Mac CompanionPanel, settings, logs, pin, radial input or onboarding parity. Tray Open intentionally clears the captured target: focus the target app and press Ctrl+K before submitting. This extra explicit handoff is a conservative Linux UX difference, not immediate Mac target capture.

Quit enters the same local ingress as the other controls, invalidates pending/approved work and voice epochs, clears queued requests, cancels active async request/capture/highlight/provider waits, and rejects later callbacks. It does not undo OS input already dispatched. Client/writer retirement records closed, cancelled, failed or pending rather than claiming every resource closed. Cancellation of a to_thread capture does not kill the native worker.

Voice PTT is retained as an owned monitor, stops before cleanup and cannot restart capture after shutdown. Mic capture has a native generation independent of provider writer replacement: old capture EOF callbacks are rejected, but current capture EOF still aborts the session after a provider reconnect. Mic OFF invalidates immediately and an owned worker promptly terminates/kills/reaps children and joins readers. Reply playback uses a nonblocking subprocess pipe and one worker with a 30-second PCM backlog limit; overflow fails closed with a visible log, rather than blocking request/Stop ingress. It is not an audio quality guarantee. Player flush kills queued playback and reaps it; final close prevents reopening.

Runtime source `15786e00` has fresh own-PRE tests: actual GTK tray Quit, five-second approved binding Quit with zero old effects after six seconds, blocked 30-second provider send cancellation with one recorded final close, queued provider-shaped audio/tool cancellation, tray-open refusal then explicit target recapture and typed Yes followed by an actual target button click. All app/driver exits are zero. The recapture screenshot shows approved-running and the actual change, not completed-plan/resumed-follow proof. That harness's original closes-once assertion wording overstates its instrumentation: it checks only a closed receipt; the provider-send and voice harnesses have explicit close counters.

Controlled subprocess audio tests use real pipes and X11 PTT with a scripted provider, never physical devices or real STT. Ignore-TERM Mic children and nonreading Player children are killed/reaped and workers joined; rapid PTT during cleanup creates no new child. Delayed old Mic EOF after a new capture/writer is rejected; a single capture through tainted-provider replacement then EOF aborts the current session. Native spawn OSError aborts without crashing. Adapter, GTK and shutdown units are numeric zero with their own PRE; 19 offline scripts are numeric zero. Earlier failed/narrower fixture ordering runs and corrected labels remain in external evidence, not erased.

Provider-bound JPEG pixels were inspected: own menu/text absent and external XFCE host/plugin dialog retained. Popup exclusion follows the menu's native toplevel, with a popdown fallback that does not reopen a dismissed menu. Unsupported root backing still uses hide fallback and may flicker. The before frame lacked the pointer, so this pair does not independently prove pointer exclusion. No universal detached-popup, compositor or Wayland claim.

A genuine cancellation-resistant close was never released: cleanup reported pending, GTK returned and the app process exited zero, while its daemon async runner could remain in final cancellation drain until process exit. This is not a clean provider close or a universal shutdown deadline. Hung native X queries can leave a monitor/worker pending; cleanup reports false where detected. Hung native capture/default-executor work and other stalls before GTK quit remain possible. No physical microphone, audible reply, new real-provider, mixed-DPI or whole-port readiness claim.

## Prior bounded checkpoints

# R51 bounded text-surface style

The optional text window now ships a scoped GTK CSS asset using pinned Mac DesignSystem colors: background #101211, primary #ECEEED, secondary #ADB5B2, subtle border #373B39 and input #202221. Entry text is 13px and activity 11px. Native window-manager decorations, 420px width and Linux Submit/Stop/Hide controls remain. This is not exact Mac borderless 340x64/shadow/fade/results-layout parity. No other app theme or provider/mode behavior changes.

Exact `3c3df213` source has 19 scripts numeric zero, including a fresh GTK constructor loading the CSS and cancellation/backpressure/target identity/follow-timer/monitor cleanup tests. Actual scripted-provider motion shows follow, proposal freeze, UI Yes/native selection 0..14 and completion resume; the styled GTK Stop during a five-second approved binding stall leaves zero old effects after six seconds, app/driver zero. Dark panel and actual provider-bound clean JPEG pixels were inspected. First Stop automation used the old coordinate, missed the newly sized button and timed out; it is retained as failure. The unit wrapper detached-child warning remains separate from numeric script success. No new real-provider, audio, physical input or full-UI validation.

## Prior bounded checkpoints

# R50 bounded visible follow and capture correction

The optional text entry now follows the mouse on a 16ms GTK timer, using actual outer frame extents and monitor workarea in GDK coordinates. Mac constants and candidate order are preserved with explicit bottom-left to top-left Y conversion. A too-small workarea refuses movement. The actual loop-owned pending proposal, active goal, turn, replay and resolving state continuously reconciles tracking freeze; an owned focus worker independently blocks motion. Tracking resumes at idle and the timer is removed on close. Status text remains partial; this is not full Mac fade/style/results resizing or radial dispatch.

A real new capture failure was found and retained: the moving/lowered text entry appeared in the provider-bound JPEG because GTK client XIDs were reparented under window-manager decoration frames. Exclusion now resolves the own client to its root-child ancestor while the server is grabbed, and excludes that whole frame from mask reconstruction. Fresh actual sent pixels for the moved/partly occluded case were inspected and contain only the target, not own text/proposal/pointer. Unsupported bare-root backing now takes the logged real hide fallback. This can flicker; no universal flicker-free claim is made. The earlier leaking JPEG is not a pass.

Exact candidate `bcb350c9` has 19 scripts numeric zero and actual scripted-provider GTK runs: following changes X/Y, displayed proposal freezes X/Y, UI Yes gives native selection 0..14, completion resumes X/Y; actual GTK Stop during an approved five-second binding stall leaves zero old button effects after six seconds, app/driver zero. Current provider-bound JPEG and Stop pixels were inspected. Fast no-tool recovery is supported by continuous-state code and mocked state tests, not a separate actual no-tool run. Virtual audio sections skipped; no new physical microphone, real provider, mixed-DPI or Wayland proof. A unit-wrapper detached-child warning is retained despite numeric script zero.

Radial geometry is pure policy only. Full menu/onboarding/radial UI, text fade/results/style parity, live JEV, physical voice and the wider full-port gaps remain open. Visual state pairs are screenshots, not a video or continuous recording.

## Prior bounded checkpoints

# R49 bounded Gemini startup surface

`packaging/tiptour-linux desktop` opens an optional Gemini-only Linux startup window. JEV is explicitly unavailable. It uses the existing model and configured key files, with no key writes or new providers. Key entries are only detected, not validated for quota or authenticity. Readiness and runtime share a loader that skips unreadable files, directories and invalid encodings without printing secrets. Detected X11/tool/GTK/OCR conditions are not accessibility or microphone permission grants. AT-SPI app access and microphone capture remain unverified until use. Missing voice tools disables voice; text and point-only are default, actions/voice require explicit checkboxes.

The initial target probe has a 0.2-second deadline and freezes its result before building the UI. A late result cannot change the displayed or launched target. Timeout gives no target and disables Start. The setup window has its own TipTour WM_CLASS. The target is shown as an X11 ID; change it by closing setup, focusing the desired app and reopening. After setup closes, launch rechecks identity and restores focus, then executes the existing runtime. This post-UI restore can hang in Xlib; xdotool activation has a two-second timeout. No zero-blocking or atomic focus guarantee is claimed.

Bare-root clean-capture fallback now temporarily disables focus-on-map only while restoring the text entry window, preventing the observed own-entry focus steal. This is a narrow text-window fix, not an all-own-surfaces guarantee.

Exact final `0963da88` source: deadline/late-identity and key-loader negative tests numeric zero, current setup pixels inspected, actual GTK Start and text request then FIFO Yes/Stop into the original point-only proposal/pointer path, app/driver zero. The previous `51048799` head has 17 non-GUI unit scripts zero, direct app UI Yes -> native selection 0..14 and GTK Stop during an approved five-second binding stall with zero old button effects after six seconds. Those are prior-head checks, not a fresh full final-head suite. All model responses in these new UI runs were scripted; no new real provider, physical microphone or voice validation. Earlier failed startup-coordinate, typing and refused-focus fixtures are retained.

This is not full Mac onboarding, menu, radial input, text mouse-follow/frozen/ticker, JEV transport or whole-port completion. Earlier checkpoint limitations remain below.

## Prior bounded checkpoints

# R48 bounded text adapter

Opt-in `--text-ui` adds a GTK command entry and Ctrl+K listener to the same local ingress, immutable proposal and displayed local Yes path. It does not add JEV transport or a second execution route. Escape hides the entry, Stop cancels pending/running work and an unsubmitted focus handoff, and recognized local runtime events update a partial status label. Own text UI is excluded from model captures. X11 target identity is bound to window ID, PID and WM_CLASS; unrelated invalid focus or a backpressured show clears the captured target. Only reopening from the exact own entry preserves an existing captured target.

One async focus worker is allowed at a time. Stop/show/dismiss invalidate old completions, and cancellation is checked after identity lookup and before activation. A waiting activation client is terminated on cancellation. Focus activation already delivered to the window manager cannot be recalled, and the final focus/OS dispatch check remains non-atomic. A truly hung Xlib call can leave one daemon worker busy. The normal monitor closes its XDisplay on exit; normal destroy cleanup is tested. Shortcut polling is 30Hz and may miss short presses. No immediate CPU cancellation, zero response delay or zero late focus is claimed.

Evidence boundaries: final source `3a701bde` has numeric-zero extended TextPanel state/cleanup tests and actual fake-model UI request/Yes -> native selection 0..14, reserved-control refusal, own/invalid identity refusal and Escape target-focus restoration. Its prior `2a93f125` head has all 17 scripts numeric zero and actual GTK Stop during a five-second approved native binding stall with zero old button effects after six seconds. These are not fresh-final-head active Stop or full-regression claims. Virtual audio sections were skipped; no new voice/provider validation. Two earlier short-chord automation failures, a preexisting-selection assertion failure and their timeouts are retained. Combined runtime wrappers warn about detached-child cleanup despite app/driver zero, not claimed clean shell completion. Pixels inspected include displayed proposal, final selection, stopped status and provider-bound JPEG own-UI exclusion.

Full Mac menu, onboarding, radial input, mouse-follow/frozen text panel, full activity ticker, shortcut settings, JEV live flow and physical voice remain open. This is a bounded opt-in Linux text adapter, not a whole-port readiness claim.

## Prior bounded checkpoints

# R47 read-only facade candidate

R47 adds an opt-in `--readonly-harness` on loopback port 19474. It exposes read-only health, observe, skills, targets and screenshots through the existing runtime. No action, task or plan endpoint is registered; external `execute=true` is never local approval. Screenshots honor the screenshot toggle and existing own-window exclusion. Active application uses Linux WM_CLASS; bundle identifier is unavailable. This is a partial facade, not full HTTP, UI or JEV integration.

Read captures do not replace approval/utterance pins. Read perception has a private cache and does not publish the shared runtime target cache or generation. Observe uses the real runtime detection count. Capture reads are refused while a plan/turn/replay/resolution is active. One owned read worker serializes queued/running/finished state: queued cancellation frees the slot; a running timeout keeps it busy until actual exit. Final cancellation check and response completion share the ownership lock. A whole native capture/perception pass already in flight can continue CPU use, including OCR after a stalled detector, until it returns. Cancellation prevents late publication and a stale successful response; it is not immediate CPU cancellation or zero interference.

Current finalization source has an actual simulated-model GTK/HTTP run: observe, skills, refreshed targets and screenshot reads; POST refused 405; browser Origin and non-loopback Host refused 403; local typed Yes then actual selection 0..14, app/driver 0. A thread test cancels immediately before payload return and gets no stale result. Earlier owned-source runs tested an 18-second detector stall: HTTP timeout at 15.0017s, backpressure until worker exit, STOP processed, runtime count 14 unchanged; a delayed approved-click binding refused read captures and STOP left zero old effects after six seconds. Those runtime records retain their exact source boundaries. Earlier failed 503 and timeout runs are retained, not counted as passes.

Previously pushed bounded checkpoints on feature/linux-port: R42 `313f900`, R44 app skills `983d374`, R45 offline JEV contracts `fd27bbb`, R46 pure visual-context policy `2715fbf`. JEV has no live transport, key access or provider call; its strict numeric/top-level JSON boundary is not a full typed answer decoder. Pure visual policy is not capture/crop delivery. Full product UI/onboarding/radial/tutorial/JEV flow, remaining skills input/menu behavior, HTTP action integration, physical mixed-DPI/Wayland and real voice STOP/partial-intent edges remain open. No whole-port readiness claim.

## Earlier source-bound R44 report

# R44 app-skill checkpoint

Portable app-skill registry is copied from the pinned Mac contract: user/project/bundled roots, front matter, structured runtime hints, app matching, first-match aliases, numeric-policy queries and info records. Bundled Blender markdown is unchanged from the pinned source. Linux uses desktop id in place of a bundle id; lexical file order makes unspecified Mac enumeration deterministic. The candidate constructs a registry at each proposal rather than the Mac shared startup snapshot; this reload/performance difference is explicit and remains to be aligned. Non-JSON and nonfinite numeric hints are rejected, including JSON overflow to infinity.

Only semantic keyboard-step normalization is wired into the live path, before proposal display/hash/approval. A `select all` semantic key in an ordinary app becomes the original Cmd+A contract (Linux dispatch maps Cmd to Ctrl); Blender's existing structured alias takes priority. No action happens on load or normalization. Numeric physical-key delivery, menu-region filtering, HTTP skills exposure and planner integration remain unported. Consecutive type coalescing is not changed in this candidate.

R44 actual GTK run with a simulated model: proposed click first, then displayed Cmd+A, typed Yes, selected exactly 0..14 of `hello original`, app/driver exit 0. This is not a real-provider app-skill inference claim. Twelve offline scripts exit 0, including the new skill contract and existing action/approval tests. Current STOP-after-render and saved-range two-edit regressions exit 0. R44 does not inherit R42's whole runtime evidence without rechecking.

# Current evidence ledger

## Latest candidate: R42 product, R43 documentation

R43 changes documentation only. R42 source archive SHA256 is 569339a5ba25e7e7f6314294dac9a9155235ef295bfa01efa847ba177b27ab9c. Bounded checkpoint only, not release or whole-port acceptance. Older sections below describe their exact historical heads and are not current runtime credit.

- Current real original Gemini static GTK four-click plan completes actual effects 1..4 once after typed Yes. The same case with a real XFCE desktop window has zero capture-hide fallbacks. Bare-root Xvfb runs need fallback when own UI covers unbacked desktop pixels.
- Current real virtual-microphone STT produces a held click/pointing plan; spoken Yes approves the same stored plan and points at the Message field with actions OFF. It awaits a human click, so this is not an end-to-end completion or active voice cancellation pass. An earlier attempt had a dead Pulse server and is retained as a nonpass.
- Current simulated five-step dynamic fixture has actual effects 1..5 once, no explicit retries in this particular continuous recording, and no capture-hide calls/fallbacks. This is not a real-provider dynamic inference benchmark, the original missing wizard, or proof of general loading recovery.
- Current actual send_screenshot JPEG/desktop pair while an approved target is held shows the labeled pointer on desktop and neither pointer nor label in provider-bound bytes. The receiver is a simulated provider. New unrelated typed asks intentionally retire the old plan and therefore cannot prove held-label exclusion.
- Twelve current unit scripts have numeric exit records and PRE snapshots. Current integer-scale input fixtures each produce two intended effects; their bare desktop cases log capture-hide fallbacks, so these are not flicker-free cross-scale proofs.
- Typed new requests during delayed native binding or final modal read revoke old execution and leave revision 2 pending with zero old effects. Completed eligible simulated voice new requests revoke old execution. Partial/straddled/late-completion voice cases remain unverified. Duplicate yes, no and whitespace do not revoke an already-approved plan; STOP still does.
- Current typed STOP after render yields no click; current saved-range two-edit fixture ends hello NEW! world, caret 10. The earlier R37 folders named stop/range omitted required flags and do NOT establish these results.
- Current capture-worker test injects an eight-second stall after the X server grab; a 1.5-second parent timeout kills it and an independent X request succeeds in about 4.4ms afterward. This bounds a possible stall, not a zero-freeze claim. Double capture failure restores UI only for the original token.

Latency: R34 three simulated typed-approval/native-click samples had a 3972ms median to actual GTK callback. R39 dependency-aware samples had a 3135ms median, but these small sequential runs are not a reliable general speedup estimate or provider/voice latency measurement. Mac autopilot minimum is 0.28s, not 1s. A 0.28-only trial clicked before the validator baseline was ready and failed to advance. Current code overlaps native binding with the minimum delay, waits for the same step baseline (bounded and token-cancellable), then retains final focus/native/modal/input checks. Parallel YOLO/OCR and thread-tuning trials did not improve this environment and were rejected.

Open: coherent final source/whole-port audit, current-head full voice supersession edges/real voice STOP, broader physical and mixed-DPI support, translucent/multiwindow/current-underlying-change capture coverage, root-global redirection coexistence/performance, bare-root unsupported capture fallback, and product UI/tutorial/JEV/skills/HTTP areas. No global flicker fix or whole-product readiness claim.

## Earlier checkpoints


These are bounded test results, not release clearance. Runtime evidence is tied to the exact source captured before each run. R30 changes documentation only from R29; do not describe R29 snapshots as a separately executed R30 run. Historical logs and failures remain available in HISTORICAL_PARITY.md and the original test archives.

## Source checkpoints

- R23 source archive SHA256: 5a6cd364a492b2865548f0dcf177deee18f2e44d94be13b43a05d0b067889336.
- R29 candidate source archive SHA256: fa997708e9bbaeab5ebed2379ab82da67d73c36f7c356aeb8571113198dd3df8.
- Historical pre-checkpoint Git state was local R20 aadd25029c1701ab29d5014fce0e2b571ffa5257. The accepted R42 product checkpoint is now pushed at 313f900662d3de522e89b6033f8b4f50347c2332 on feature/linux-port and checkpoint/linux-r42-opaque-x11. This is not whole-port acceptance.

## R23 bounded runtime

Real Gemini static four-click proposal -> typed Yes -> actual effects 1..4 once -> completion. Real Gemini STT from generated speech through a virtual microphone -> held plan -> spoken Yes -> one observe/point step complete. Separate spoken STOP cancels a pending proposal, not a post-approval dispatch. Physical synthetic X11 old Confirm press/new revision release does not approve the new plan; fresh click does. Native selection, browser plain-input, modal, window, integer-scale and cancellation tests passed in their recorded scopes.

A 51.85-second continuous recording shows actual pointer movement and page callbacks 1..5. The plan was simulated; two explicit retries recovered loading and movement. It is not a real-provider dynamic-task success or physical desktop validation. Capture-hide flicker is visible and reproduced with timed visibility logs.

## R29 candidate bounded runtime

- No-hint owned control appearing within the tested budget resolves and the two actual effects complete.
- Missing target produces a visible failure panel. Explicit Retry after a controlled page change completes; Skip ends the plan without a second effect.
- Injected late capture expires at 3.5081 seconds without late input. Separate slow-read cases are cancelled by STOP or STOP plus a new pending proposal, not by an observed deadline expiry; they do not publish the old failure.
- STOP at the final pre-arm read boundary prevents pointer/dispatch; this does not force the narrower interleaving after that read returns. Failed test-harness attempts that created a regular file instead of a FIFO are retained separately and are not product failures.
- Delayed capture during the resolution budget returns after timeout without reviving the overlay through its old restore callback. Separate STOP during capture also remains covered in its stated scope.
- Production PausePanel widget old-press/new-episode-release Retry and Skip are suppressed after per-episode widget/token binding; fresh clicks work once. This isolated-widget test is not a complete whole-app callback-race proof.
- Typed confirmation, Chrome plain-input chain, browser negatives, native saved range, post-render typed STOP, nested modal, duplicate same-process windows, missing/late-lost mapping and virtual integer 100%/200% tests passed on exact recorded R29 bytes.
- Eleven unit scripts have pre-execution tree snapshots and numeric zero exits. This does not replace runtime or independent source review.

## Still open

Current-head real-provider and voice repeats, post-approval real voice STOP and native-write cancellation, click bypass coverage, full source parity and product UI gaps, physical/mixed/fractional display support, and the unresolved capture flicker. No blanket action, smoothness, semantic equivalence or whole-port readiness claim.

## Evidence archive identifiers

R29 candidate evidence: 6b31fa12465fca79ffe7bd4c5542b7eb6be929a785634e5e61290e498b747e5f.
R29 more cancellation: 0ee3187d9f63f8455fe25b578449f3d9724bffa478d5ef0183abe5ccb366b1e0.
R29 units/display: d39dbee3783b5822d44ddd007d55c390b96161d08eb4b008ef2589bef06c2d3d.

The archives contain test-only seams where stated. A zero exit is not completion unless the actual effects and assertions support it.
