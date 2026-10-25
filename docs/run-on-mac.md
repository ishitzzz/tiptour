# Run the combined branch locally on your Mac

This branch (`feature/combined-jev-or-keypool-clipboard`) combines three
reviewed pieces on top of `main`: the Gemini multi-key pool, the
TypeSafe-Jev-via-OpenRouter connection option, and the ask-harness
clipboard copy fixes. The notes below cover all three.

## Updating an existing local build without losing your changes

If you already have this repo checked out on your Mac with your own
edits (tracked or untracked), keep them safe first - do not hard-reset
or stash-drop them:

```bash
cd tiptour
git checkout -b backup-before-combined   # new local safety branch
git add -A                               # stage tracked AND untracked changes
git commit -m "Local state before combined branch"
git checkout main                        # or whatever you had checked out
git fetch origin
git checkout feature/combined-jev-or-keypool-clipboard
```

Your old state stays recoverable on `backup-before-combined`. If you want
your local edits on top of the combined branch later, merge or cherry-pick
from that backup branch.


## Get the code

```bash
git clone https://github.com/ishitzzz/tiptour.git
cd tiptour
git checkout feature/combined-jev-or-keypool-clipboard
```

Or, in an existing clone: `git fetch origin && git checkout feature/combined-jev-or-keypool-clipboard`.

## Build

1. Requires macOS 14.2+ and a current Xcode.
2. Open `tiptour-macos.xcodeproj`, select the **TipTour** scheme, set your signing team, and build/run in Xcode. Package dependencies resolve through Xcode.
3. Use Xcode for app builds — this repository's workflow does not use terminal `xcodebuild`, to preserve the installed app's macOS permissions.

## Permissions the app will ask for

- **Accessibility** — inspect and control apps (both modes); also the ask-harness hotkey and optional paste.
- **Screen Recording / Screen Content** — screenshots and local screen detection; also the ask-harness capture.
- **Microphone** — Gemini voice mode, and the ask harness's spoken question.
- **Speech Recognition** — ask harness only; transcription is on-device.

## Ask harness (scribble + voice, copy to clipboard)

Hold **Ctrl+Option+Shift**, say your question, release. The preview opens
with the captured screen and your transcribed question; use **Copy both**,
**Copy image** or **Copy text**, then paste where you want. Direct
insertion into an app is optional and off by default (Settings → Advanced
→ Ask Direct Insert App). Details and honest limits:
[docs/ask-harness.md](docs/ask-harness.md). Not yet run on a Mac.

## JEV through OpenRouter (optional)

Settings → Models → JEV connection: TypeSafe direct (default, unchanged)
or OpenRouter. Each connection has its own Keychain key. The OpenRouter
connection bills input tokens to your OpenRouter balance (output free);
no automatic fallback or top-up. Per-call latency and input tokens show
in the JEV step view; a run's partial reported cost subtotal and last
reported provider go to the pipeline log (not a spend ledger or cap).

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
