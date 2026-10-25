# Run this branch locally on your Mac

## Get the code

```bash
git clone https://github.com/ishitzzz/tiptour.git
cd tiptour
git checkout feature/gemini-key-pool
```

Or, in an existing clone: `git fetch origin && git checkout feature/gemini-key-pool`.

## Build

1. Requires macOS 14.2+ and a current Xcode.
2. Open `tiptour-macos.xcodeproj`, select the **TipTour** scheme, set your signing team, and build/run in Xcode. Package dependencies resolve through Xcode.
3. Use Xcode for app builds — this repository's workflow does not use terminal `xcodebuild`, to preserve the installed app's macOS permissions.

## Permissions the app will ask for

- **Accessibility** — inspect and control apps (both modes).
- **Screen Recording / Screen Content** — screenshots and local screen detection.
- **Microphone** — Gemini voice mode only.

## Add your Gemini keys

Settings → Models → Gemini keys. Paste each key and choose **Add key** — one per Google project you created. The list shows each key masked (last 4 characters) with its live status: Ready, cooling down (with the retry time), or parked (with the reason). **Reset key states** makes every key eligible again.

An existing single Gemini key from an older install migrates into the pool automatically on first read.

## What to expect from the pool

- A rate-limited key cools down (server's own retry time when the transport exposes it) and the next available key is tried — each connection attempt covers every ready key, however many you saved.
- A rejected key (bad/disabled key, project restriction) is parked for the rest of the app run and says so — it is never deleted. Relaunching the app makes it eligible again.
- A billing/credits failure (402) parks the key and warns that projects on the same Google billing account share that cap.
- If no key is currently usable, the menu bar panel says so with the earliest retry time; if a bounded connect run gives up first, it says that instead. Stopping voice (or switching modes) mid-connect never counts as a key failure.
- Switching keys opens a fresh Gemini session; the conversation does not carry across keys (same as any reconnect today).
- The onboarding key step for Gemini is the same key-pool card as Settings → Models.

## Tests (no Xcode, no network, no real keys)

```bash
bash scripts/test-gemini-key-pool.sh   # key pool + failure classification
bash scripts/test-jev.sh               # existing JEV decision tests
```

Both build a scratch SPM package and run in seconds. The key-pool script also runs with a plain Linux Swift toolchain.

## Not yet verified (needs your Mac run)

- Real websocket handshake classification against Google's actual Live error responses. In particular: whether macOS exposes the failed upgrade's HTTP status and `Retry-After` to URLSessionWebSocketTask is unverified — if it doesn't, classification falls back to close code and message text and cooldowns use the bounded backoff.
- The Settings key-list card's and menu bar panel error banner's layout and interactions.
- End-to-end failover with real keys from your projects.
