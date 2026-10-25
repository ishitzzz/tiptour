# Run the combined branch locally on your Mac

This branch combines three reviewed pieces on top of `main`: the Gemini
multi-key pool, the TypeSafe-Jev-via-OpenRouter connection option, and the
ask-harness clipboard copy fixes. The notes below cover all three.

## Updating an existing local build without losing your changes

If this repo is already on your Mac with your own edits, do not hard-reset,
stash-drop, or `git add -A` / `git add -u`. Tracked files can hold keys too,
so check contents, not only filenames. Push NOTHING: no local backup,
integration or combined branch is ever pushed.

1. Look first. Note your current branch (or detached HEAD) and what changed.
   Set the timestamp ONCE; later steps reuse it:

```bash
cd tiptour
TS=$(date +%Y%m%d-%H%M%S)
git status --short --branch
git diff --cached --name-only
```

If `git diff --cached --name-only` lists anything, something is already
staged. STOP and report those names only - do not commit, reset or unstage
them, and do not continue.

2. Fetch, then run the private backup helper. It copies modified/untracked
files plus small secret-named ignored files into a chmod-700 folder outside
git (recording deletions and symlinks without copying them), verifies every
copied file's hash, and scans contents privately, reporting names only.
If python3 is missing or the helper exits nonzero, STOP - there is no
fallback path.

```bash
git fetch origin
command -v python3
HELPER=$(mktemp /tmp/tiptour-local-backup.XXXXXX)   # unique, private (0600), never an existing file
git show origin/fix/combined-docs-safe-update:scripts/local-backup.py > "$HELPER"
python3 "$HELPER"
```

Keep the backup folder private: never zip, upload, push or paste it.

3. Optional local safety branch. Stage only files you have reviewed
(`git diff <file>`) and that contain no keys, by name. Skip any file with
`.env*`, `*.pem`, `*.key`, `*secret*`, `*credential*`, `*apikey*`, or
key-looking contents; those stay in the private backup only. If a tracked
file already holds a key, do not commit it: keep the private copy and ask
for help. Skip this step entirely when there is nothing safe to commit.

```bash
git branch "backup-$TS"                       # marks the current commit, no checkout
git switch -c "local-integration-backup-$TS"  # unique branch from where you are (detached HEAD works)
git add path/to/reviewed-file1 path/to/reviewed-file2
git diff --cached --name-only                 # must list EXACTLY those files; anything else: STOP, report names only
git commit -m "Local state before combined branch"
```

4. Bring in the combined branch without replacing your work:

```bash
git switch -c "local-integration-combined-$TS"   # unique branch from your current state
git merge origin/fix/combined-docs-safe-update
```

If the merge conflicts, STOP and report the conflicted file names only.
Do not use `-X theirs/ours`, do not drop the key pool, and do not resolve
by hand - we will work through the conflicts together. The combined branch
reorganised files into subfolders, so conflicts with flat local paths are
possible. Your old branch and the private backup keep your state.

## Get the code

```bash
git clone https://github.com/ishitzzz/tiptour.git
cd tiptour
git checkout fix/combined-docs-safe-update
```

Or, in an existing clone: `git fetch origin && git checkout fix/combined-docs-safe-update`.

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

## Verification status (what has and has not been checked)

- `scripts/test-ask.sh` runs only the pure ask-harness logic (coordinate
  mapping, session generations, clipboard ownership with a fake pasteboard,
  copy-mode flavors, the copy-request gate, copy-outcome reset rules,
  composer role policy, chord provenance, markings and sizing decisions)
  in a temporary Swift package, with Swift language mode 5 and a macOS 14
  platform setting. During review on 2026-10-25, the same package the
  script builds (same Package.swift, sources and test rewrite) passed
  41/41 tests on the official Swift 6.1.2 Linux toolchain via a direct
  XCTest run; the script itself was not executed end-to-end there. The
  key-pool suite builds on Linux but was not re-run in that pass (its
  author previously recorded 19/19 passing on Linux Swift 6.1.2). These
  tests do not cover the native UI, paste, or hotkey code.
- Not verified on a Mac or against live services: the native UI, the paste
  attempts, and the app as a whole. No Xcode build or Swift compile of the
  app has been run for this branch. This applies to all three pieces, not
  only the Gemini key pool.
- OpenRouter/JEV: the real endpoint response, the `usage.cost` field, which
  provider serves a request, and the runtime behaviour are unverified.
  Cost figures in the app are never estimated locally: they are copied only
  from values the OpenRouter response itself reports, and even then they are
  a partial subtotal (successful, grounding-valid, cost-reporting calls
  only - cancelled, failed or unreported calls are missing), not a spend
  total, ledger or cap. They are unverified against a live endpoint. The
  JEV package needs Swift 6.1.
- Microphone: Gemini Live and the ask harness's speech recognition may both
  want the mic at once. Concurrent use is untested. Do not assume it is
  safe; test it and limit it to one at a time until it is checked.
- If the merge step above conflicts with your local changes, those are
  yours to resolve by hand. Nothing here auto-resolves them.
