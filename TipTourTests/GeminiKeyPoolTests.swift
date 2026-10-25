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

    // MARK: - Failover runner (orchestration seam)

    private func noWait(_: Int, _: GeminiKeyFailureKind, _: GeminiConnectionFailure) -> TimeInterval { 0 }

    @Test func acquireRespectsRoundExclusions() throws {
        let pool = makePool()
        let a = try pool.acquireKey()
        let b = try pool.acquireKey(preferring: a.id, excluding: [a.id])
        #expect(b.id != a.id)
    }

    @Test func ninePlusKeysAllRateLimitedAreCoveredDistinctlyThenAllBlocked() async throws {
        let keys = (1...12).map { "key-\($0)-secret-material-\($0)" }
        let pool = makePool(keys: keys)
        var attempted: [String] = []
        do {
            try await GeminiKeyFailover.run(
                pool: pool,
                policy: GeminiFailoverPolicy(maxRounds: 2, maxAttempts: max(4, keys.count * 2), wait: noWait),
                isCancelled: { false },
                sleep: { _ in },
                failureFrom: { _ in GeminiConnectionFailure(httpStatus: 429, retryAfter: 30, message: "quota") },
                attempt: { entry in
                    attempted.append(entry.id)
                    throw NSError(domain: "test", code: 1, userInfo: [NSLocalizedDescriptionKey: "quota"])
                }
            )
            Issue.record("expected the run to throw")
        } catch let error as GeminiKeyPool.PoolError {
            guard case .allUnavailable(let retryAt) = error else {
                Issue.record("expected allUnavailable, got \(error)")
                return
            }
            #expect(retryAt == Date(timeIntervalSince1970: 1_000_000).addingTimeInterval(30))
        }
        // Round 1 tried every distinct key exactly once; round 2 found all
        // of them cooling and stopped with the truthful "all blocked" error
        // carrying the earliest retry time.
        #expect(attempted.count == 12)
        #expect(Set(attempted).count == 12)
    }

    @Test func transientFailuresAdvanceAcrossAllKeysInsteadOfBurningStrikesOnOne() async throws {
        // The old flat 8-attempt cap plus same-key preference let one key's
        // 3 transient strikes consume the budget and skip later ready keys.
        let keys = (1...6).map { "key-\($0)-secret-material-\($0)" }
        let pool = makePool(keys: keys)
        var attempted: [String] = []
        _ = try? await GeminiKeyFailover.run(
            pool: pool,
            policy: GeminiFailoverPolicy(maxRounds: 2, maxAttempts: max(4, keys.count * 2), wait: noWait),
            isCancelled: { false },
            sleep: { _ in },
            failureFrom: { _ in GeminiConnectionFailure(message: "The network connection was lost") },
            attempt: { entry in
                attempted.append(entry.id)
                throw NSError(domain: "test", code: 2, userInfo: [NSLocalizedDescriptionKey: "network down"])
            }
        )
        #expect(Set(attempted).count == 6)   // every key tried in round 1
        #expect(attempted.count == 12)       // one retry each in round 2
    }

    @Test func attemptsExhaustedIsDistinctFromAllBlocked() async throws {
        let pool = makePool()
        var attemptedCount = 0
        do {
            try await GeminiKeyFailover.run(
                pool: pool,
                policy: GeminiFailoverPolicy(maxRounds: 2, maxAttempts: 1, wait: noWait),
                isCancelled: { false },
                sleep: { _ in },
                failureFrom: { _ in GeminiConnectionFailure(message: "The network connection was lost") },
                attempt: { _ in
                    attemptedCount += 1
                    throw NSError(domain: "test", code: 3, userInfo: [NSLocalizedDescriptionKey: "network down"])
                }
            )
            Issue.record("expected the run to throw")
        } catch let error as GeminiKeyPool.PoolError {
            guard case .attemptsExhausted(let triedKeys) = error else {
                Issue.record("expected attemptsExhausted, got \(error)")
                return
            }
            #expect(triedKeys == 1)
        }
        #expect(attemptedCount == 1)
        // Keys that were never tried were never blamed — still ready.
        #expect(pool.entries.allSatisfy { $0.state == .ready })
    }

    @Test func cancellationErrorNeverPenalizesAKey() async throws {
        let pool = makePool(keys: ["key-alpha-1111", "key-beta-2222"])
        var attemptedCount = 0
        do {
            try await GeminiKeyFailover.run(
                pool: pool,
                policy: GeminiFailoverPolicy(maxRounds: 2, maxAttempts: 10, wait: noWait),
                isCancelled: { false },
                sleep: { _ in },
                failureFrom: { _ in GeminiConnectionFailure(message: "must not be used") },
                attempt: { _ in
                    attemptedCount += 1
                    throw CancellationError()
                }
            )
            Issue.record("expected CancellationError")
        } catch is CancellationError {
            // expected
        }
        #expect(attemptedCount == 1)
        #expect(pool.entries.allSatisfy {
            $0.state == .ready && $0.consecutiveRateLimits == 0 && $0.consecutiveTransients == 0
        })
    }

    @Test func urlSessionCancelledNeverPenalizesAKey() async throws {
        // NSURLErrorCancelled (-999) — user stopped or switched mode
        // mid-connect. Compared by domain string for Linux portability.
        let pool = makePool(keys: ["key-alpha-1111", "key-beta-2222"])
        do {
            try await GeminiKeyFailover.run(
                pool: pool,
                policy: GeminiFailoverPolicy(maxRounds: 2, maxAttempts: 10, wait: noWait),
                isCancelled: { false },
                sleep: { _ in },
                failureFrom: { _ in GeminiConnectionFailure(message: "must not be used") },
                attempt: { _ in throw NSError(domain: "NSURLErrorDomain", code: -999) }
            )
            Issue.record("expected CancellationError")
        } catch is CancellationError {
            // expected
        }
        #expect(pool.entries.allSatisfy {
            $0.state == .ready && $0.consecutiveRateLimits == 0 && $0.consecutiveTransients == 0
        })
    }

    @Test func staleSessionFlagNeverPenalizesAKey() async throws {
        // User stopped / mode switched while a connect was in flight: the
        // liveness flag flips before the error arrives.
        let pool = makePool(keys: ["key-alpha-1111", "key-beta-2222"])
        var stale = false
        do {
            try await GeminiKeyFailover.run(
                pool: pool,
                policy: GeminiFailoverPolicy(maxRounds: 2, maxAttempts: 10, wait: noWait),
                isCancelled: { stale },
                sleep: { _ in },
                failureFrom: { _ in GeminiConnectionFailure(message: "The network connection was lost") },
                attempt: { _ in
                    stale = true
                    throw NSError(domain: "test", code: 4, userInfo: [NSLocalizedDescriptionKey: "network down"])
                }
            )
            Issue.record("expected CancellationError")
        } catch is CancellationError {
            // expected
        }
        #expect(pool.entries.allSatisfy {
            $0.state == .ready && $0.consecutiveRateLimits == 0 && $0.consecutiveTransients == 0
        })
    }

    @Test func clientErrorStopsImmediatelyWithoutBlamingAnyKey() async throws {
        struct BadRequest: Error {}
        let pool = makePool()
        var attemptedCount = 0
        do {
            try await GeminiKeyFailover.run(
                pool: pool,
                policy: GeminiFailoverPolicy(maxRounds: 2, maxAttempts: 10, wait: noWait),
                isCancelled: { false },
                sleep: { _ in },
                failureFrom: { _ in GeminiConnectionFailure(httpStatus: 400, message: "bad request") },
                attempt: { _ in
                    attemptedCount += 1
                    throw BadRequest()
                }
            )
            Issue.record("expected BadRequest")
        } catch is BadRequest {
            // expected — the original request error, not a pool error
        }
        #expect(attemptedCount == 1)
        #expect(pool.entries.allSatisfy { $0.state == .ready })
    }

    @Test func secondRoundRetriesAKeyWhoseCooldownExpired() async throws {
        final class Clock { var date = Date(timeIntervalSince1970: 1_000_000) }
        let clock = Clock()
        let pool = GeminiKeyPool(keys: ["key-alpha-1111"])
        pool.now = { clock.date }
        var attemptCount = 0
        let entry = try await GeminiKeyFailover.run(
            pool: pool,
            policy: GeminiFailoverPolicy(maxRounds: 2, maxAttempts: 10,
                                         wait: { _, _, failure in failure.retryAfter ?? 0 }),
            isCancelled: { false },
            sleep: { seconds in clock.date = clock.date.addingTimeInterval(seconds) },
            failureFrom: { _ in GeminiConnectionFailure(httpStatus: 429, retryAfter: 30, message: "quota") },
            attempt: { _ in
                attemptCount += 1
                if attemptCount == 1 {
                    throw NSError(domain: "test", code: 5, userInfo: [NSLocalizedDescriptionKey: "quota"])
                }
            }
        )
        #expect(attemptCount == 2)
        #expect(entry.masked.hasSuffix("1111"))
        #expect(pool.entries[0].state == .ready)
    }

    // MARK: - Reconnect backoff bounds

    @Test func reconnectBackoffStartsSmallAndStaysCappedAtLargeAttempts() {
        let policy = GeminiFailoverPolicy.reconnect(keyCount: 3)
        // First retry: ~0.5 s base with jitter — a blip, not a pause.
        for _ in 0..<50 {
            let wait = policy.wait(1, .transient, GeminiConnectionFailure(message: "boom"))
            #expect(wait.isFinite && wait >= 0.4 && wait <= 0.6)
        }
        // Later attempts in any pool: growth is capped at 15 s base
        // (18 s with jitter). The uncapped doubling this replaces reached
        // multi-hour sleeps by the late attempts of a large pool.
        for attempt in [2, 5, 10, 37, 100, 10_000] {
            for _ in 0..<20 {
                let wait = policy.wait(attempt, .transient, GeminiConnectionFailure(message: "boom"))
                #expect(wait.isFinite && wait >= 0 && wait <= 18.0)
            }
        }
    }

    @Test func reconnectBackoffExtremeIndicesStayFiniteAndBounded() {
        let policy = GeminiFailoverPolicy.reconnect(keyCount: 1)
        // Degenerate and absurd indices must never yield NaN, infinity, or
        // a wait that overflows the nanosecond conversion at the call site.
        for attempt in [0, -1, -100, Int.max] {
            let wait = policy.wait(attempt, .unknown, GeminiConnectionFailure(message: "boom"))
            #expect(wait.isFinite && wait >= 0 && wait <= 18.0)
        }
    }

    @Test func reconnectHonorsServerRetryHintSeparatelyWithItsOwnCap() {
        let policy = GeminiFailoverPolicy.reconnect(keyCount: 2)
        // A hint longer than the capped base wins, exactly as in the
        // initial connect.
        #expect(policy.wait(1, .rateLimited,
                            GeminiConnectionFailure(httpStatus: 429, retryAfter: 45, message: "quota")) == 45)
        // An absurd hint is clamped to its own 60 s cap, not slept raw.
        #expect(policy.wait(1, .rateLimited,
                            GeminiConnectionFailure(httpStatus: 429, retryAfter: 3_600, message: "quota")) == 60)
        // A non-finite hint is ignored, leaving the capped base wait.
        let nanHint = policy.wait(1, .rateLimited,
                                  GeminiConnectionFailure(httpStatus: 429, retryAfter: .nan, message: "quota"))
        #expect(nanHint.isFinite && nanHint >= 0 && nanHint <= 18.0)
    }

    @Test func largePoolReconnectRunSleepsOnlyBoundedWaits() async throws {
        // 21 keys (attempt bound 42) — a pool size where the old uncapped
        // exponential slept for hours and then trapped converting the wait
        // to nanoseconds. Every sleep must be finite and capped, and the
        // run must still terminate with the truthful terminal error.
        let keys = (1...21).map { "key-\($0)-secret-material-\($0)" }
        let pool = makePool(keys: keys)
        var sleeps: [TimeInterval] = []
        var attempted: [String] = []
        do {
            try await GeminiKeyFailover.run(
                pool: pool,
                policy: .reconnect(keyCount: keys.count),
                isCancelled: { false },
                sleep: { seconds in
                    #expect(seconds.isFinite && seconds >= 0 && seconds <= 60)
                    sleeps.append(seconds)
                },
                failureFrom: { _ in GeminiConnectionFailure(httpStatus: 429, retryAfter: 5, message: "quota") },
                attempt: { entry in
                    attempted.append(entry.id)
                    throw NSError(domain: "test", code: 6, userInfo: [NSLocalizedDescriptionKey: "quota"])
                }
            )
            Issue.record("expected the run to throw")
        } catch let error as GeminiKeyPool.PoolError {
            guard case .allUnavailable(let retryAt) = error else {
                Issue.record("expected allUnavailable, got \(error)")
                return
            }
            #expect(retryAt == Date(timeIntervalSince1970: 1_000_000).addingTimeInterval(5))
        }
        // Round 1 tried every one of the 21 keys exactly once — no ready
        // key skipped — then round 2 found all of them cooling.
        #expect(attempted.count == 21)
        #expect(Set(attempted).count == 21)
        #expect(sleeps.count == 21)
    }

    @Test func sleepNanosecondsNeverTrapsOnBadInput() {
        #expect(GeminiKeyFailover.sleepNanoseconds(.nan) == 0)
        #expect(GeminiKeyFailover.sleepNanoseconds(.infinity) == 0)
        #expect(GeminiKeyFailover.sleepNanoseconds(-.infinity) == 0)
        #expect(GeminiKeyFailover.sleepNanoseconds(-5) == 0)
        #expect(GeminiKeyFailover.sleepNanoseconds(0) == 0)
        #expect(GeminiKeyFailover.sleepNanoseconds(1) == 1_000_000_000)
        // Absurd values clamp to the defensive ceiling instead of trapping
        // the Double -> UInt64 conversion.
        #expect(GeminiKeyFailover.sleepNanoseconds(1e300) == 300_000_000_000)
    }

    // MARK: - Persistence honesty

    @Test func failedPersistenceDoesNotTouchPoolOrReportSaved() {
        let pool = makePool(keys: ["key-alpha-1111"])
        pool.keyListWriter = { _ in false }
        #expect(pool.addKey("key-beta-2222") == false)
        #expect(pool.entries.count == 1)   // memory unchanged — UI cannot lie "Saved"

        let id = pool.entries[0].id
        #expect(pool.removeKey(id: id) == false)
        #expect(pool.entries.count == 1)   // still there — no fake deletion
    }

    @Test func successfulPersistenceDrivesReload() {
        final class Store { var keys: [String] = ["key-alpha-1111"] }
        let store = Store()
        let pool = makePool(keys: store.keys)
        pool.keyListWriter = { store.keys = $0; return true }
        pool.keyListReader = { store.keys }

        #expect(pool.addKey("key-beta-2222") == true)
        #expect(store.keys == ["key-alpha-1111", "key-beta-2222"])

        // An outside change is picked up on reload, cooldowns preserved.
        pool.reportFailure(pool.entries[0].id, failure: GeminiConnectionFailure(httpStatus: 403, message: ""))
        store.keys.append("key-gamma-3333")
        pool.reloadKeys()
        #expect(pool.entries.count == 3)
        guard case .parked = pool.entries[0].state else {
            Issue.record("expected first key to stay parked across reload")
            return
        }
    }

    // MARK: - Error scrubbing

    @Test func sanitizerStripsKeyURLsAndSecrets() {
        let secret = "AIzaSySecretMaterial1234567890abcd"
        let msg = "The operation couldn't be completed. wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=\(secret)"
        let out = GeminiKeyPool.sanitized(msg, secrets: [secret])
        #expect(!out.contains(secret))
        #expect(!out.contains("key=AIza"))

        // Unknown keys embedded as URL params are scrubbed even without a
        // supplied secret list.
        let out2 = GeminiKeyPool.sanitized("connect failed: https://example.com/ws?key=SomeOtherKey123&x=1")
        #expect(!out2.contains("SomeOtherKey123"))
        #expect(out2.contains("key=••••"))
        #expect(out2.contains("&x=1"))
    }
}
