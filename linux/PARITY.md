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
