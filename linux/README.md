# TipTour Linux port (experimental, X11 only, NOT a full port)
Branch feature/linux-port, base upstream 6e97782. Python/GTK3. See PARITY.md for exactly what is verified and what is not.

## Setup
- apt: python3-gi gir1.2-gtk-3.0 python3-cairo xdotool tesseract-ocr gir1.2-atspi-2.0 at-spi2-core; pip: see requirements.txt.
- Detector model: `python3 tools/mil_to_onnx.py ../TipTour/UIElementDetector.mlpackage /tmp/uielement.onnx` (needs onnx + coremltools). Without it the app falls back to raw model coordinates, drawn with a "?" and reported as unconfirmed.
- Gemini API keys: files only, never in the repo. `TIPTOUR_KEYS_GLOB='/path/keys/*/password'` (one key per file). Use a free-tier key.
- X11 session required (no Wayland). Single display, devicePixelRatio 1.

## Chrome accessibility (launcher responsibility)
Chrome only exposes its accessibility tree to AT-SPI when started with it enabled:
1. Start the AT-SPI bus BEFORE Chrome (`/usr/libexec/at-spi-bus-launcher --launch-immediately`, or a normal desktop session).
2. Launch Chrome with `ACCESSIBILITY_ENABLED=1 GTK_A11Y=atspi` in its environment and `--force-renderer-accessibility`.
3. For the browser stage start Chrome with `--remote-debugging-port=9222` (CDP, localhost only). The CDP stage and the DOM-selection fallback need it; both bind to the foreground window and a single focused tab, and refuse otherwise.
The first AT-SPI walk after Chrome starts is slow and AT-SPI can report UNAVAILABLE (never "none") when stale or empty; this is a known reliability gap.

## Run (point-only by default)
`python3 -m tiptour_linux.app --highlight --serve /tmp/tiptour.fifo --out /tmp/tt-out` then Ctrl+Shift+drag to highlight, and write utterances to the FIFO. `--voice` adds push-to-talk: **Ctrl+Alt (no Shift/Super) toggles a live voice session** (Mac source: Control+Option press edge); the mic is streamed as PCM16 16 kHz to Gemini (server-side VAD) and replies are played through paplay. Needs PulseAudio/pipewire-pulse (`parec`, `paplay`); `TIPTOUR_MIC_SOURCE` / `TIPTOUR_AUDIO_SINK` pick devices. The spoken request's input transcript is what the no-action/scope/intent gates read; no transcript means no pointing. Only tested with virtual audio devices and synthetic speech, never a physical microphone or real keyboard.
`--act` enables click/type actions: it is OFF by default and has NEVER been run live.

## Privacy defaults
- Highlight with Alt/Option held at release stays local. A normal release sends a fresh screenshot plus a context prompt to Gemini.
- trace.log / stdout carry no window titles, element labels, utterances or replies unless `TIPTOUR_DEBUG_LOG=1`. Debug env: `TIPTOUR_DEBUG_ATSPI*` (prints labels/selected text), do not use on real data.
- `--out` DIR holds test artifacts (screens, sent frames, prompt dumps, results.json with utterances/labels/window titles). Treat it as sensitive; it is a test/verification output.
- Test-only seams (`TIPTOUR_CLIENT_FACTORY`, fake client) work only with `TIPTOUR_TEST_MODE=1` and live in tests/.

## Licenses (facts from the repo, not legal advice)
Repo source: MIT (../LICENSE). The bundled detector (TipTour/UIElementDetector.mlpackage, model.mlmodel metadata) states Ultralytics YOLO11m under AGPL-3.0; the ONNX file this port generates is derived from those weights. NekoSprites: BSD-2 (TipTour/NekoSprites/LICENSE-NEKO.txt). Shipping the detector weights inside an MIT-licensed product needs a decision by the owner; none is made here.

## Ask harness (experimental, X11)
`packaging/tiptour-linux ask` (or `python3 -m tiptour_linux.ask`): hold Ctrl+Alt+Shift, speak, release. A preview shows the screenshot and the transcript;
Copy text / Copy image / Insert draft (pastes into the window focused at press, never presses Enter) / Cancel. Needs xclip, xdotool, GTK3, and for speech
`pip install vosk` plus a Vosk model dir in TIPTOUR_VOSK_MODEL (the Mac app uses on-device SFSpeech). Scribble is not ported. Tested only with a virtual mic and synthetic speech
under Xvfb+xfwm4 and an owned GTK entry; no physical mic/keyboard or settings UI. The separate runtime --text-ui mode has a small status icon, described below. The .desktop file is untested on a real desktop.

## Settings and launcher
`python3 -m tiptour_linux.settings list|get K|set K V` edits ~/.config/tiptour-linux/settings.json (keys: isScreenshotStreamingEnabled, useAtspi, useCdp, askTargetWmClass [stored, unused]). Explicit env vars win. The Mac default isAutopilotEnabled=true is not mirrored; actions need --act on the command line and are untested. `packaging/tiptour-linux ask|voice` is a shell wrapper (ask path ran through it in the virtual test); the .desktop file, tray icon and a settings window do not exist or are untested.

## Ask target chooser, settings window, tray (update)
The Ask preview has an "Insert into" chooser: the window focused at press (default) or any app by WM_CLASS (must match exactly one window, otherwise refused). The choice is stored as askTargetWmClass (replaces the Mac askTargetBundleIdentifier; the earlier stored-unused key is gone). `tiptour-linux settings gui` opens a settings window (3 toggles). A tray icon (Gtk.StatusIcon with Settings/Quit) is coded best-effort inside `ask` and has NOT been seen on any desktop; no tray host exists in the test environment.

## Optional runtime status icon
`--text-ui` owns a legacy GTK status icon with Open text command, Stop and Quit TipTour. A compatible desktop host is required. Open clears the target: focus the desired app then Ctrl+K before Submit. Stop and Quit use the local cancellation path. This is not the full Mac menu panel. Reply playback uses a bounded nonblocking PCM backlog and fails closed if overwhelmed; audio-device and native-X hangs remain possible. Read the R52 PARITY section for exact tests and limitations.
