# Gemini key pool (fork addition)

This branch adds a pool of user-supplied Gemini API keys to the Gemini realtime voice mode. When a key fails, TipTour classifies the failure, cools the key down (or parks it for the rest of the run), and tries the next available key. When no key is currently usable, the error names the earliest retry time.

You supply the keys — one per Google project you create yourself. TipTour never creates projects, never reads keys from other apps, and never sends keys anywhere except to Google over the Gemini Live websocket.

## Where things live

- `TipTour/Voice/GeminiKeyPool.swift` — the pool: key list, cooldown state, failure classification, handout order. Pure Foundation/Combine, no AppKit.
- `TipTour/Utilities/KeychainStore.swift` — `geminiAPIKeys` list storage (JSON in macOS Keychain). An existing single `geminiAPIKey` migrates into the list on first read.
- `TipTour/Voice/GeminiLiveClient.swift` — captures the handshake's HTTP status, `Retry-After` header, and websocket close code into `GeminiLiveConnectError` so failures can be classified.
- `TipTour/Voice/GeminiLiveSession.swift` — `connectWithKeyPool()` and the reconnect loop both run through `GeminiKeyFailover`, the pool's bounded failover runner: distinct-key coverage per round, no failure strikes for cancelled or stale attempts, truthful terminal errors.
- `TipTour/App/CompanionManager.swift` + `TipTour/UI/CompanionPanelView.swift` — connection failures surface in the menu bar panel: all keys blocked (with the earliest retry time), attempt budget exhausted, or a scrubbed transport error. Onboarding's key step uses the same pool card as Settings.
- `TipTour/UI/ProviderSetupView.swift` — `GeminiKeyPoolCard` in Settings → Models: add/remove keys, per-key status (masked, last 4 characters only), and a "Reset key states" button.

## Failure policy

| Signal | Classification | What the pool does |
| --- | --- | --- |
| HTTP 429, or close 1011, or "quota"/"RESOURCE_EXHAUSTED" text | Rate limited | Cool down: the server's `Retry-After` when the transport exposes it (see note below), else exponential backoff with jitter (20 s base, doubling per repeat, 1 hour cap). |
| HTTP 402 | Billing / credits | Park for the rest of the run. Note in the UI: projects sharing one Google billing account share its caps, so other keys may be affected too. |
| HTTP 401/403, or close 1008 | Key or project rejected | Park for the rest of the run. 403 has several causes (disabled key, leaked key, project restrictions), so the key is never permanently tombstoned — it becomes eligible again on relaunch or "Reset key states". |
| HTTP 400/404 | Request error | Not the key's fault. The error is surfaced immediately instead of burning through the pool. |
| 5xx, network drops, timeouts | Transient | Same key stays eligible; bounded retries with jittered backoff. After 3 consecutive transient failures the key cools down briefly (5 s doubling to 60 s cap). |

Close-code meanings (1008/1011) are community-reported for Gemini Live, not an official Google table, so they are only used when the handshake's HTTP status is unavailable. Whether macOS URLSessionWebSocketTask exposes the failed upgrade's HTTP response (status, `Retry-After`) is UNVERIFIED against Google's servers — when it doesn't, classification falls back to close code and message text, and cooldowns come from the bounded backoff. Nothing in the app promises a server retry hint was available.

Cooldowns are congestion backoff derived from real server failures — the pool deliberately has no daily caps, request counters, or other self-invented quotas. Rate limits are per Google project; whether projects share a billing-account cap is not detectable from a key, so each key's state is tracked independently and nothing is claimed about quota multiplication.

## Behavior notes

- Switching keys means a new websocket connection. Gemini's server-side session context does not carry over (TipTour does not use session resumption), the same as any reconnect today.
- Connect and reconnect both use the pool's failover runner: each round tries every distinct ready key at most once (one key's repeated failures can never starve keys that were never tried), with at most two rounds and an attempt bound derived from the pool size — never a flat global cap that drops user keys. Waits between attempts are jittered and capped (15 s base, 60 s when the server supplies a retry hint), so both operations always terminate and a wait can never overflow its nanosecond conversion. When the run stops early the terminal error says which of two truths applies: every key is cooling down or parked (`allUnavailable`, with the earliest retry time when one exists), or the bounded attempt budget ran out while keys were still being handed out (`attemptsExhausted`).
- Cancellation is never a key failure: a user stop, mode switch, or task cancellation mid-attempt adds no failure strike and no cooldown.
- Cooldown and parked state lives in memory for the current app run only. Relaunching TipTour (or "Reset key states" in Settings) makes every key eligible again; a server's `Retry-After` is not persisted across relaunch — if the key is still rate limited, the next failure re-reads the hint.
- Keys are never logged or shown. Transport errors can embed the request URL (which carries the raw key), so every error message is scrubbed at the client boundary and again before logs or UI. Logs and the UI show only the masked last-4 form.
- Adding or removing a key writes to the Keychain first; the pool and the UI only change when that write succeeds, and the UI says so when it fails. The legacy single-key slot migrates into the list on first read and is only deleted after the list write reads back intact.

## Testing

`scripts/test-gemini-key-pool.sh` runs the pure pool/classifier/failover tests (`TipTourTests/GeminiKeyPoolTests.swift`, 31 tests) in a scratch SPM package, the same pattern as `scripts/test-jev.sh` — no Xcode, no network, no real keys. The failover runner tests use injected connect/sleep/failure closures, including 9+-key coverage, cancellation, and persistence-failure honesty.

Not covered automatically: the real websocket handshake, Google's actual error payloads, and the Settings UI. Those need a Mac run with real keys.
