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
        case allUnavailable(retryAt: Date?)

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
            }
        }
    }

    private(set) var entries: [Entry] = [] {
        didSet { emitChange() }
    }

    private func emitChange() {
        #if canImport(Combine)
        objectWillChange.send()
        #endif
    }

    /// Injectable clock for tests.
    var now: () -> Date = Date.init

    private let lock = NSLock()
    private var nextHandoutIndex = 0

    init(keys: [String]) {
        applyKeyList(keys)
    }

    // MARK: - Key list management

    #if canImport(Security)
    /// Shared pool backed by the app's Keychain list.
    static let shared = GeminiKeyPool(keys: KeychainStore.geminiAPIKeys)

    /// Re-reads the stored key list, preserving cooldown state for keys
    /// that are still present and dropping state for removed ones.
    func reloadKeys() {
        applyKeyList(KeychainStore.geminiAPIKeys)
    }
    #endif

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
    }

    #if canImport(Security)
    func addKey(_ key: String) {
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        var keys = currentKeys()
        guard !keys.contains(trimmed) else { return }
        keys.append(trimmed)
        KeychainStore.geminiAPIKeys = keys
        applyKeyList(keys)
    }

    func removeKey(id: String) {
        let keys = currentKeys().filter { Self.fingerprint($0) != id }
        KeychainStore.geminiAPIKeys = keys
        applyKeyList(keys)
    }
    #endif

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
    /// - Parameter preferredID: the key the caller was already talking to.
    ///   Returned while still ready so a transient blip retries the same
    ///   key before the pool fails over. When it is not ready, the handout
    ///   continues at the key AFTER it so failover actually moves on.
    func acquireKey(preferring preferredID: String? = nil) throws -> Entry {
        lock.lock()
        defer { lock.unlock() }
        guard !entries.isEmpty else { throw PoolError.noKeys }
        refreshCooldownsLocked()

        if let preferredID,
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
            if isUsable(entries[idx]) {
                nextHandoutIndex = entries.index(after: idx) % entries.count
                return entries[idx]
            }
        }
        throw PoolError.allUnavailable(retryAt: nextRetryDateLocked())
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
        defer { lock.unlock() }
        guard let idx = entries.firstIndex(where: { $0.id == id }) else { return }
        entries[idx].state = .ready
        entries[idx].consecutiveRateLimits = 0
        entries[idx].consecutiveTransients = 0
    }

    func reportFailure(_ id: String, failure: GeminiConnectionFailure) {
        let kind = GeminiFailureClassifier.classify(failure)
        lock.lock()
        defer { lock.unlock() }
        guard let idx = entries.firstIndex(where: { $0.id == id }) else { return }
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
            print("[GeminiKeyPool] \(masked) rate limited — cooling down \(Int(cooldown))s")
        case .billingOrCredits:
            entries[idx].state = .parked(reason: "Billing or prepaid credits exhausted (402). Keys whose projects share one Google billing account can hit this together.")
            print("[GeminiKeyPool] \(masked) parked — billing/credits (402)")
        case .keyOrProjectDenied:
            entries[idx].state = .parked(reason: "Rejected by Google — check the key and its project")
            print("[GeminiKeyPool] \(masked) parked — key/project denied")
        case .clientError:
            // Not the key's fault; leave its state untouched. The session
            // surfaces this instead of burning through the pool.
            print("[GeminiKeyPool] \(masked) request error (not key-related): \(failure.message)")
        case .transient, .unknown:
            entries[idx].consecutiveTransients += 1
            let n = entries[idx].consecutiveTransients
            if n >= 3 {
                let cooldown = Self.jittered(min(5 * pow(2.0, Double(n - 3)), 60))
                entries[idx].state = .coolingDown(until: now().addingTimeInterval(cooldown), reason: "Connection trouble")
                print("[GeminiKeyPool] \(masked) transient failure x\(n) — cooling down \(Int(cooldown))s")
            }
        }
    }

    /// Makes every key eligible again (user action in Settings). Parked
    /// keys are re-tried on the next connection attempt.
    func resetStates() {
        lock.lock()
        defer { lock.unlock() }
        for idx in entries.indices {
            entries[idx].state = .ready
            entries[idx].consecutiveRateLimits = 0
            entries[idx].consecutiveTransients = 0
        }
    }

    // MARK: - Helpers

    static func masked(_ key: String) -> String {
        "••••" + String(key.suffix(4))
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
