# Gemini key pool (fork addition)

This branch adds a pool of user-supplied Gemini API keys to the Gemini realtime voice mode. When a key fails, TipTour classifies the failure, cools the key down (or parks it for the rest of the run), and tries the next available key. When no key is currently usable, the error names the earliest retry time.

You supply the keys — one per Google project you create yourself. TipTour never creates projects, never reads keys from other apps, and never sends keys anywhere except to Google over the Gemini Live websocket.

## Where things live

- `TipTour/Voice/GeminiKeyPool.swift` — the pool: key list, cooldown state, failure classification, handout order. Pure Foundation/Combine, no AppKit.
- `TipTour/Utilities/KeychainStore.swift` — `geminiAPIKeys` list storage (JSON in macOS Keychain). An existing single `geminiAPIKey` migrates into the list on first read.
- `TipTour/Voice/GeminiLiveClient.swift` — captures the handshake's HTTP status, `Retry-After` header, and websocket close code into `GeminiLiveConnectError` so failures can be classified.
- `TipTour/Voice/GeminiLiveSession.swift` — `connectWithKeyPool()` and the reconnect loop acquire keys from the pool, report success/failure, and stay strictly bounded.
- `TipTour/UI/ProviderSetupView.swift` — `GeminiKeyPoolCard` in Settings → Models: add/remove keys, per-key status (masked, last 4 characters only), and a "Reset key states" button.

## Failure policy

| Signal | Classification | What the pool does |
| --- | --- | --- |
| HTTP 429, or close 1011, or "quota"/"RESOURCE_EXHAUSTED" text | Rate limited | Cool down: the server's `Retry-After` when present, else exponential backoff with jitter (20 s base, doubling per repeat, 1 hour cap). |
| HTTP 402 | Billing / credits | Park for the rest of the run. Note in the UI: projects sharing one Google billing account share its caps, so other keys may be affected too. |
| HTTP 401/403, or close 1008 | Key or project rejected | Park for the rest of the run. 403 has several causes (disabled key, leaked key, project restrictions), so the key is never permanently tombstoned — it becomes eligible again on relaunch or "Reset key states". |
| HTTP 400/404 | Request error | Not the key's fault. The error is surfaced immediately instead of burning through the pool. |
| 5xx, network drops, timeouts | Transient | Same key stays eligible; bounded retries with jittered backoff. After 3 consecutive transient failures the key cools down briefly (5 s doubling to 60 s cap). |

Close-code meanings (1008/1011) are community-reported for Gemini Live, not an official Google table, so they are only used when the handshake's HTTP status is unavailable.

Cooldowns are congestion backoff derived from real server failures — the pool deliberately has no daily caps, request counters, or other self-invented quotas. Rate limits are per Google project; whether projects share a billing-account cap is not detectable from a key, so each key's state is tracked independently and nothing is claimed about quota multiplication.

## Behavior notes

- Switching keys means a new websocket connection. Gemini's server-side session context does not carry over (TipTour does not use session resumption), the same as any reconnect today.
- Connect attempts are bounded: at most `min(max(3, keys × 2), 8)` attempts per start, with jittered, capped waits between them, and the reconnect loop keeps its 5-attempt bound. There is no busy loop.
- Keys are never logged. Logs and the UI show only the masked last-4 form.

## Testing

`scripts/test-gemini-key-pool.sh` runs the pure pool/classifier tests (`TipTourTests/GeminiKeyPoolTests.swift`) in a scratch SPM package, the same pattern as `scripts/test-jev.sh` — no Xcode, no network, no real keys.

Not covered automatically: the real websocket handshake, Google's actual error payloads, and the Settings UI. Those need a Mac run with real keys.
