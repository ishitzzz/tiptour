import XCTest
@testable import TipTour

/// Fake pasteboard that can simulate a concurrent user copy.
private final class FakePasteboard: AskStagingPasteboard {
    var changeCount = 10
    var contents = "user-original"
    func writeStaged(_ payload: AskStagedPayload) -> Int {
        contents = payload.kind == .image ? "image" : "text"
        changeCount += 1
        return changeCount
    }
    func restorePrevious() -> Int {
        contents = "user-original"
        changeCount += 1
        return changeCount
    }
    func userCopies(_ value: String) { contents = value; changeCount += 1 }
}


// MARK: - Speech lifecycle test doubles

/// A manually completed permission prompt: the coordinator's permission
/// closure parks here until the test grants or denies it.
private final class PermissionGate: @unchecked Sendable {
    enum TestError: Error, Equatable { case speechDenied, micDenied, installFailed }

    private var continuation: CheckedContinuation<Void, Error>?
    var isWaiting: Bool { continuation != nil }

    func wait() async throws {
        try await withCheckedThrowingContinuation { continuation = $0 }
    }

    func grant() {
        guard let continuation else { return }
        self.continuation = nil
        continuation.resume()
    }

    func deny(_ error: TestError) {
        guard let continuation else { return }
        self.continuation = nil
        continuation.resume(throwing: error)
    }
}

/// Hands each permission request its own gate, so overlapping starts can be
/// completed independently (old start vs new start).
private final class GateQueue: @unchecked Sendable {
    private(set) var gates: [PermissionGate] = []
    func next() -> PermissionGate {
        let gate = PermissionGate()
        gates.append(gate)
        return gate
    }
}


/// Mutable install counter shared with the coordinator's install closure.
private final class InstallCounter: @unchecked Sendable {
    var value = 0
}

private func awaitCondition(
    _ condition: @escaping () -> Bool,
    file: StaticString = #filePath,
    line: UInt = #line
) async {
    for _ in 0..<200 where !condition() {
        try? await Task.sleep(nanoseconds: 10_000_000)
    }
    XCTAssertTrue(condition(), "condition never became true", file: file, line: line)
}

private func assertSuperseded(
    _ task: Task<Void, Error>,
    file: StaticString = #filePath,
    line: UInt = #line
) async {
    do {
        try await task.value
        XCTFail("expected supersession, got success", file: file, line: line)
    } catch is AskSpeechStartCoordinator.Supersession {
        // expected
    } catch {
        XCTFail("expected supersession, got \(error)", file: file, line: line)
    }
}

final class AskHarnessCoreTests: XCTestCase {

    // MARK: clipboard ownership

    func testRestoreHappensWhenStillOwned() throws {
        let board = FakePasteboard()
        let ownership = AskClipboardOwnership(pasteboard: board)
        try ownership.stage(AskStagedPayload(kind: .image))
        try ownership.stage(AskStagedPayload(kind: .text))
        XCTAssertTrue(ownership.restoreIfStillOwned())
        XCTAssertEqual(board.contents, "user-original")
    }

    func testConcurrentCopyAfterImageBlocksTextWriteAndKeepsUserCopy() throws {
        let board = FakePasteboard()
        let ownership = AskClipboardOwnership(pasteboard: board)
        try ownership.stage(AskStagedPayload(kind: .image))
        board.userCopies("newer-user-copy")
        XCTAssertThrowsError(try ownership.assertOwnedBeforePaste()) {
            XCTAssertEqual($0 as? AskClipboardError, .clipboardChangedByOthers)
        }
        XCTAssertThrowsError(try ownership.stage(AskStagedPayload(kind: .text)))
        XCTAssertFalse(ownership.restoreIfStillOwned())
        XCTAssertEqual(board.contents, "newer-user-copy")
    }

    func testCopyDuringFinalWaitIsNotRestoredOver() throws {
        let board = FakePasteboard()
        let ownership = AskClipboardOwnership(pasteboard: board)
        try ownership.stage(AskStagedPayload(kind: .text))
        board.userCopies("copied-during-wait")
        XCTAssertFalse(ownership.restoreIfStillOwned())
        XCTAssertEqual(board.contents, "copied-during-wait")
    }

    func testRestoreWithoutAnyWriteDoesNothing() {
        let board = FakePasteboard()
        let ownership = AskClipboardOwnership(pasteboard: board)
        XCTAssertFalse(ownership.restoreIfStillOwned())
        XCTAssertEqual(board.changeCount, 10)
    }

    // MARK: session generations

    func testRepressWhileFinishingIsRejected() {
        var gate = AskSessionGate()
        let first = gate.begin()
        XCTAssertNotNil(first)
        XCTAssertNil(gate.begin(), "no second session while capturing")
        XCTAssertEqual(gate.beginFinish(), first)
        XCTAssertNil(gate.begin(), "no new session while the old one is finishing")
        XCTAssertTrue(gate.mayPublish(first!))
        gate.finished()
        XCTAssertNotNil(gate.begin())
    }

    func testCancelledFinishCannotPublish() {
        var gate = AskSessionGate()
        let first = gate.begin()!
        _ = gate.beginFinish()
        gate.cancel()
        XCTAssertFalse(gate.mayPublish(first))
        XCTAssertNil(gate.begin(), "still finishing until the task ends")
        gate.finished()
        let second = gate.begin()!
        XCTAssertNotEqual(first, second)
        XCTAssertFalse(gate.isCurrent(first))
    }

    func testCancelWhileCapturingReturnsToIdle() {
        var gate = AskSessionGate()
        let first = gate.begin()!
        gate.cancel()
        XCTAssertEqual(gate.phase, .idle)
        XCTAssertFalse(gate.isCurrent(first))
        XCTAssertNil(gate.beginFinish())
    }

    // MARK: provenance

    func testAskChordFlags() {
        let all = AskGestureProvenance.controlMask | AskGestureProvenance.optionMask | AskGestureProvenance.shiftMask
        XCTAssertTrue(AskGestureProvenance.isAskChord(flagsRawValue: all))
        XCTAssertFalse(AskGestureProvenance.isAskChord(flagsRawValue: all | AskGestureProvenance.commandMask))
        XCTAssertFalse(AskGestureProvenance.isAskChord(flagsRawValue: AskGestureProvenance.controlMask | AskGestureProvenance.shiftMask))
        XCTAssertFalse(AskGestureProvenance.isAskChord(flagsRawValue: 0))
    }

    func testMasksMatchAppKitModifierFlags() {
        #if canImport(AppKit)
        XCTAssertEqual(UInt(AskGestureProvenance.shiftMask), NSEvent.ModifierFlags.shift.rawValue)
        XCTAssertEqual(UInt(AskGestureProvenance.controlMask), NSEvent.ModifierFlags.control.rawValue)
        XCTAssertEqual(UInt(AskGestureProvenance.optionMask), NSEvent.ModifierFlags.option.rawValue)
        XCTAssertEqual(UInt(AskGestureProvenance.commandMask), NSEvent.ModifierFlags.command.rawValue)
        #endif
    }

    // MARK: composer policy

    func testOnlyTextAreaIsAComposer() {
        XCTAssertTrue(AskComposerPolicy.isComposerRole(role: "AXTextArea", subrole: nil))
        XCTAssertFalse(AskComposerPolicy.isComposerRole(role: "AXTextArea", subrole: "AXSearchField"))
        XCTAssertFalse(AskComposerPolicy.isComposerRole(role: "AXSearchField", subrole: nil))
        XCTAssertFalse(AskComposerPolicy.isComposerRole(role: "AXComboBox", subrole: nil))
        XCTAssertFalse(AskComposerPolicy.isComposerRole(role: "AXTextField", subrole: nil))
        XCTAssertFalse(AskComposerPolicy.isComposerRole(role: nil, subrole: nil))
    }

    // MARK: retry progress

    func testRetrySkipsPiecesAlreadyPasted() {
        var progress = AskInsertionProgress()
        progress.prepare(forTarget: "com.a")
        progress.imagePasted = true
        progress.prepare(forTarget: "com.a")
        XCTAssertTrue(progress.imagePasted, "same target keeps progress")
        progress.prepare(forTarget: "com.b")
        XCTAssertFalse(progress.imagePasted, "new target starts fresh")
    }

    // MARK: markings and sizing

    func testMarkingDecisions() {
        XCTAssertEqual(AskMarkingPolicy.decide(pointCount: 0, pointsOnDisplayCount: 0), .none)
        XCTAssertEqual(AskMarkingPolicy.decide(pointCount: 1, pointsOnDisplayCount: 1), .none)
        XCTAssertEqual(AskMarkingPolicy.decide(pointCount: 5, pointsOnDisplayCount: 5), .draw(count: 5))
        XCTAssertEqual(AskMarkingPolicy.decide(pointCount: 5, pointsOnDisplayCount: 3), .rejectedOffDisplay)
        XCTAssertEqual(AskMarkingPolicy.decide(pointCount: 5, pointsOnDisplayCount: 0), .rejectedOffDisplay)
    }

    func testCaptureSizingUsesScale() {
        let retina = AskCaptureSizing.pixelSize(pointWidth: 1512, pointHeight: 982, scale: 2)
        XCTAssertEqual(retina.width, 3024)
        XCTAssertEqual(retina.height, 1964)
        let bad = AskCaptureSizing.pixelSize(pointWidth: 100, pointHeight: 50, scale: 0)
        XCTAssertEqual(bad.width, 100)
        XCTAssertEqual(bad.height, 50)
    }

    func testCaptionDoesNotPromiseUnchangedScreen() {
        let text = AskPreviewCaption.text(completedTimeText: "10:00:01", delaySeconds: 0.34, decision: .draw(count: 9))
        XCTAssertTrue(text.contains("may have changed"))
        XCTAssertTrue(text.contains("0.3s"))
        let rejected = AskPreviewCaption.text(completedTimeText: "10:00:01", delaySeconds: 0.1, decision: .rejectedOffDisplay)
        XCTAssertTrue(rejected.contains("not drawn"))
    }

    // MARK: speech lifecycle seam

    private func makeCoordinator(
        speech: GateQueue,
        mic: GateQueue,
        installCount: InstallCounter
    ) -> AskSpeechStartCoordinator {
        AskSpeechStartCoordinator(
            requestSpeechPermission: { try await speech.next().wait() },
            requestMicrophonePermission: { try await mic.next().wait() },
            installRecording: { installCount.value += 1 }
        )
    }

    func testGrantedPermissionsInstallExactlyOnce() async {
        let speech = GateQueue(), mic = GateQueue(), counter = InstallCounter()
        let coordinator = makeCoordinator(speech: speech, mic: mic, installCount: counter)
        let start = Task { try await coordinator.start() }
        await awaitCondition { speech.gates.first?.isWaiting == true }
        speech.gates[0].grant()
        await awaitCondition { mic.gates.first?.isWaiting == true }
        mic.gates[0].grant()
        try? await start.value
        XCTAssertEqual(counter.value, 1)
        XCTAssertFalse(coordinator.hasPendingStart)
    }

    func testReleaseWhileSpeechPermissionPendingNeverInstalls() async {
        let speech = GateQueue(), mic = GateQueue(), counter = InstallCounter()
        let coordinator = makeCoordinator(speech: speech, mic: mic, installCount: counter)
        let start = Task { try await coordinator.start() }
        await awaitCondition { speech.gates.first?.isWaiting == true }
        coordinator.invalidatePendingStart()  // user released mid-prompt
        speech.gates[0].grant()
        await assertSuperseded(start)
        XCTAssertEqual(counter.value, 0, "no recording after stop supersession")
        XCTAssertFalse(coordinator.hasPendingStart)
    }

    func testReleaseWhileMicPermissionPendingNeverInstalls() async {
        let speech = GateQueue(), mic = GateQueue(), counter = InstallCounter()
        let coordinator = makeCoordinator(speech: speech, mic: mic, installCount: counter)
        let start = Task { try await coordinator.start() }
        await awaitCondition { speech.gates.first?.isWaiting == true }
        speech.gates[0].grant()
        await awaitCondition { mic.gates.first?.isWaiting == true }
        coordinator.invalidatePendingStart()  // user released on the second prompt
        mic.gates[0].grant()
        await assertSuperseded(start)
        XCTAssertEqual(counter.value, 0)
    }

    func testNewStartSupersedesPendingStartAndInstallsExactlyOnce() async {
        let speech = GateQueue(), mic = GateQueue(), counter = InstallCounter()
        let coordinator = makeCoordinator(speech: speech, mic: mic, installCount: counter)
        let first = Task { try await coordinator.start() }
        await awaitCondition { speech.gates.first?.isWaiting == true }

        // New press: a second start before the first one's prompt resolves.
        let second = Task { try await coordinator.start() }
        await awaitCondition { speech.gates.count == 2 && speech.gates[1].isWaiting }

        speech.gates[0].grant()  // late answer for the old start
        await assertSuperseded(first)

        speech.gates[1].grant()
        await awaitCondition { mic.gates.first?.isWaiting == true }
        mic.gates[0].grant()
        try? await second.value
        XCTAssertEqual(counter.value, 1, "only the newer start may install")
    }

    func testSpeechDenialSurfacesEvenAfterRelease() async {
        let speech = GateQueue(), mic = GateQueue(), counter = InstallCounter()
        let coordinator = makeCoordinator(speech: speech, mic: mic, installCount: counter)
        let start = Task { try await coordinator.start() }
        await awaitCondition { speech.gates.first?.isWaiting == true }
        coordinator.invalidatePendingStart()  // released, then the prompt was denied
        speech.gates[0].deny(.speechDenied)
        do {
            try await start.value
            XCTFail("expected speech denial")
        } catch let error as PermissionGate.TestError {
            XCTAssertEqual(error, .speechDenied, "denial is durable state and must surface, not be swallowed as supersession")
        } catch {
            XCTFail("expected speech denial, got \(error)")
        }
        XCTAssertEqual(counter.value, 0)
        XCTAssertFalse(coordinator.hasPendingStart)
    }

    func testMicDenialThrowsAndNeverInstalls() async {
        let speech = GateQueue(), mic = GateQueue(), counter = InstallCounter()
        let coordinator = makeCoordinator(speech: speech, mic: mic, installCount: counter)
        let start = Task { try await coordinator.start() }
        await awaitCondition { speech.gates.first?.isWaiting == true }
        speech.gates[0].grant()
        await awaitCondition { mic.gates.first?.isWaiting == true }
        mic.gates[0].deny(.micDenied)
        do {
            try await start.value
            XCTFail("expected mic denial")
        } catch let error as PermissionGate.TestError {
            XCTAssertEqual(error, .micDenied)
        } catch {
            XCTFail("expected mic denial, got \(error)")
        }
        XCTAssertEqual(counter.value, 0)
        XCTAssertFalse(coordinator.hasPendingStart)
    }

    func testInstallFailurePropagatesAndClearsPending() async {
        let speech = GateQueue(), mic = GateQueue()
        let coordinator = AskSpeechStartCoordinator(
            requestSpeechPermission: { try await speech.next().wait() },
            requestMicrophonePermission: { try await mic.next().wait() },
            installRecording: { throw PermissionGate.TestError.installFailed }
        )
        let start = Task { try await coordinator.start() }
        await awaitCondition { speech.gates.first?.isWaiting == true }
        speech.gates[0].grant()
        await awaitCondition { mic.gates.first?.isWaiting == true }
        mic.gates[0].grant()
        do {
            try await start.value
            XCTFail("expected install failure")
        } catch let error as PermissionGate.TestError {
            XCTAssertEqual(error, .installFailed)
        } catch {
            XCTFail("expected install failure, got \(error)")
        }
        XCTAssertFalse(coordinator.hasPendingStart)
    }

    func testInvalidateWithoutPendingStartIsHarmlessAndNextStartWorks() async {
        let speech = GateQueue(), mic = GateQueue(), counter = InstallCounter()
        let coordinator = makeCoordinator(speech: speech, mic: mic, installCount: counter)
        coordinator.invalidatePendingStart()
        coordinator.invalidatePendingStart()
        let start = Task { try await coordinator.start() }
        await awaitCondition { speech.gates.first?.isWaiting == true }
        speech.gates[0].grant()
        await awaitCondition { mic.gates.first?.isWaiting == true }
        mic.gates[0].grant()
        try? await start.value
        XCTAssertEqual(counter.value, 1)
    }

    // MARK: transcript sink epochs

    func testStaleRecordingResultsNeverContaminateNextTranscript() {
        let sink = AskTranscriptSink()
        let first = sink.beginNewRecording()
        XCTAssertTrue(sink.accept("old words", isFinal: false, fromEpoch: first))
        let second = sink.beginNewRecording()
        XCTAssertFalse(sink.accept("old final", isFinal: true, fromEpoch: first))
        sink.markFinal(fromEpoch: first)
        XCTAssertEqual(sink.finish(), "", "stale epoch must not write into the new session")
        XCTAssertFalse(sink.didReceiveFinal, "stale final flag must not leak")
        XCTAssertTrue(sink.accept("new words", isFinal: true, fromEpoch: second))
        XCTAssertEqual(sink.finish(), "new words")
        XCTAssertTrue(sink.didReceiveFinal)
    }

    func testFinishTrimsWhitespace() {
        let sink = AskTranscriptSink()
        let epoch = sink.beginNewRecording()
        sink.accept("  hello there\n", isFinal: false, fromEpoch: epoch)
        XCTAssertEqual(sink.finish(), "hello there")
    }
}

final class AskCopyModeTests: XCTestCase {
    func testImageAndTextCarriesBothFlavorsWhenTextExists() {
        XCTAssertEqual(AskCopyMode.imageAndText.flavors(hasText: true), [.png, .text])
    }

    func testImageAndTextFallsBackToImageWhenQuestionIsEmpty() {
        XCTAssertEqual(AskCopyMode.imageAndText.flavors(hasText: false), [.png])
        let confirmation = AskCopyMode.imageAndText.confirmation(hasText: false)
        XCTAssertTrue(confirmation.contains("image only"))
        XCTAssertTrue(confirmation.contains("question is empty"))
        XCTAssertNotEqual(confirmation, AskCopyMode.imageOnly.confirmation(hasText: false))
    }

    func testTextOnlyWithEmptyQuestionCopiesNothing() {
        XCTAssertTrue(AskCopyMode.textOnly.flavors(hasText: false).isEmpty)
        XCTAssertEqual(AskCopyMode.textOnly.confirmation(hasText: false), "Nothing to copy: the question is empty.")
    }

    func testImageOnlyIgnoresText() {
        XCTAssertEqual(AskCopyMode.imageOnly.flavors(hasText: true), [.png])
    }
}

final class AskCopyRequestGateTests: XCTestCase {
    func testEditInvalidatesPendingEncodingEvenIfTextIsChangedBack() {
        var gate = AskCopyRequestGate()
        let pendingCopy = gate.begin()
        gate.invalidate()
        gate.invalidate()
        XCTAssertFalse(gate.isCurrent(pendingCopy))
    }

    func testSlowerOldCopyCannotOverwriteNewerCopyOrPublishOldStatus() {
        var gate = AskCopyRequestGate()
        let slowImageCopy = gate.begin()
        let newerTextCopy = gate.begin()
        XCTAssertTrue(gate.isCurrent(newerTextCopy))
        XCTAssertFalse(gate.isCurrent(slowImageCopy))
    }

    func testClosedOrReplacedPreviewInvalidatesPendingCopy() {
        var gate = AskCopyRequestGate()
        let pendingCopy = gate.begin()
        gate.invalidate()
        XCTAssertFalse(gate.isCurrent(pendingCopy))
        let freshPreviewCopy = gate.begin()
        XCTAssertTrue(gate.isCurrent(freshPreviewCopy))
    }
}

final class AskCopyOutcomeStateTests: XCTestCase {
    /// The reset semantics the capture-start, draft-publish and
    /// preview-close wiring all call. These cover the pure decision only;
    /// the AppKit wiring that calls reset() (window delegate, capture
    /// start) is verified on a Mac, not here.
    func testBeginCopyOwnsGateAndClearsOldConfirmation() {
        var outcome = AskCopyOutcomeState()
        let firstCopy = outcome.beginCopy()
        outcome.finishCopy(confirmation: "done")
        let secondCopy = outcome.beginCopy()
        XCTAssertTrue(outcome.isCurrent(secondCopy))
        XCTAssertFalse(outcome.isCurrent(firstCopy))
        XCTAssertNil(outcome.confirmation)
        XCTAssertTrue(outcome.hasOutcome)
    }

    func testResetInvalidatesPendingCopyAndClearsOutcome() {
        var outcome = AskCopyOutcomeState()
        let pendingCopy = outcome.beginCopy()
        outcome.markCopying()
        outcome.reset()
        XCTAssertFalse(outcome.isCurrent(pendingCopy),
                       "a copy pending at reset must never write or publish afterwards")
        XCTAssertFalse(outcome.isCopying)
        XCTAssertFalse(outcome.hasOutcome)
        XCTAssertNil(outcome.confirmation)
    }

    func testResetThenNewCopyPublishesOnlyNewGeneration() {
        var outcome = AskCopyOutcomeState()
        let staleCopy = outcome.beginCopy()
        outcome.reset()
        let freshCopy = outcome.beginCopy()
        XCTAssertFalse(outcome.isCurrent(staleCopy))
        XCTAssertTrue(outcome.isCurrent(freshCopy))
    }

    func testFinishCopyClearsCopyingFlagAndKeepsConfirmation() {
        var outcome = AskCopyOutcomeState()
        _ = outcome.beginCopy()
        outcome.markCopying()
        XCTAssertTrue(outcome.isCopying)
        outcome.finishCopy(confirmation: "copied")
        XCTAssertFalse(outcome.isCopying)
        XCTAssertEqual(outcome.confirmation, "copied")
        XCTAssertTrue(outcome.hasOutcome)
    }
}
