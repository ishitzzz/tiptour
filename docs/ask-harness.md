# Ask harness: scribble + voice to any app's composer (draft)

Branch: `feature/ask-scribble-harness` (built on upstream `c1d2731`).

Hold **Ctrl+Option+Shift**, say your question out loud, release. TipTour
captures the screen under your cursor, draws your scribble (the
Ctrl+Shift focus highlight) onto the image, transcribes what you said
on-device, and opens a preview. From the preview you pick a target app
and press **Insert as draft**: the image and the question text land in
that app's composer. Nothing is ever sent - sending stays with you.

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
- **Preview**: floating panel with the image, editable transcript and a
  target-app picker (running apps plus the configured default).
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
3. Settings > Advanced > **Ask Draft Target App** sets the default
   target bundle identifier (`com.openai.chat` = ChatGPT Mac app). The
   preview's picker overrides it per use and remembers the choice.

## Honest limits

- **Not yet run on a Mac.** Built and reviewed on Linux without Xcode;
  UI pixels, the capture/composite pipeline, and the paste flow all need
  a real Mac pass before calling this working.
- Whether a given app's composer accepts a pasted image is app-dependent
  and unverified. If an app ignores the image paste, the text still
  lands; test with your target first.
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
generations, clipboard ownership with a fake pasteboard, composer role
policy, chord provenance, markings and sizing decisions) with SwiftPM and
no Xcode. It does not cover capture, compositing pixels, event taps, AX or
the paste flow; those need a Mac.
