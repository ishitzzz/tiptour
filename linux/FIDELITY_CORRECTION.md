# Fidelity status

## Current R42 product changes

R43 is documentation-only. X11 Composite backing capture now keeps own UI visible while excluding the pointer, pause and proposal windows from supported model screenshots. Preparation redirects root subwindows automatically; capture readback runs in an isolated child with a 1.5s watchdog. Unknown background, translucent backing or unsupported servers use a logged hide fallback. A normal XFCE desktop window is tested without fallback; bare-root Xvfb is not universally fixed. Do not claim global compositor support or zero desktop stall.

Autopilot minimum now follows pinned WorkflowRunner130: 0.28 seconds, with identity binding overlapped. Automated clicks explicitly wait for their own validator baseline readiness, bounded at eight seconds and cancellable. A new meaningful typed request revokes old execution at ingress. A completed eligible new voice request or replacement proposal also revokes it; partial voice intent is not guessed. This conservative proposal boundary is an explicit user-requested confirmation adaptation.

Current scope and evidence are in the first section of PARITY.md. Historical R29/R30 open statements below do not supersede that latest ledger.


Baseline: 6e97782039b57a3f3dcd5a8bf7101438ba6b1c37. Historical implementation notes are preserved in HISTORICAL_FIDELITY_CORRECTION.md and must not be read as current status.

## Established source decisions

- Preserve original Gemini model and extracted prompt/schema; OS substitutions and user-approved multi-step/propose-then-yes changes are explicit in live.py.
- Mac WorkflowRunner uses a 3.5-second resolution budget, 0.9-second AX poll, 200ms between misses, and an 80ms post-click settle before fresh capture. This is distinct from waitForState, which the pinned Mac skips. Hinted resolution may accept a raw model coordinate immediately; automatic waiting on every hinted miss would be a redesign.
- Current R29 candidate bounds resolution reads only, not valid OS dispatch. No-hint failure shows Retry/Skip; original operation eligibility is checked before failure mutation and before arming. Late capture restore is token-bound. These changes remain under review.
- Mac rejects disabled candidate controls but traverses their children. Linux adapts this through AT-SPI ENABLED on interactive roles.
- Mac capture excludes its own windows. Linux currently hides the pointer for screenshot capture and restores it. A timed reproduction confirms visible quarter-second flicker. This is a known visual flaw, not proof the model needs hidden-pointer screenshots.

## Unresolved and non-equivalent

- Full source audit and coherent final-head regression review are not complete. Passing bounded fixtures does not establish a faithful whole-product port.
- Current final candidate needs its own real-provider, voice, click-bypass and remaining action-cancellation repeats. Earlier R23 results are not inherited.
- Reconstructed dynamic wizard is not the missing original wizard fixture. Its hinted five-step test needed two explicit retries. No claim of general automatic loading recovery.
- No physical microphone, mixed-DPI/negative-origin/fractional display or Wayland validation.
- X11 input and accessible-object identity are not atomic. STOP cannot undo dispatched input; path reuse and in-flight native operations have limits.
- Plain browser input uses same-object DOM setter/input event, not keyboard/undo/rich-text/saved-highlight equivalence.
- Full Linux product UI, tutorial/JEV/skills/HTTP-facade areas remain unestablished. Do not silently waive these from a request for the same TipTour.
- Pointer-in-screenshot harm has not been causally established. Small controlled image calls were inconclusive and had confounds; no production capture guard was removed.

No push or completion approval is recorded by this document.
