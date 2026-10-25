//
//  AskHarnessCore.swift
//  TipTour
//
//  Foundation-only decision logic for the ask harness, kept free of AppKit
//  so scripts/test-ask.sh can unit-test it on any Swift toolchain (including
//  Linux). The AppKit code feeds these types real events; the types decide.
//

import Foundation

// MARK: - Hotkey provenance

/// Which modifier combination a raw CGEventFlags value represents. Read from
/// the event that caused a transition, so the answer does not depend on the
/// order in which two independent event taps deliver their callbacks.
enum AskGestureProvenance {
    static let shiftMask: UInt64 = 0x0002_0000
    static let controlMask: UInt64 = 0x0004_0000
    static let optionMask: UInt64 = 0x0008_0000
    static let commandMask: UInt64 = 0x0010_0000

    /// True when Ctrl+Option+Shift are all held and Command is not: the ask
    /// harness chord. A focus highlight that ends while this is true was
    /// committed BY the ask gesture and must stay local.
    static func isAskChord(flagsRawValue: UInt64) -> Bool {
        flagsRawValue & controlMask != 0
            && flagsRawValue & optionMask != 0
            && flagsRawValue & shiftMask != 0
            && flagsRawValue & commandMask == 0
    }
}

// MARK: - Session phases and generations

/// Capture session lifecycle with a generation counter. Every asynchronous
/// continuation records the generation it started under and may publish
/// results only while it is still current, so a stale finish can never
/// overwrite a newer session's preview. A new session cannot begin while a
/// previous one is still finishing (the transcriber is shared).
struct AskSessionGate: Equatable {
    enum Phase: Equatable { case idle, capturing, finishing }

    private(set) var phase: Phase = .idle
    private(set) var generation: Int = 0

    /// Starts a session. Returns its generation, or nil if one is running or finishing.
    mutating func begin() -> Int? {
        guard phase == .idle else { return nil }
        generation += 1
        phase = .capturing
        return generation
    }

    /// Moves capturing -> finishing. Returns the generation, or nil if not capturing.
    mutating func beginFinish() -> Int? {
        guard phase == .capturing else { return nil }
        phase = .finishing
        return generation
    }

    /// Invalidates the current session. A finishing session stays in
    /// `finishing` until its task calls `finished`, so no new session
    /// starts while the old task still holds the transcriber.
    mutating func cancel() {
        generation += 1
        if phase == .capturing { phase = .idle }
    }

    /// Called by the finishing task when it ends, whatever the outcome.
    mutating func finished() {
        if phase == .finishing { phase = .idle }
    }

    func isCurrent(_ candidate: Int) -> Bool { candidate == generation }
    func mayPublish(_ candidate: Int) -> Bool { candidate == generation && phase == .finishing }
}

// MARK: - Clipboard ownership

struct AskStagedPayload: Equatable {
    enum Kind: Equatable { case image, text }
    let kind: Kind
}

/// What the stager needs from a pasteboard. NSPasteboard is wrapped by one
/// conformer; tests use a fake that can simulate a concurrent user copy.
protocol AskStagingPasteboard: AnyObject {
    var changeCount: Int { get }
    /// Replaces the contents with the payload and returns the new change count.
    func writeStaged(_ payload: AskStagedPayload) -> Int
    /// Puts the user's previous contents back and returns the new change count.
    func restorePrevious() -> Int
}

enum AskClipboardError: Error, Equatable {
    /// Something else wrote to the clipboard after our last write.
    case clipboardChangedByOthers
}

/// Tracks the change count produced by OUR most recent write. The count is
/// captured immediately after each write; before the next write or paste
/// the live count must still equal it, otherwise the user (or an app)
/// copied something and we must not overwrite or paste over it.
final class AskClipboardOwnership<Pasteboard: AskStagingPasteboard> {
    private let pasteboard: Pasteboard
    private(set) var ownedChangeCount: Int?

    init(pasteboard: Pasteboard) {
        self.pasteboard = pasteboard
    }

    var isStillOwned: Bool {
        guard let ownedChangeCount else { return true }
        return pasteboard.changeCount == ownedChangeCount
    }

    /// Writes a payload unless the clipboard changed since our last write.
    func stage(_ payload: AskStagedPayload) throws {
        guard isStillOwned else { throw AskClipboardError.clipboardChangedByOthers }
        ownedChangeCount = pasteboard.writeStaged(payload)
    }

    /// Throws if someone else copied since our last write; call right
    /// before synthesizing a paste so a newer clipboard is never pasted.
    func assertOwnedBeforePaste() throws {
        guard isStillOwned else { throw AskClipboardError.clipboardChangedByOthers }
    }

    /// Restores the user's previous contents only if we still own the
    /// clipboard. Returns whether a restore happened. Never overwrites a
    /// newer copy.
    @discardableResult
    func restoreIfStillOwned() -> Bool {
        guard ownedChangeCount != nil, isStillOwned else { return false }
        ownedChangeCount = pasteboard.restorePrevious()
        return true
    }
}

// MARK: - Insertion progress (retry without blind duplicate paste)

/// Which pieces of the current draft were already pasted into the target.
/// A retry after a partial failure skips what already went in, instead of
/// blindly pasting the image (or text) a second time.
struct AskInsertionProgress: Equatable {
    var imagePasted = false
    var textPasted = false
    var targetBundleIdentifier: String?

    /// A different target is a fresh insertion, so progress resets.
    mutating func prepare(forTarget bundleIdentifier: String) {
        if targetBundleIdentifier != bundleIdentifier {
            self = AskInsertionProgress(targetBundleIdentifier: bundleIdentifier)
        }
    }

    var hasAnyPaste: Bool { imagePasted || textPasted }
}

// MARK: - Composer policy

enum AskComposerPolicy {
    /// Only multi-line text areas count as a message composer. Single-line
    /// text fields, combo boxes and search fields are excluded: they are
    /// where a stray paste does the most harm (search boxes, address bars,
    /// rename fields).
    static func isComposerRole(role: String?, subrole: String?) -> Bool {
        guard role == "AXTextArea" else { return false }
        if subrole == "AXSearchField" { return false }
        return true
    }
}

// MARK: - Markings policy

enum AskMarkingDecision: Equatable {
    case none
    case draw(count: Int)
    case rejectedOffDisplay
}

enum AskMarkingPolicy {
    /// All-or-nothing: markings are drawn only when every point lies on
    /// the captured display (small edge tolerance). A scribble that
    /// partly or wholly sits on another display cannot be shown honestly
    /// on this screenshot, so it is rejected and the preview says so.
    static func decide(
        pointCount: Int,
        pointsOnDisplayCount: Int
    ) -> AskMarkingDecision {
        guard pointCount >= 2 else { return .none }
        return pointsOnDisplayCount == pointCount ? .draw(count: pointCount) : .rejectedOffDisplay
    }
}

// MARK: - Capture sizing

enum AskCaptureSizing {
    /// Pixel size for a capture of a display of `pointWidth` x `pointHeight`
    /// at the display's verified backing scale. Never below 1x.
    static func pixelSize(
        pointWidth: Double,
        pointHeight: Double,
        scale: Double
    ) -> (width: Int, height: Int) {
        let safeScale = scale.isFinite && scale >= 1 ? scale : 1
        return (Int((pointWidth * safeScale).rounded()), Int((pointHeight * safeScale).rounded()))
    }
}

// MARK: - Preview captions

enum AskPreviewCaption {
    /// What the preview says about timing and markings. `requestedAt` is
    /// the hotkey press; `completedAt` is when the image actually came back
    /// from ScreenCaptureKit. The screen may have changed in between.
    static func text(
        completedTimeText: String,
        delaySeconds: Double,
        decision: AskMarkingDecision
    ) -> String {
        var parts = ["Screen captured at \(completedTimeText), about \(String(format: "%.1f", max(0, delaySeconds)))s after you pressed the hotkey; the screen may have changed in that gap."]
        switch decision {
        case .none:
            parts.append("No markings.")
        case .draw:
            parts.append("Your highlight from this gesture is drawn on top. It is composited after capture, so it shows where you drew, not necessarily what was under it at that moment.")
        case .rejectedOffDisplay:
            parts.append("Markings were not drawn: your scribble was not entirely on the captured display.")
        }
        return parts.joined(separator: " ")
    }
}
