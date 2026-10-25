# Ask harness: scribble + voice clipboard handoff

Branch: `fix/ask-preview-close-copy-gate` (built on `a4993b2`).

Hold **Ctrl+Option+Shift**, say your question out loud, release. TipTour
captures the screen under your cursor, draws your scribble (the
Ctrl+Shift focus highlight) onto the image, transcribes what you said
on-device, and opens a preview. Use **Copy both**, **Copy image** or
**Copy text**, then paste yourself. The receiving app decides whether it
accepts image, text or both. Direct insertion is optional and off by
default. Nothing is ever sent - sending stays with you.

Scribble first with the existing Ctrl+Shift highlight, then add Option
while keeping Ctrl+Shift held: the highlight commits and the capture
starts with those markings. Capturing without a scribble works too.

## How it works

- **Capture**: pressing the hotkey starts an asynchronous
  ScreenCaptureKit capture of the cursor's display at its native pixel
  scale (`pointPixelScale`, falling back to the NSScreen backing scale).
  The image returns a short moment after the press, so the screen may
  have changed; the preview shows the actual completion time and the
  delay. It does not promise the screen is unchanged.
- **Markings**: strictly bound to the ask gesture. Only a highlight still
  in flight when the chord is pressed, or one committed by the ask chord
  itself within ~1.5s, is used; earlier, separate highlights are never
  reused. The capture excludes TipTour's windows, so the trail is drawn
  onto the image afterwards (off the main actor) with the same stroke
  style as the overlay. It shows where you drew, not necessarily what was
  under it at the capture instant. If any scribble point is off the
  captured display, markings are rejected entirely and the preview says
  so (multi-display scribbles are not supported).
- **Provider independence**: Option being added commits the focus
  highlight. That commit is recognised from the committing event's own
  modifier flags (Ctrl+Option+Shift) and is never sent to Gemini, even
  when a Gemini session is active. The harness makes no provider calls.
- **Sessions**: each press gets a generation. A release moves the session
  to "finishing"; a re-press while finishing is ignored with a hint, and a
  cancelled or superseded session can never publish a preview.
- **Transcription**: `SFSpeechRecognizer` with
  `requiresOnDeviceRecognition = true`. If the active locale reports
  `supportsOnDeviceRecognition == false`, the flow stops with an
  explanation instead of sending audio to a network service.
- **Clipboard copy**: the preview has **Copy both**, **Copy image** and **Copy text**. They leave the marked image and/or your question on the system clipboard (the clipboard is not restored afterwards, so the copy stays until you paste) for you to paste into your chosen app or site; acceptance depends on that app or site. **Copy both** writes one item with PNG and text flavors; which flavor an app reads is the app's choice, so use the single-flavor buttons when an app takes only one. Direct insertion into a named app is optional and off by default (no ChatGPT default). Copy both with an empty question explicitly reports image-only copying. Editing the preview clears the old copy confirmation. A pending copy is invalidated by edits, closing the preview (Close button, Escape or the window's red close), a new capture, or a newer copy request, and cannot overwrite the clipboard or publish its result after that invalidation; copy again after editing. A copy failure is reported, not shown as success.
- **Preview**: floating panel with the image, editable transcript and a
  target-app picker (running apps plus the configured default). Closing it
  (Close button, Escape or the red close) cancels the preview and drops
  any pending copy.
- **Insertion**: the target app is activated and verified frontmost. The
  focused element must be a multi-line text area (search fields, combo
  boxes and single-line text fields are refused), and the exact focused
  window + element is captured and re-checked before every paste (the
  app pid alone is not enough). If the composer can't be identified,
  nothing is pasted and you are asked to click into the message field
  yourself and retry. Image then text are staged on the pasteboard and
  pasted with a synthesized Cmd+V to the target's pid. Return is never
  pressed. The pasteboard change count is recorded right after each of
  our writes; if you copy something meanwhile, the sequence stops and
  your newer clipboard is never overwritten or pasted. The previous
  clipboard is restored only while we still own it, on success, failure
  and cancel alike. A retry after a partial insert skips pieces already
  pasted instead of pasting them twice.

## Setup on your Mac

1. Open `tiptour-macos.xcodeproj` in Xcode (macOS 14.2+, your signing
   team) and run TipTour.
2. Permissions the harness needs:
   - **Screen Recording** (already used by TipTour) for the capture.
   - **Accessibility** (already used) for the global hotkey and Cmd+V.
   - **Microphone** and **Speech Recognition** (new prompt on first use)
     for on-device transcription.
3. Settings > Advanced > **Ask Direct Insert App (optional)** is empty by default.
   Leave it empty to copy and paste yourself. For optional direct
   insertion, enter an installed app's bundle identifier or pick a
   running app in the preview; the choice is remembered.

## Honest limits

- **Not yet run on a Mac.** Built and reviewed on Linux without Xcode;
  UI pixels, the capture/composite pipeline, and the paste flow all need
  a real Mac pass before calling this working.
- Whether a given app's composer accepts a pasted image or pasted text
  is app-dependent and unverified. Each paste is a best-effort attempt:
  the app may accept the image, the text, both or neither, and TipTour
  cannot confirm what the app accepted. Check the draft in the target
  app; test with your target first.
- "On-device" covers transcription only. The target app may sync its own
  drafts, and macOS may sync the staged clipboard (Universal Clipboard)
  while it is staged.
- Paste timing is a heuristic. The target app gives no signal when it has
  consumed a paste, so TipTour waits ~0.8s after the image and ~1.5s
  before restoring your clipboard. A slow app can miss a paste or read
  the clipboard after the restore. The result message says to check the
  draft; there is no timing guarantee.
- The trail fades on screen a few seconds after you finish scribbling;
  the composited image shows the markings at full opacity.
- The harness is independent of the Gemini/JEV modes and uses no
  provider keys or network calls.

## Tests

`scripts/test-ask.sh` runs the pure logic (coordinate mapping, session
generations, clipboard ownership with a fake pasteboard, copy-mode
flavors, copy-request gate and copy-outcome reset rules, composer role
policy, chord provenance, markings and sizing decisions) with SwiftPM and
no Xcode. It does not cover capture, compositing pixels, event taps, AX,
the paste flow or the AppKit window-close wiring that calls those reset
rules; those need a Mac.
