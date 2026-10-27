# Linux TipTour feature inventory

Read the latest R52 PARITY section for current bounded tray/shutdown/voice-lifecycle evidence. The inventory below predates those checkpoints and is not a complete current status table. Read the latest PARITY.md section before interpreting this earlier inventory. Supported X11 backing capture avoids capture-hide flicker and excludes three own UI windows; unsupported backing uses logged hide fallback. Autopilot uses the pinned 0.28s minimum with a bounded same-step validator-baseline dependency. Whole-product parity remains open.


This replaces the superseded status tables kept in HISTORICAL_MAC_FEATURE_INVENTORY.md. Those tables describe earlier unfinished builds, not current capabilities. This is a work-in-progress port, not a whole-product readiness claim.

Baseline: Mac commit 6e97782039b57a3f3dcd5a8bf7101438ba6b1c37. Linux-only adaptation plus the user-requested multi-step request and propose-then-yes behavior. Annotations excluded. No Mac/main/Dojo/Windows changes.

| Area | Current implementation | Evidence and limits |
|---|---|---|
| Gemini Live | Original model, prompt/schema extraction with explicit OS and approved multi-step deltas, key pool, audio/PTT | R23 real-provider static four-click chain, virtual-audio STT/voice approval of observe step. Later candidates need their own repeat. No physical mic or audio-quality claim. |
| Plans and approval | Multi-step stored plan, displayed revision, exact-plan approval, STOP at ingress | Typed and simulated-event negatives, physical old-Confirm press/new-Confirm release tested. Not every callback interleaving. |
| Resolution | Local cache/marks, native AT-SPI, Chrome CDP, local perception, model-hint fallback | Bound active window, integer-scale mapping, ambiguity/modal/mapping refusals. A raw model hint can still be inaccurate and does not authorize an automated click. |
| Retry / Skip / Resume | Fresh capture and full resolution; ordered advance; post-click validator | R29 candidate restores bounded no-hint resolution and failure panel. Deadline, cancellation and late-capture cases tested; independent review remains required. |
| Actions | Native click and editable text, key/shortcut/scroll adapters, cancellation checks | Owned-fixture effects verified in bounded cases. Native X11 dispatch is not atomic and already-dispatched input cannot be undone. |
| Browser text | Plain input fallback bound to same DOM object/window/frame/text/selection | Setter and input event, not literal native typing, rich text or undo parity. Browser saved-highlight replacement unsupported. |
| Saved native selection | Object/text/range bound and consumed once; next edit uses live caret | Two-step NEW then ! regression. Secret/readonly controls refused. |
| Pointer and highlight | X11 blue companion, movement/follow/retire, focus highlight | Current R42 continuous simulated five-step recording has no hide/fallback; real Gemini static four-click fixture on XFCE desktop also has none. Unsupported bare-root or translucent backing still falls back to hiding. No universal flicker-free or exact Mac-motion claim. |
| Displays | Virtual wide desktop, uniform integer 100%/200% mapping | Not physical mixed-DPI, fractional scaling, negative origins or Wayland. Unknown mapping refuses. |
| App skills | R44 portable structured markdown registry, app matching, aliases, input-policy metadata and info; semantic keyboard aliases normalized before proposal hashing/display | Offline tests and actual simulated-model GTK select-all run pass. Numeric physical-key delivery, menu-region filtering and HTTP skills exposure are not wired. No complete app-skill parity claim. |
| Product shell and other Mac features | Partial Linux shell only | Full onboarding/menu UI, radial/text-command UI, Neko/debug UI, tutorials/Elorian, JEV, skill integration and HTTP facade are not established as ported. See source audit before claiming equivalence. |

See PARITY.md for the current evidence ledger and FIDELITY_CORRECTION.md for unresolved source differences.
