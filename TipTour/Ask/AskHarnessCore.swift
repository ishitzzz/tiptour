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

// MARK: - Clipboard handoff (copy only, any target app)

/// What a copy-to-clipboard action puts on the pasteboard. `.imageAndText` writes
/// one pasteboard item carrying PNG and text flavors; which flavor an app
/// reads is the app's choice, so image-only and text-only exist as exact
/// alternatives.
enum AskCopyMode: Equatable {
    case imageAndText, imageOnly, textOnly

    enum Flavor: Equatable { case png, text }

    func flavors(hasText: Bool) -> [Flavor] {
        switch self {
        case .imageAndText: return hasText ? [.png, .text] : [.png]
        case .imageOnly: return [.png]
        case .textOnly: return hasText ? [.text] : []
        }
    }

    func confirmation(hasText: Bool) -> String {
        switch flavors(hasText: hasText) {
        case [.png, .text]:
            return "Copied the marked image and your question together. Paste where you like. If the app only takes one of them, use Copy image or Copy text. Your clipboard now holds this copy."
        case [.png]:
            if self == .imageAndText {
                return "Copied the marked image only: your question is empty. Add a question and copy again to include it. Your clipboard now holds the image."
            }
            return "Copied the marked image. Paste where you like. Your clipboard now holds it."
        case [.text]:
            return "Copied your question. Paste where you like. Your clipboard now holds it."
        default:
            return "Nothing to copy: the question is empty."
        }
    }
}

/// A copy may encode an image off the main actor. Only the latest request
/// for the unchanged preview may write the clipboard or publish a result.
struct AskCopyRequestGate {
    private(set) var generation = 0

    mutating func begin() -> Int {
        generation += 1
        return generation
    }

    mutating func invalidate() { generation += 1 }
    func isCurrent(_ candidate: Int) -> Bool { candidate == generation }
}

// MARK: - Insertion progress (retry without blind duplicate paste)

/// Which pieces of the current draft a paste was already ATTEMPTED for in
/// the target. An attempt is not acceptance: the target app may have
/// dropped the paste, and TipTour cannot observe that. User-facing text
/// must never describe these flags as confirmed placement. A retry after a
/// partial failure skips pieces already attempted (no blind duplicates);
/// the user reviews the draft in the target app and copies anything
/// missing from the preview themselves.
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


// MARK: - Speech recording lifecycle

/// Orders a single push-to-talk recording start against stop()/cancel and
/// later starts. The problem it solves: starting speech recognition
/// suspends on the Speech and microphone permission prompts, and a release
/// or cancel (stop) - or a newer press (another start) - can land while
/// the start is still suspended. Without an intent generation, the late
/// start would resume and install a live microphone engine after its
/// session already ended, unowned; a following start could then leak a
/// second engine.
///
/// Every stage revalidates the start intent after each await, and once
/// more immediately before install, so a superseded start never records.
/// Confined to one serial context (the transcriber's MainActor in
/// production; tests drive it one suspension at a time).
final class AskSpeechStartCoordinator {
    /// A stop/cancel or a newer start invalidated this start while it was
    /// suspended on a permission prompt. Expected control flow: callers
    /// must not surface it to the user.
    enum Supersession: Error {
        case superseded
    }

    /// Throwing marks denial/failure with the caller's own domain error,
    /// which propagates even when the start was meanwhile superseded:
    /// a denied permission is durable state the user must hear about.
    private let requestSpeechPermission: () async throws -> Void
    private let requestMicrophonePermission: () async throws -> Void
    private let installRecording: () throws -> Void

    private var intentVersion = 0
    /// True while the current start is between entry and a finished install.
    private(set) var hasPendingStart = false

    init(
        requestSpeechPermission: @escaping () async throws -> Void,
        requestMicrophonePermission: @escaping () async throws -> Void,
        installRecording: @escaping () throws -> Void
    ) {
        self.requestSpeechPermission = requestSpeechPermission
        self.requestMicrophonePermission = requestMicrophonePermission
        self.installRecording = installRecording
    }

    func start() async throws {
        intentVersion &+= 1
        let intent = intentVersion
        hasPendingStart = true

        do {
            try await requestSpeechPermission()
        } catch {
            clearPending(intent)
            throw error
        }
        try validate(intent)

        do {
            try await requestMicrophonePermission()
        } catch {
            clearPending(intent)
            throw error
        }

        // Final gate, immediately before install: no recording may begin
        // after stop()/cancel or after a newer start took over. There is
        // no suspension point between this check and installRecording().
        try validate(intent)

        do {
            try installRecording()
        } catch {
            clearPending(intent)
            throw error
        }
        clearPending(intent)
    }

    /// stop()/cancel: kills any start still waiting on a permission prompt,
    /// so it can never install audio afterwards. Idempotent: harmless when
    /// nothing is pending or when called repeatedly.
    func invalidatePendingStart() {
        intentVersion &+= 1
        hasPendingStart = false
    }

    private func validate(_ intent: Int) throws {
        guard intent == intentVersion else {
            throw Supersession.superseded
        }
    }

    private func clearPending(_ intent: Int) {
        if intent == intentVersion { hasPendingStart = false }
    }
}

// MARK: - Epoch-keyed transcript sink

/// Holds the latest transcript for the current recording epoch. Results
/// from a superseded recording are dropped instead of contaminating the
/// next session's transcript: recognition callbacks arrive asynchronously
/// and can outlive the stop() that cancelled their task.
final class AskTranscriptSink {
    private(set) var epoch = 0
    private(set) var latest = ""
    private(set) var didReceiveFinal = false

    /// Starts a new recording epoch and clears prior state. Returns the
    /// epoch the new recording's callbacks must present.
    @discardableResult
    func beginNewRecording() -> Int {
        epoch &+= 1
        latest = ""
        didReceiveFinal = false
        return epoch
    }

    /// Accepts a transcript update only from the current epoch.
    @discardableResult
    func accept(_ text: String, isFinal: Bool, fromEpoch candidate: Int) -> Bool {
        guard candidate == epoch else { return false }
        latest = text
        if isFinal { didReceiveFinal = true }
        return true
    }

    /// Marks the stream finished (e.g. recognition ended with an error),
    /// but only from the current epoch.
    func markFinal(fromEpoch candidate: Int) {
        guard candidate == epoch else { return }
        didReceiveFinal = true
    }

    /// The transcript to publish, trimmed.
    func finish() -> String {
        latest.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
