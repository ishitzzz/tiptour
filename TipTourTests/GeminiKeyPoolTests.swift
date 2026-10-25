import Foundation
import Testing
@testable import TipTour

struct GeminiKeyPoolTests {

    private func makePool(keys: [String] = ["key-alpha-1111", "key-beta-2222", "key-gamma-3333"],
                          now: Date = Date(timeIntervalSince1970: 1_000_000)) -> GeminiKeyPool {
        let pool = GeminiKeyPool(keys: keys)
        pool.now = { now }
        return pool
    }

    private func state(of id: String, in pool: GeminiKeyPool) -> GeminiKeyState? {
        pool.entries.first(where: { $0.id == id })?.state
    }

    // MARK: - Classifier

    @Test func httpStatusIsAuthoritative() {
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(httpStatus: 429, message: "")) == .rateLimited)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(httpStatus: 402, message: "")) == .billingOrCredits)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(httpStatus: 401, message: "")) == .keyOrProjectDenied)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(httpStatus: 403, message: "")) == .keyOrProjectDenied)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(httpStatus: 400, message: "")) == .clientError)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(httpStatus: 404, message: "")) == .clientError)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(httpStatus: 500, message: "")) == .transient)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(httpStatus: 503, message: "")) == .transient)
    }

    @Test func closeCodesUsedOnlyWithoutHTTPStatus() {
        // Community-reported Live close semantics: consulted only as fallback.
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(closeCode: 1011, message: "")) == .rateLimited)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(closeCode: 1008, message: "")) == .keyOrProjectDenied)
        // An HTTP status wins over a contradictory close code.
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(httpStatus: 500, closeCode: 1011, message: "")) == .transient)
    }

    @Test func messageTextIsLastResort() {
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(message: "You exceeded your current quota")) == .rateLimited)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(message: "RESOURCE_EXHAUSTED")) == .rateLimited)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(message: "API key not valid")) == .keyOrProjectDenied)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(message: "Prepay credits depleted, check billing")) == .billingOrCredits)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(message: "The network connection was lost")) == .transient)
        #expect(GeminiFailureClassifier.classify(GeminiConnectionFailure(message: "something odd happened")) == .unknown)
    }

    // MARK: - Failover and cooldown

    @Test func rateLimitedKeyCoolsDownAndNextKeyIsTried() throws {
        let pool = makePool()
        let first = try pool.acquireKey()
        pool.reportFailure(first.id, failure: GeminiConnectionFailure(httpStatus: 429, message: "quota"))

        let second = try pool.acquireKey(preferring: first.id)
        #expect(second.id != first.id)
        if case .coolingDown = state(of: first.id, in: pool) {} else {
            Issue.record("expected first key to be cooling down")
        }
    }

    @Test func serverRetryHintSetsCooldownLength() throws {
        let pool = makePool()
        let first = try pool.acquireKey()
        pool.reportFailure(first.id, failure: GeminiConnectionFailure(httpStatus: 429, retryAfter: 120, message: "quota"))
        guard case .coolingDown(let until, _) = state(of: first.id, in: pool) else {
            Issue.record("expected cooling down")
            return
        }
        #expect(until == Date(timeIntervalSince1970: 1_000_000).addingTimeInterval(120))
    }

    @Test func allKeysUnavailableReportsEarliestRetry() throws {
        let pool = makePool(keys: ["key-alpha-1111", "key-beta-2222"])
        let a = try pool.acquireKey()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 429, retryAfter: 30, message: ""))
        let b = try pool.acquireKey(preferring: a.id)
        pool.reportFailure(b.id, failure: GeminiConnectionFailure(httpStatus: 429, retryAfter: 90, message: ""))

        #expect(throws: GeminiKeyPool.PoolError.self) {
            try pool.acquireKey()
        }
        #expect(pool.nextRetryDate == Date(timeIntervalSince1970: 1_000_000).addingTimeInterval(30))
    }

    @Test func rejectedKeyIsParkedButRecoversOnReset() throws {
        let pool = makePool(keys: ["key-alpha-1111", "key-beta-2222"])
        let a = try pool.acquireKey()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 403, message: "denied"))

        // Parked: never handed out again this run...
        for _ in 0..<5 {
            let next = try pool.acquireKey(preferring: a.id)
            #expect(next.id != a.id)
        }
        // ...until the user resets states.
        pool.resetStates()
        let again = try pool.acquireKey(preferring: a.id)
        #expect(again.id == a.id)
    }

    @Test func billingFailureParksWithSharedAccountNote() throws {
        let pool = makePool()
        let a = try pool.acquireKey()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 402, message: ""))
        guard case .parked(let reason) = state(of: a.id, in: pool) else {
            Issue.record("expected parked")
            return
        }
        #expect(reason.contains("billing"))
    }

    @Test func clientErrorDoesNotPenalizeKey() throws {
        let pool = makePool()
        let a = try pool.acquireKey()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 400, message: "bad request"))
        let again = try pool.acquireKey(preferring: a.id)
        #expect(again.id == a.id)
    }

    @Test func transientBlipsKeepKeyReadyUntilThirdStrike() throws {
        let pool = makePool()
        let a = try pool.acquireKey()
        let blip = GeminiConnectionFailure(message: "The network connection was lost")
        pool.reportFailure(a.id, failure: blip)
        pool.reportFailure(a.id, failure: blip)
        #expect(try pool.acquireKey(preferring: a.id).id == a.id)
        pool.reportFailure(a.id, failure: blip)
        if case .coolingDown = state(of: a.id, in: pool) {} else {
            Issue.record("expected cooling down after third transient failure")
        }
    }

    @Test func successResetsKeyToReady() throws {
        let pool = makePool(keys: ["key-alpha-1111", "key-beta-2222"])
        let a = try pool.acquireKey()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 429, message: ""))
        pool.reportSuccess(a.id)
        #expect(try pool.acquireKey(preferring: a.id).id == a.id)
    }

    @Test func emptyPoolThrowsNoKeys() {
        let pool = makePool(keys: [])
        #expect(throws: GeminiKeyPool.PoolError.noKeys) {
            try pool.acquireKey()
        }
    }

    @Test func duplicateKeysAreStoredOnce() {
        let pool = makePool(keys: ["key-alpha-1111", "key-alpha-1111", "  key-beta-2222  "])
        #expect(pool.entries.count == 2)
    }

    @Test func cooldownExpiresAndKeyBecomesReadyAgain() throws {
        final class Clock { var date = Date(timeIntervalSince1970: 1_000_000) }
        let clock = Clock()
        let pool = GeminiKeyPool(keys: ["key-alpha-1111", "key-beta-2222"])
        pool.now = { clock.date }

        let a = try pool.acquireKey()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 429, retryAfter: 30, message: ""))
        #expect(try pool.acquireKey(preferring: a.id).id != a.id) // beta serves while alpha cools

        clock.date = clock.date.addingTimeInterval(31)
        #expect(try pool.acquireKey(preferring: a.id).id == a.id) // cooldown expired
    }

    @Test func failoverHandsOutTheNextKeyNotTheSameOne() throws {
        let pool = makePool()
        let a = try pool.acquireKey()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 429, message: ""))
        let b = try pool.acquireKey(preferring: a.id)
        // beta follows alpha in list order
        #expect(b.masked.hasSuffix("2222"))
        pool.reportFailure(b.id, failure: GeminiConnectionFailure(httpStatus: 429, message: ""))
        let c = try pool.acquireKey(preferring: b.id)
        #expect(c.masked.hasSuffix("3333"))
    }

    @Test func parkedKeysHaveNoAutomaticRetryDate() throws {
        let pool = makePool(keys: ["key-alpha-1111"])
        let a = try pool.acquireKey()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 403, message: ""))
        #expect(pool.nextRetryDate == nil)
        #expect(throws: GeminiKeyPool.PoolError.self) { try pool.acquireKey() }
    }

    @Test func rateLimitBackoffEscalatesAcrossCooldownExpiries() throws {
        final class Clock { var date = Date(timeIntervalSince1970: 1_000_000) }
        let clock = Clock()
        let pool = GeminiKeyPool(keys: ["key-alpha-1111"])
        pool.now = { clock.date }
        let a = try pool.acquireKey()

        // First failure: ~20s cooldown (jitter 0.8-1.2).
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 429, message: ""))
        guard case .coolingDown(let firstUntil, _) = state(of: a.id, in: pool) else {
            Issue.record("expected cooling down")
            return
        }
        let first = firstUntil.timeIntervalSince(clock.date)
        #expect(first >= 20 * 0.8 && first <= 20 * 1.2)

        // Cooldown expires; counters persist, so the next failure doubles.
        clock.date = clock.date.addingTimeInterval(25)
        #expect(try pool.acquireKey(preferring: a.id).id == a.id)
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 429, message: ""))
        guard case .coolingDown(let secondUntil, _) = state(of: a.id, in: pool) else {
            Issue.record("expected cooling down")
            return
        }
        let second = secondUntil.timeIntervalSince(clock.date)
        #expect(second >= 40 * 0.8 && second <= 40 * 1.2)
    }

    @Test func resetStatesClearsEscalationCounters() throws {
        let pool = makePool(keys: ["key-alpha-1111"])
        let a = try pool.acquireKey()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 429, message: ""))
        pool.resetStates()
        pool.reportFailure(a.id, failure: GeminiConnectionFailure(httpStatus: 429, message: ""))
        guard case .coolingDown(let until, _) = state(of: a.id, in: pool) else {
            Issue.record("expected cooling down")
            return
        }
        let cooldown = until.timeIntervalSince(Date(timeIntervalSince1970: 1_000_000))
        #expect(cooldown >= 20 * 0.8 && cooldown <= 20 * 1.2) // back to base, not doubled
    }

    // MARK: - Masking

    @Test func maskingShowsOnlyLastFourCharacters() {
        let key = "AIzaSySecretMaterial1234567890abcd"
        let masked = GeminiKeyPool.masked(key)
        #expect(masked.hasSuffix("abcd"))
        #expect(!masked.contains("Secret"))
        #expect(masked == "••••abcd")
        // Fingerprints are stable and reveal nothing of the secret.
        #expect(GeminiKeyPool.fingerprint(key) == GeminiKeyPool.fingerprint(key))
        #expect(GeminiKeyPool.fingerprint(key) != GeminiKeyPool.fingerprint("other-key"))
    }
}
