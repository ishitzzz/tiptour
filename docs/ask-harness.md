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

- **Capture**: ScreenCaptureKit captures the cursor's display. The
  capture excludes TipTour's own windows, so the visible trail is NOT in
  the raw image; `AskMarkingCompositor` composites the focus-highlight
  points onto it with the same stroke style as the on-screen overlay
  (Catmull-Rom smoothing, three halo/bloom/core layers, `#4F8EF7`,
  quadratic tail fade), mapping AppKit points to image pixels through
  the display frame and the capture's pixel size (Retina-safe).
- **Transcription**: `SFSpeechRecognizer` with
  `requiresOnDeviceRecognition = true`. If the active locale reports
  `supportsOnDeviceRecognition == false`, the flow stops with an
  explanation instead of sending audio to a network service.
- **Preview**: floating panel with the image, editable transcript and a
  target-app picker (running apps plus the configured default).
- **Insertion**: the target app is activated and verified frontmost
  (aborting if not, so nothing lands in the wrong window), and its
  focused accessibility element must be an editable text role before
  anything is pasted - if the composer can't be confirmed, the insert
  fails closed and asks you to click into the message field and retry.
  Focus is re-verified between the image and text pastes. Image and text
  are staged on the pasteboard and pasted with a synthesized Cmd+V to
  the target's pid. Return is never pressed. The previous clipboard
  contents are restored only if the pasteboard's changeCount shows
  nothing else was copied while staged; a skipped restore is logged and
  reported. Keep in mind Universal Clipboard can sync staged content to
  your other devices during the short staging window.

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
  drafts, and macOS may sync the staged clipboard - see above.
- The trail fades on screen a few seconds after you finish scribbling;
  the composited image always shows the markings at full opacity. The
  screenshot and the markings are frozen at the same moment (hotkey
  press); a scribble committed more than ~6 seconds earlier is not
  reused, so markings never overlay content that changed since. The
  preview labels the capture time and flags when markings came from an
  earlier scribble.
- The harness is independent of the Gemini/JEV modes and uses no
  provider keys or network calls.
