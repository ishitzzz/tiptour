# TipTour Linux port (experimental, X11 only, NOT a full port)
Branch feature/linux-port, base upstream 6e97782. Python/GTK3. See PARITY.md for exactly what is verified and what is not. The R78 checkpoint adds bounded app-skill numeric character dispatch tested with an owned GTK fixture, not real Blender. A fresh four-step real-Gemini browser workflow also passes; this is not full-port acceptance. Pointing aims at the native field/widget, not necessarily its insertion caret. Selected UI tests still have two retained prior fixture failures.

## R80 app-skill lifetime

Default app skills load once on first use and are shared by plan key normalization, numeric-key delivery and read-only skill metadata. Restart TipTour to pick up later skill-file edits. Search roots and precedence are unchanged; explicit registry instances used by tools/tests remain independent. This aligns the pinned Mac process snapshot and does not turn skill files into user approval or change the local plan/Yes boundary. Controlled-provider tests use an owned GTK fixture, not actual Blender or physical input.

## R79 read-only HTTP metadata candidate

With `--readonly-harness`, GET `/v1/capabilities` and GET `/v1/agent-contract` (also `/v1/agent_contract`) describe the implemented Linux read-only subset. The listener remains opt-in on 127.0.0.1:19474. Metadata passes the same existing Host/Origin checks and does not invoke the provider or read private runtime state. Loopback filtering is not caller authentication. No HTTP action, workflow submission, task or consent endpoint is added.

The unchanged bundled Blender skill still includes Mac planner instructions referring to unsupported POST workflow/visual-context routes. This contradictory inherited guidance is an open gap, not support for those routes. Consult the Linux capabilities/contract for current HTTP support.

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
`--act` permits approved click/type/key/scroll actions and is OFF by default. Owned X11 fixtures have exercised real OS effects with scripted providers; see PARITY.md for the separate earlier real-provider evidence. This is not general desktop or physical-device validation.

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
under Xvfb+xfwm4 and an owned GTK entry; no physical mic/keyboard validation. A limited settings window is implemented, described below. The separate runtime --text-ui mode has a small status icon, described below. The .desktop file is untested on a real desktop.

## Settings and launcher
`python3 -m tiptour_linux.settings list|get K|set K V` edits ~/.config/tiptour-linux/settings.json. Keys are isScreenshotStreamingEnabled, useAtspi, useCdp and askTargetWmClass. Explicit environment variables win. The target WM_CLASS is consumed by the Ask insert chooser, not an unused placeholder. Actions stay behind explicit `--act`, never a settings-file toggle.

`packaging/tiptour-linux desktop|ask|voice|settings [gui]` routes to the corresponding entry point. `settings gui` implements three checkboxes for streaming, AT-SPI and CDP, applied to new launches, plus the current Ask target label. This is not the full Mac settings UI. The .desktop file remains unverified on a physical desktop.

## Ask target chooser and separate Ask tray
The Ask preview has an "Insert into" chooser: the window focused at press (default) or an app by WM_CLASS (must match exactly one window, otherwise refused). The choice is stored as askTargetWmClass. Ask also has best-effort GTK status-icon code with Settings/Quit; that separate Ask icon has not been visually verified in the current checkpoint. Do not infer Ask tray coverage from the runtime tray tests below.

## Optional runtime status icon
`--text-ui` owns a legacy GTK status icon with the pinned pointer silhouette and Open text command, Stop, Settings and Quit TipTour. Settings opens only the three supported Linux toggles, applies on new launches and honors explicit environment overrides; closing it does not quit the runtime. Idle streaming pauses while this menu or settings is open. Explicit request captures still exclude owned UI. A compatible desktop host is required. Open clears the target: focus the desired app then Ctrl+K before Submit. Stop and Quit use the local cancellation path. This is not the full Mac menu panel. Reply playback uses a bounded nonblocking PCM backlog and fails closed if overwhelmed; audio-device and native-X hangs remain possible. R52 verified runtime Open/Quit. A paired follow-up test verified actual tray Stop during an approved delayed binding: the matched popup/Escape control executed, while Stop followed by the same target refocus left zero old effects after six seconds. Both use a scripted provider and real X11 input. Read PARITY.md for exact tests and limitations.

## Radial visual preview (not input-mode dispatch)
`--radial-preview` opts into a Ctrl+Alt+Super hold-and-move visual preview. It cannot be combined with `--voice` or `--highlight`: partial modifier presses/releases could activate those monitors. Close separate Ask or other shortcut apps before trying it; this process cannot prevent their shortcuts. The UI says "Preview only: no dispatch". Speak/Type/Highlight release does not start any mode. This is a tested intermediate port slice, not the completed radial feature. Near-edge placement refuses instead of shifting the gesture center. X11 polling can miss short gestures or hang in native calls. Pinned Mac dispatch and mode semantics still require work; no JEV-to-Gemini substitution is implied.

## Radial Speak input (bounded, opt-in)
`--radial-input --voice` replaces the separate Ctrl+Alt voice hotkey with radial Speak toggling existing Gemini voice. Both ON/OFF stop workflow work; an in-progress start can be toggled OFF. It cannot combine with `--radial-preview`. Adding `--highlight` enables the shared Ctrl+Shift painted-highlight monitor. Type still refuses without JEV. The radial Highlight wedge does not yet capture its hover target; in combined mode it points users to Ctrl+Shift painting. Before ON, the hovered identified app must already be focused; missing/own/unknown surfaces or expired checks refuse. This is not Mac hover/selection target override parity. Separate shortcut apps can still react to partial modifier chords. See R55 PARITY for tests and limits.


## Bounded radial native-selection context
Radial Speak ON now captures the already-focused hovered native field before starting the microphone. This needs enabled AT-SPI lookup, two matching native reads and a matching hovered/focused window after the reads, within a two-second total context deadline after the initial 0.4-second target check. Missing, disabled, secret or expired context refuses without starting voice. A pending Speak can be cancelled by Speak again; Type/Highlight do not leave that pending microphone start running.

The same Gemini connection receives a capped selected-text prompt before audio starts. Explicit currentSelection/currentHighlight plans can bind the owned native selection; painted context has precedence. The displayed proposal still needs Yes. The saved range is consumed once; later edits use the current caret. Changed field/text/window/PID refuses the saved-range write, and the range path will not activate a different window. This is a tested partial hover-context port, not a general AX target override, browser selection fallback, physical-STT result or full Mac parity. Tainted provider replacement refuses stale context rather than silently reconnecting without it. Hover state expires in under 300 seconds and clears on replacement/Stop/OFF/Quit. Source and exact controlled-test limits are in PARITY.md.


### R59 shared radial and painted-highlight checkpoint

`--text-ui --voice --radial-input --highlight --serve /tmp/tiptour.fifo`
opts into one shared X11 gesture sampler. Genuine transitions between radial
Ctrl+Alt+Super and painted Ctrl+Shift can end one gesture and begin the next
without releasing every modifier. Only explicit Stop requires full modifier
release before another gesture. Quit and sampler failure cancel, never commit.

Speak admits its toggle and workflow cleanup before a later painted gesture.
A native target/context check belongs to that reserved voice attempt; finishing
it does not create a second voice edge. A normal painted release builds and
stores owned local context. During voice startup it waits for the fresh session;
while voice is active it sends the fresh screenshot/context alongside that
session without taking over its transcript/tool event consumer. Spoken
acknowledgement is requested, but global turnComplete is not proof of a separate
highlight acknowledgement. Alt-at-release remains local-only Ask behavior.
New paint retires older paint/context, not the reserved Speak startup. Stop
retires both. Existing committed context can seed the next Speak session.

Runtime evidence uses virtual X11 input, native GTK/AT-SPI fixtures, and scripted
provider/native-delay seams. It does not establish real Gemini combined-mode
behavior, physical microphone/STT, Wayland support, or complete Mac parity.
Radial Highlight target capture, JEV Type mode, and the full port remain unfinished.
X11 polling can miss fast gestures and can infer a chord already held at startup.
Native X calls or capture locks can hang: logical retirement prevents late work
from publishing, but is not a universal bounded worker-join guarantee. Shared
consumer callbacks use a short nonblocking lock contract, not a universal close
budget. Separate shortcut applications may still react to partial chords.
