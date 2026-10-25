//
//  GeminiKeyPool.swift
//  TipTour
//
//  A pool of user-supplied Gemini API keys with server-honoring cooldowns.
//  When a key fails, the pool classifies the failure, cools the key down
//  (or parks it for the rest of the run), and hands out the next available
//  key. Cooldowns come from the server's own retry hint when one exists and
//  from bounded exponential backoff with jitter otherwise, per Google's
//  published retry guidance. The pool never invents usage quotas of its own
//  and never logs key material — only masked fingerprints.
//

import Foundation
#if canImport(Combine)
import Combine
#endif

#if canImport(Combine)
/// ObservableObject where SwiftUI exists; a plain protocol elsewhere so the
/// pool's logic stays testable without Apple frameworks.
typealias GeminiKeyPoolObservable = ObservableObject
#else
protocol GeminiKeyPoolObservable {}
#endif

/// The parts of a failed Gemini Live connect/reconnect attempt the pool
/// needs to decide what happens to that key next. Every transport field is
/// optional because the websocket path does not always expose an HTTP
/// status — classification must stay defensive.
struct GeminiConnectionFailure: Equatable {
    var httpStatus: Int?
    var closeCode: Int?
    var retryAfter: TimeInterval?
    var message: String

    init(httpStatus: Int? = nil, closeCode: Int? = nil, retryAfter: TimeInterval? = nil, message: String) {
        self.httpStatus = httpStatus
        self.closeCode = closeCode
        self.retryAfter = retryAfter
        self.message = message
    }
}

enum GeminiKeyFailureKind: Equatable {
    /// 429 / quota. Cool the key; honor the server's retry hint when given.
    case rateLimited
    /// 402. Prepay credits or a billing-account cap. Google says do not
    /// retry; projects sharing one billing account can trip this together.
    case billingOrCredits
    /// 401/403 (or websocket close 1008). The key or its project was
    /// rejected — but 403 has several causes, so the key is parked for
    /// this run and surfaced, never permanently tombstoned.
    case keyOrProjectDenied
    /// 400/404. The request itself is wrong — not the key's fault. Failing
    /// over would produce the same error on every key.
    case clientError
    /// 5xx, network drops, timeouts. Bounded retry on the same key is fine.
    case transient
    case unknown
}

/// Maps transport-level failure details to a failure kind. The HTTP status
/// is authoritative. Websocket close-code meanings (1008 = denied, 1011 =
/// quota) are community-reported for Gemini Live, not an official Google
/// table, so they are only consulted when no HTTP status is available.
enum GeminiFailureClassifier {
    static func classify(_ failure: GeminiConnectionFailure) -> GeminiKeyFailureKind {
        if let status = failure.httpStatus {
            switch status {
            case 429: return .rateLimited
            case 402: return .billingOrCredits
            case 401, 403: return .keyOrProjectDenied
            case 400, 404: return .clientError
            case 500...599: return .transient
            default: break
            }
        }
        if let code = failure.closeCode {
            switch code {
            case 1008: return .keyOrProjectDenied
            case 1011: return .rateLimited
            case 1012, 1013: return .transient
            default: break
            }
        }
        let text = failure.message.lowercased()
        if text.contains("quota") || text.contains("rate limit")
            || text.contains("resource_exhausted") || text.contains("resource exhausted") {
            return .rateLimited
        }
        if text.contains("billing") || text.contains("credit") {
            return .billingOrCredits
        }
        if text.contains("permission") || text.contains("denied") || text.contains("forbidden")
            || text.contains("api key") || text.contains("leaked") {
            return .keyOrProjectDenied
        }
        if text.contains("timeout") || text.contains("network") || text.contains("offline")
            || text.contains("connection") || text.contains("socket") || text.contains("reset") {
            return .transient
        }
        return .unknown
    }
}

enum GeminiKeyState: Equatable {
    case ready
    case coolingDown(until: Date, reason: String)
    /// Parked keys are skipped for the rest of this app run. They become
    /// eligible again on relaunch or when the user resets key states —
    /// nothing is tombstoned permanently.
    case parked(reason: String)
}

/// Lock-protected (nonisolated) so both the @MainActor session and SwiftUI
/// can use it without actor hops. All current callers run on the main
/// thread, which is also what the change publisher expects.
final class GeminiKeyPool: GeminiKeyPoolObservable {

    struct Entry: Equatable, Identifiable {
        /// Stable identity derived from the secret's hash — never the secret.
        let id: String
        /// The secret itself. Never log this; UI shows `masked` only.
        var key: String
        var state: GeminiKeyState = .ready
        var consecutiveRateLimits: Int = 0
        var consecutiveTransients: Int = 0

        var masked: String { GeminiKeyPool.masked(key) }
    }

    enum PoolError: LocalizedError, Equatable {
        case noKeys
        /// Every key is cooling down or parked — nothing can be tried
        /// right now. `retryAt` is the earliest cooldown expiry when one
        /// exists (parked keys have no automatic retry time).
        case allUnavailable(retryAt: Date?)
        /// The connect run's attempt bounds were reached while keys were
        /// still being handed out — distinct from `allUnavailable`, where
        /// every key is actually blocked.
        case attemptsExhausted(triedKeys: Int)

        var errorDescription: String? {
            switch self {
            case .noKeys:
                return "Add at least one Gemini API key in Settings → Models to use realtime voice."
            case .allUnavailable(let retryAt):
                if let retryAt {
                    let time = retryAt.formatted(date: .omitted, time: .shortened)
                    return "All Gemini keys are cooling down or rejected right now. Earliest retry: \(time). Per-key status is in Settings → Models."
                }
                return "All Gemini keys are currently unavailable. Check each key's status in Settings → Models."
            case .attemptsExhausted(let triedKeys):
                return "Could not connect with any of the \(triedKeys) Gemini key\(triedKeys == 1 ? "" : "s") tried. Per-key status is in Settings → Models — try again."
            }
        }
    }

    private(set) var entries: [Entry] = []

    /// Emitted AFTER the lock is released by every mutating method. Sending
    /// synchronously while NSLock is held can deadlock a subscriber that
    /// reads back into the pool (P3 fix — no didSet on `entries`).
    private func emitChange() {
        #if canImport(Combine)
        objectWillChange.send()
        #endif
    }

    /// Durable key-list persistence. In the app these read from / write to
    /// the Keychain; tests inject their own. The writer must return true
    /// only when the list is durably stored — a failed write leaves the
    /// pool's in-memory state (and any "Saved" UI) untouched.
    var keyListWriter: (([String]) -> Bool)?
    var keyListReader: (() -> [String])?

    /// Injectable clock for tests.
    var now: () -> Date = Date.init

    private let lock = NSLock()
    private var nextHandoutIndex = 0

    init(keys: [String]) {
        #if canImport(Security)
        keyListWriter = { KeychainStore.setGeminiAPIKeys($0) }
        keyListReader = { KeychainStore.geminiAPIKeys }
        #endif
        applyKeyList(keys)
    }

    // MARK: - Key list management

    #if canImport(Security)
    /// Shared pool backed by the app's Keychain list.
    static let shared = GeminiKeyPool(keys: KeychainStore.geminiAPIKeys)
    #endif

    /// Re-reads the stored key list (when a persistence reader is
    /// installed), preserving cooldown state for keys that are still
    /// present and dropping state for removed ones.
    func reloadKeys() {
        guard let keyListReader else { return }
        applyKeyList(keyListReader())
    }

    private func applyKeyList(_ keys: [String]) {
        var seen = Set<String>()
        let cleaned = keys
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .filter { seen.insert(Self.fingerprint($0)).inserted }
        lock.lock()
        let existing = Dictionary(uniqueKeysWithValues: entries.map { ($0.id, $0) })
        entries = cleaned.map { key in
            let id = Self.fingerprint(key)
            if var kept = existing[id] {
                kept.key = key
                return kept
            }
            return Entry(id: id, key: key)
        }
        nextHandoutIndex = entries.isEmpty ? 0 : nextHandoutIndex % entries.count
        lock.unlock()
        emitChange()
    }

    /// Adds a key to the durable list first, then the pool. Returns false
    /// when the durable write fails — in that case nothing in memory or
    /// the UI changes, so nobody is told "Saved" for a key that didn't
    /// persist.
    @discardableResult
    func addKey(_ key: String) -> Bool {
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        var keys = currentKeys()
        guard !keys.contains(trimmed) else { return true }
        keys.append(trimmed)
        if let keyListWriter, !keyListWriter(keys) { return false }
        applyKeyList(keys)
        return true
    }

    /// Removes a key from the durable list first, then the pool. Returns
    /// false when the durable write fails — the entry stays in place so
    /// the UI never claims a deletion that didn't happen.
    @discardableResult
    func removeKey(id: String) -> Bool {
        let keys = currentKeys().filter { Self.fingerprint($0) != id }
        if let keyListWriter, !keyListWriter(keys) { return false }
        applyKeyList(keys)
        return true
    }

    private func currentKeys() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return entries.map(\.key)
    }

    var hasKeys: Bool {
        lock.lock()
        defer { lock.unlock() }
        return !entries.isEmpty
    }

    // MARK: - Acquisition

    /// The next key allowed to attempt a connection right now.
    /// - Parameters:
    ///   - preferredID: the key the caller was already talking to.
    ///     Returned while still ready so a transient blip retries the same
    ///     key before the pool fails over. When it is not ready, the
    ///     handout continues at the key AFTER it so failover moves on.
    ///   - excludedIDs: keys already tried in the current failover round.
    ///     They are skipped for both preference and scanning, so one
    ///     key's repeated failures can never starve keys that were never
    ///     tried.
    func acquireKey(preferring preferredID: String? = nil, excluding excludedIDs: Set<String> = []) throws -> Entry {
        lock.lock()
        defer { lock.unlock() }
        guard !entries.isEmpty else { throw PoolError.noKeys }
        refreshCooldownsLocked()

        if let preferredID,
           !excludedIDs.contains(preferredID),
           let entry = entries.first(where: { $0.id == preferredID }),
           isUsable(entry) {
            return entry
        }

        let startIndex: Int
        if let preferredID, let idx = entries.firstIndex(where: { $0.id == preferredID }) {
            startIndex = entries.index(after: idx) % entries.count
        } else {
            startIndex = nextHandoutIndex % entries.count
        }
        for offset in 0..<entries.count {
            let idx = (startIndex + offset) % entries.count
            if !excludedIDs.contains(entries[idx].id), isUsable(entries[idx]) {
                nextHandoutIndex = entries.index(after: idx) % entries.count
                return entries[idx]
            }
        }
        throw PoolError.allUnavailable(retryAt: nextRetryDateLocked())
    }

    /// True when at least one key can attempt a connection right now,
    /// ignoring any caller-side exclusions. Used to tell "every key is
    /// blocked" apart from "this round already used the ready keys".
    var hasUsableKey: Bool {
        lock.lock()
        defer { lock.unlock() }
        refreshCooldownsLocked()
        return entries.contains(where: isUsable)
    }

    private func isUsable(_ entry: Entry) -> Bool {
        switch entry.state {
        case .ready: return true
        case .coolingDown(let until, _): return until <= now()
        case .parked: return false
        }
    }

    private func refreshCooldownsLocked() {
        let current = now()
        for idx in entries.indices {
            if case .coolingDown(let until, _) = entries[idx].state, until <= current {
                // State recovers, but the consecutive-failure counters do
                // NOT reset here: a key that keeps failing after each
                // cooldown (e.g. an exhausted per-day quota) escalates its
                // backoff toward the cap instead of spinning every 20s.
                // Only an explicit resetStates() or a success clears them.
                entries[idx].state = .ready
            }
        }
    }

    /// Earliest moment any cooling-down key becomes eligible again.
    /// Parked keys have no automatic retry time and are not included.
    var nextRetryDate: Date? {
        lock.lock()
        defer { lock.unlock() }
        return nextRetryDateLocked()
    }

    private func nextRetryDateLocked() -> Date? {
        entries.compactMap { entry -> Date? in
            if case .coolingDown(let until, _) = entry.state { return until }
            return nil
        }.min()
    }

    // MARK: - Outcome reporting

    func reportSuccess(_ id: String) {
        lock.lock()
        guard let idx = entries.firstIndex(where: { $0.id == id }) else {
            lock.unlock()
            return
        }
        entries[idx].state = .ready
        entries[idx].consecutiveRateLimits = 0
        entries[idx].consecutiveTransients = 0
        lock.unlock()
        emitChange()
    }

    func reportFailure(_ id: String, failure: GeminiConnectionFailure) {
        let kind = GeminiFailureClassifier.classify(failure)
        var logLine: String?
        var changed = false
        lock.lock()
        if let idx = entries.firstIndex(where: { $0.id == id }) {
            let masked = Self.masked(entries[idx].key)
            switch kind {
            case .rateLimited:
                entries[idx].consecutiveRateLimits += 1
                let n = entries[idx].consecutiveRateLimits
                // Server hint wins. Otherwise bounded backoff with jitter; the
                // 1-hour cap keeps an exhausted per-day quota from spinning
                // every few seconds (repeated failures escalate the backoff)
                // without the pool inventing a quota of its own.
                let backoff = min(20 * pow(2.0, Double(n - 1)), 3600)
                let cooldown = failure.retryAfter ?? Self.jittered(backoff)
                let until = now().addingTimeInterval(cooldown)
                entries[idx].state = .coolingDown(until: until, reason: "Rate limited by Google")
                changed = true
                logLine = "[GeminiKeyPool] \(masked) rate limited — cooling down \(Int(cooldown))s"
            case .billingOrCredits:
                entries[idx].state = .parked(reason: "Billing or prepaid credits exhausted (402). Keys whose projects share one Google billing account can hit this together.")
                changed = true
                logLine = "[GeminiKeyPool] \(masked) parked — billing/credits (402)"
            case .keyOrProjectDenied:
                entries[idx].state = .parked(reason: "Rejected by Google — check the key and its project")
                changed = true
                logLine = "[GeminiKeyPool] \(masked) parked — key/project denied"
            case .clientError:
                // Not the key's fault; leave its state untouched. The session
                // surfaces this instead of burning through the pool.
                logLine = "[GeminiKeyPool] \(masked) request error (not key-related): \(failure.message)"
            case .transient, .unknown:
                entries[idx].consecutiveTransients += 1
                changed = true
                let n = entries[idx].consecutiveTransients
                if n >= 3 {
                    let cooldown = Self.jittered(min(5 * pow(2.0, Double(n - 3)), 60))
                    entries[idx].state = .coolingDown(until: now().addingTimeInterval(cooldown), reason: "Connection trouble")
                    logLine = "[GeminiKeyPool] \(masked) transient failure x\(n) — cooling down \(Int(cooldown))s"
                }
            }
        }
        lock.unlock()
        if let logLine { print(logLine) }
        if changed { emitChange() }
    }

    /// Makes every key eligible again (user action in Settings). Parked
    /// keys are re-tried on the next connection attempt.
    func resetStates() {
        lock.lock()
        for idx in entries.indices {
            entries[idx].state = .ready
            entries[idx].consecutiveRateLimits = 0
            entries[idx].consecutiveTransients = 0
        }
        lock.unlock()
        emitChange()
    }

    // MARK: - Helpers

    static func masked(_ key: String) -> String {
        "••••" + String(key.suffix(4))
    }

    /// Scrubs key material out of a message before it is logged, stored,
    /// or shown in the UI. Transport errors can embed the websocket URL —
    /// which carries the API key as `?key=` — so anything derived from a
    /// thrown error passes through here first. Masks every supplied
    /// secret plus any `key=` query value found in the text.
    static func sanitized(_ message: String, secrets: [String] = []) -> String {
        var result = message
        for secret in secrets where secret.count >= 8 {
            result = result.replacingOccurrences(of: secret, with: masked(secret))
        }
        // Advance past each replacement — the mask itself contains
        // "key=" and must not match again (that would loop forever).
        var searchStart = result.startIndex
        while let range = result.range(of: #"key=[^&\s"']+"#, options: .regularExpression,
                                       range: searchStart..<result.endIndex) {
            let replacement = "key=••••"
            result.replaceSubrange(range, with: replacement)
            searchStart = result.index(range.lowerBound, offsetBy: replacement.count)
        }
        return result
    }

    /// `message` scrubbed of every key currently in the pool.
    func sanitized(_ message: String) -> String {
        Self.sanitized(message, secrets: currentKeys())
    }

    /// True for deliberate teardown: Task cancellation and URLSession's
    /// cancelled error (NSURLErrorCancelled, -999). Compared by domain
    /// string so it works without FoundationNetworking on Linux. A
    /// cancelled attempt must never cost a key a failure strike.
    static func isCancellation(_ error: Error) -> Bool {
        if error is CancellationError { return true }
        let nsError = error as NSError
        return nsError.domain == "NSURLErrorDomain" && nsError.code == -999
    }

    static func jittered(_ base: TimeInterval) -> TimeInterval {
        base * Double.random(in: 0.8...1.2)
    }

    /// Stable, non-secret identity for a key (FNV-1a 64-bit). Used to match
    /// entries across key-list reloads and to tag log lines — never the
    /// secret itself.
    static func fingerprint(_ key: String) -> String {
        var hash: UInt64 = 0xcbf29ce484222325
        for byte in key.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x100000001b3
        }
        return String(format: "%016x", hash)
    }
}

// MARK: - Bounded failover orchestration

/// Bounds and pacing for one failover run. Pure value + closures so the
/// whole policy is testable without any transport.
struct GeminiFailoverPolicy {
    /// How many full passes over the ready keys are allowed. Each pass
    /// tries every distinct ready key at most once, so no key is starved
    /// by another key's retries and no user key is silently dropped.
    var maxRounds: Int
    /// Absolute cap on connect attempts across all rounds.
    var maxAttempts: Int
    /// Wait after a failed attempt (attempt index is 1-based in the run).
    var wait: (_ attempt: Int, _ kind: GeminiKeyFailureKind, _ failure: GeminiConnectionFailure) -> TimeInterval

    /// First connect from a cold session: every ready key gets a fair
    /// attempt (one per round, two rounds) and waits stay jittered and
    /// capped so `start()` always terminates. A second round only helps
    /// keys whose cooldown expired during the run.
    static func initialConnect(keyCount: Int) -> GeminiFailoverPolicy {
        GeminiFailoverPolicy(maxRounds: 2, maxAttempts: max(4, keyCount * 2)) { attempt, kind, failure in
            let base: TimeInterval = (kind == .transient || kind == .unknown) ? 0.5 : 2.0
            var wait = min(base * pow(2.0, Double(max(attempt, 1) - 1)), 15.0) * Double.random(in: 0.8...1.2)
            if let hint = failure.retryAfter, hint.isFinite, hint > 0 { wait = max(wait, min(hint, 60.0)) }
            return wait
        }
    }

    /// Transparent reconnect of a live session. The bound derives from
    /// the pool size — never a flat global cap — so round 1 always covers
    /// every ready key however many the user saved (a fixed 5-attempt cap
    /// would starve keys 6+). Round 2 only revisits keys whose cooldown
    /// expired during the run; when every key is blocked the runner stops
    /// early with `allUnavailable` and its earliest retry time.
    static func reconnect(keyCount: Int) -> GeminiFailoverPolicy {
        GeminiFailoverPolicy(maxRounds: 2, maxAttempts: max(5, keyCount * 2)) { attempt, _, failure in
            // Same bounded shape as the initial connect: exponential growth
            // capped at 15 s with jitter (18 s worst case). An uncapped
            // doubling turned a large pool's late attempts into multi-hour
            // sleeps whose nanosecond conversion then trapped in
            // Double -> UInt64; the cap keeps every wait short and finite.
            var wait = min(0.5 * pow(2.0, Double(max(attempt, 1) - 1)), 15.0) * Double.random(in: 0.8...1.2)
            // A server retry hint is honored separately on top of the base
            // backoff, under its own 60 s cap, exactly as in initialConnect.
            if let hint = failure.retryAfter, hint.isFinite, hint > 0 {
                wait = max(wait, min(hint, 60.0))
            }
            return wait
        }
    }
}

/// The testable orchestration seam shared by the initial connect and the
/// reconnect loop. Transport-agnostic: callers inject the actual connect
/// (`attempt`), the failure mapping (`failureFrom`), liveness
/// (`isCancelled`), and sleeping. All pool rules live here exactly once:
///
/// - distinct-key coverage: each round tries every ready key at most
///   once (a flat attempt cap plus same-key preference previously let
///   one key's 3 transient strikes consume the whole budget and skip
///   keys that were never tried),
/// - cancellation (`isCancelled`, `CancellationError`,
///   NSURLErrorCancelled) rethrows immediately and never costs a key a
///   failure strike — user stops and mode switches are not key failures,
/// - `.clientError` rethrows at once: the request shape is wrong, so
///   failing over would hit the same error on every key,
/// - terminal errors are truthful: `PoolError.allUnavailable` only when
///   every key is actually cooling or parked (earliest retry attached
///   when one exists), `PoolError.attemptsExhausted` when the run's
///   bounds were reached first.
enum GeminiKeyFailover {

    /// Seconds -> nanoseconds for `Task.sleep` that can never trap:
    /// non-finite or negative waits become 0, and anything above a generous
    /// ceiling is clamped. The policies cap real waits at 18 s (60 s with a
    /// server hint); this conversion is the last line of defense so a wait
    /// bug can never crash a live session with a Double -> UInt64 overflow.
    static func sleepNanoseconds(_ seconds: TimeInterval) -> UInt64 {
        guard seconds.isFinite, seconds > 0 else { return 0 }
        return UInt64(min(seconds, 300) * 1_000_000_000)
    }

    @discardableResult
    static func run(
        pool: GeminiKeyPool,
        policy: GeminiFailoverPolicy,
        isCancelled: () -> Bool,
        sleep: (TimeInterval) async throws -> Void,
        failureFrom: (Error) -> GeminiConnectionFailure,
        attempt: (GeminiKeyPool.Entry) async throws -> Void
    ) async throws -> GeminiKeyPool.Entry {
        var triedKeys = Set<String>()
        var triedThisRound = Set<String>()
        var lastTriedID: String?
        var attempts = 0
        var round = 1

        while true {
            if isCancelled() || Task.isCancelled { throw CancellationError() }
            guard attempts < policy.maxAttempts else {
                throw GeminiKeyPool.PoolError.attemptsExhausted(triedKeys: triedKeys.count)
            }

            let entry: GeminiKeyPool.Entry
            do {
                entry = try pool.acquireKey(preferring: lastTriedID, excluding: triedThisRound)
            } catch {
                // acquireKey throws allUnavailable both when every key is
                // blocked AND when only already-tried-this-round keys are
                // left. Only the first is truly terminal.
                guard pool.hasUsableKey else { throw error }
                round += 1
                guard round <= policy.maxRounds else {
                    throw GeminiKeyPool.PoolError.attemptsExhausted(triedKeys: triedKeys.count)
                }
                triedThisRound.removeAll()
                continue
            }

            attempts += 1
            triedThisRound.insert(entry.id)
            triedKeys.insert(entry.id)
            lastTriedID = entry.id

            do {
                try await attempt(entry)
                pool.reportSuccess(entry.id)
                return entry
            } catch {
                // A cancelled or stale caller is not a key failure: no
                // strike, no cooldown, immediate rethrow.
                if isCancelled() || Task.isCancelled || GeminiKeyPool.isCancellation(error) {
                    throw CancellationError()
                }
                let failure = failureFrom(error)
                let kind = GeminiFailureClassifier.classify(failure)
                pool.reportFailure(entry.id, failure: failure)
                if kind == .clientError { throw error }
                if attempts < policy.maxAttempts {
                    let wait = policy.wait(attempts, kind, failure)
                    if wait > 0 { try await sleep(wait) }
                }
            }
        }
    }
}
