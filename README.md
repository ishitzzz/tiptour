<div align="center">

<img src="gemnew.png" alt="TipTour cursor actions" width="900" />

# TipTour

**This and That**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Platform: macOS 14.2+](https://img.shields.io/badge/Platform-macOS%2014.2+-black)](https://www.apple.com/macos)

</div>

A macOS menu bar companion with two modes, powered by your own API keys.

| Mode | Shortcut | What it does |
| --- | --- | --- |
| Gemini realtime | Ctrl+Option | Talk about your screen and ask for one desktop action per turn. Press again to stop. |
| JEV text | Ctrl+K | Type a click-based task. JEV chooses from locally detected controls, then TipTour executes and validates each action. |

**JEV is selected by default.** On first launch, choose JEV or Gemini, save that mode’s API key, then grant its permissions. JEV does not require microphone access. You can switch later in **Settings → Models**, which shows only the selected mode’s key field. Keys stay in macOS Keychain. There are no shared keys, hosted key proxies, or keys loaded from other projects.

Shortcuts activate only the selected mode. The primary menu-bar button and welcome hint follow your selection.

## Using TipTour

- Gemini supports clicking, typing, shortcuts, app/URL opening, scrolling, and highlighted text edits. It also supports creating an Apple Notes note from supplied content.
- JEV supports single, double, and right clicks. It reads screen labels and locations from local detection; it cannot see images or generate replacement text. Use Gemini for writing or keyboard actions.
- Press **Escape** in the text panel or click **Stop** to cancel JEV. JEV acts on its top-ranked target without a confidence cutoff. The loop stops when JEV chooses none or reports completion, on an execution pause/failure, or at its 12-action limit.
- Hold **Ctrl+Shift** and paint over an area to give Gemini focus context.
- Hold **Ctrl+Option+Command** for the Speak / Type / Highlight shortcut chooser.
- **Auto-click** lets TipTour act. **Point only** lets Gemini indicate where you should click. JEV requires auto-click.

Settings also contains desktop action access, screenshot privacy, permissions, and optional debug visuals. TipTour does not record your screen and has no video creation or image-generation pipeline.

## Ask with a scribble (this branch)

Hold **Ctrl+Option+Shift**, speak your question, release. TipTour captures the screen you scribbled on (Ctrl+Shift highlight), transcribes the question on-device, shows a preview, and lets you **Copy both**, **Copy image** or **Copy text** to paste yourself. The receiving app or site decides whether it accepts image, text or both. Direct insertion is optional and off by default, with no preset target app. Nothing is sent automatically, and no provider keys or network calls are involved. Details and setup: [docs/ask-harness.md](docs/ask-harness.md).

## Learn from a video

Paste a tutorial link (YouTube, Loom, or a direct `.mp4`) into **Learn from a video** in the menu bar panel, or choose a video file. [Elorian](https://elorian.ai) watches the tutorial and turns it into a step-by-step tour; press play and TipTour points at each control on your own screen and waits for you to click it, type, or press the shortcut. There are no Next buttons: a step moves on when you do it, and **Escape** stops the tour. TipTour never clicks for you in a tour.

- Needs an Elorian API key (Settings → Models) and works with either mode. YouTube links need [yt-dlp](https://github.com/yt-dlp/yt-dlp) (`brew install yt-dlp`); English captions are used when the video has them.
- Building a tour takes a few minutes per 90 s of video and roughly $0.15–$1 of Elorian credit per short tutorial. Tours are saved and replay instantly.
- Each step is found on your screen with TipTour's local grounding first. If that misses and **Remote Screenshots** is on, Elorian points at it on a screenshot, using the target as it looked in the video.

## Privacy and permissions

Gemini receives microphone audio and, when enabled, screenshots. JEV receives your typed task, locally detected labels/locations, and recent action history; screenshots stay local. Both modes use the shared local grounding and action engine.

Learn from a video sends the tutorial video you choose (and its captions) to Elorian, and deletes the upload when the tour is built. During a tour, a screenshot goes to Elorian only when local grounding cannot find a step and Remote Screenshots is on.

Accessibility permission is needed to inspect and control apps. macOS Screen Recording / Screen Content permission enables screenshots and local screen detection; it does **not** mean TipTour records videos. Microphone access is only needed for Gemini voice.

## Build

Requires macOS 14.2+ and a current Xcode with Swift support. Open `tiptour-macos.xcodeproj`, select the TipTour scheme, set your signing team, and build/run in Xcode. Package dependencies resolve through Xcode.

Use Xcode for app builds: terminal `xcodebuild` is prohibited by this repository's workflow to preserve the installed app's macOS permissions. Run `scripts/test-jev.sh` for isolated JEV decision tests without installing or launching the app.

## Code

See [source layout](docs/source-layout.md) and [local harness contract](docs/tiptour-agent-contract.md). `main` is the integration branch for both modes; feature branches are temporary PR work.

MIT licensed. See [LICENSE](LICENSE).
