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
}
