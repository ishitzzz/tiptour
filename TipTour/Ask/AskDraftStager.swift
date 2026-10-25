//
//  AskDraftStager.swift
//  TipTour
//
//  Places the composited screenshot and the transcribed question into the
//  chosen app's composer as a DRAFT. It stages each piece on the general
//  pasteboard, pastes with a synthesized Cmd+V aimed at the target app's
//  pid, and never presses Return - sending is always the user's action.
//
//  Safety protocol:
//  - Paste only into a focused multi-line text area (AskComposerPolicy).
//    The exact focused window + element is captured once and must be the
//    same object before every paste; the app pid alone is not enough. If
//    the composer cannot be identified, nothing is pasted and the user is
//    asked to click into the message field themselves and retry.
//  - Clipboard ownership: the change count is captured right after each of
//    our writes (AskClipboardOwnership). Before each later write/paste it
//    must be unchanged; if the user copied something, the sequence stops
//    and the newer clipboard is never overwritten or pasted.
//  - Restore of the previous clipboard happens only while we still own it,
//    on success, failure and cancellation alike.
//  - Limits we cannot remove: we cannot observe when the target app has
//    consumed a paste. The waits below are heuristics, not guarantees, and
//    a slow app can miss a paste or read the clipboard after restore. The
//    result text says so. Universal Clipboard may sync staged contents.
//  - Retry: AskInsertionProgress records which pieces a paste was already
//    ATTEMPTED for (an attempt, not confirmed acceptance - the app may
//    have dropped it), so a retry never blindly pastes the same piece
//    twice. After any partial failure the user reviews the draft in the
//    target app and copies anything missing from the preview themselves.
//

import AppKit

enum AskDraftStagerError: LocalizedError {
    case accessibilityNotGranted
    case clipboardWriteFailed
    case copyRequestChanged
    case copyImageUnavailable
    case targetAppNotInstalled(bundleIdentifier: String)
    case targetAppDidNotBecomeFrontmost(bundleIdentifier: String)
    case composerNotFocused(appName: String)
    case composerRoleUnsupported(appName: String, role: String?)
    case focusLostDuringInsertion(appName: String)
    case imageEncodingFailed
    case clipboardChangedDuringInsertion(appName: String, pastedImage: Bool)

    var errorDescription: String? {
        switch self {
        case .accessibilityNotGranted:
            return "Accessibility permission is required to paste into another app. Grant it in System Settings > Privacy & Security > Accessibility."
        case .clipboardWriteFailed:
            return "macOS refused the clipboard write. The requested copy is not available; try again."
        case .copyRequestChanged:
            return "The preview changed while copying. Copy the current preview again."
        case .copyImageUnavailable:
            return "The marked image is unavailable. Capture again, or use Copy text for your question."
        case .targetAppNotInstalled(let bundleIdentifier):
            return "No installed app matches bundle identifier \(bundleIdentifier). Pick another target in the ask preview or in Settings."
        case .targetAppDidNotBecomeFrontmost(let bundleIdentifier):
            return "\(bundleIdentifier) did not come to the front, so nothing was pasted. The draft was not inserted."
        case .composerNotFocused(let appName):
            return "Couldn't find a focused message field in \(appName). Click into its message field yourself, then press Insert as draft again. Nothing was pasted."
        case .composerRoleUnsupported(let appName, let role):
            return "\(appName)'s focused field is not a multi-line text area (accessibility role: \(role ?? "unknown")), so TipTour will not paste into it. Clicking again cannot change the field's role: copy the draft from the preview yourself, or pick a different target app. Nothing was pasted."
        case .focusLostDuringInsertion(let appName):
            return "Focus moved in \(appName) after the image paste was attempted, so the question text was not pasted. Check the draft in \(appName): inserting again skips the image and only attempts the question."
        case .imageEncodingFailed:
            return "Could not encode the captured image for the clipboard."
        case .clipboardChangedDuringInsertion(let appName, let pastedImage):
            let state = pastedImage ? "The image paste was already attempted toward \(appName), and a retry will not attempt it again; check its draft to see whether it landed." : "Nothing was pasted."
            return "You copied something while the draft was being placed, so the insert stopped and your newer clipboard was kept. \(state)"
        }
    }
}

/// NSPasteboard-backed staging surface.
private final class GeneralPasteboardStaging: AskStagingPasteboard {
    private let pasteboard = NSPasteboard.general
    private let previousItems: [NSPasteboardItem]
    private let pngData: Data
    private let text: String

    init(pngData: Data, text: String) {
        self.pngData = pngData
        self.text = text
        self.previousItems = GeneralPasteboardStaging.copyItems(from: NSPasteboard.general)
    }

    var changeCount: Int { pasteboard.changeCount }

    func writeStaged(_ payload: AskStagedPayload) -> Int {
        let item = NSPasteboardItem()
        switch payload.kind {
        case .image: item.setData(pngData, forType: .png)
        case .text: item.setString(text, forType: .string)
        }
        pasteboard.clearContents()
        pasteboard.writeObjects([item])
        return pasteboard.changeCount
    }

    func restorePrevious() -> Int {
        pasteboard.clearContents()
        if !previousItems.isEmpty { pasteboard.writeObjects(previousItems) }
        return pasteboard.changeCount
    }

    fileprivate static func copyItems(from pasteboard: NSPasteboard) -> [NSPasteboardItem] {
        pasteboard.pasteboardItems?.map { item in
            let copiedItem = NSPasteboardItem()
            for type in item.types {
                if let data = item.data(forType: type) {
                    copiedItem.setData(data, forType: type)
                } else if let string = item.string(forType: type) {
                    copiedItem.setString(string, forType: type)
                }
            }
            return copiedItem
        } ?? []
    }
}

@MainActor
enum AskClipboardHandoff {
    /// Leaves the chosen content on the general pasteboard for the user to
    /// paste themselves. Successful copies are deliberately NOT restored:
    /// the copy has to stay available until the user pastes it.
    static func copy(
        image: CGImage?, text: String, mode: AskCopyMode,
        isCurrent: () -> Bool
    ) async throws -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let flavors = mode.flavors(hasText: !trimmed.isEmpty)
        guard !flavors.isEmpty else { return mode.confirmation(hasText: false) }

        var pngData: Data?
        if flavors.contains(.png) {
            guard let image else { throw AskDraftStagerError.copyImageUnavailable }
            pngData = try await Task.detached(priority: .userInitiated) {
                let bitmap = NSBitmapImageRep(cgImage: image)
                guard let data = bitmap.representation(using: .png, properties: [:]) else {
                    throw AskDraftStagerError.imageEncodingFailed
                }
                return data
            }.value
        }

        let item = NSPasteboardItem()
        if let pngData, !item.setData(pngData, forType: .png) {
            throw AskDraftStagerError.clipboardWriteFailed
        }
        if flavors.contains(.text), !item.setString(trimmed, forType: .string) {
            throw AskDraftStagerError.clipboardWriteFailed
        }
        // No suspension between the generation check and the write. A slower
        // old encoding cannot overwrite a newer copy or an edited question.
        guard isCurrent() else { throw AskDraftStagerError.copyRequestChanged }
        let pasteboard = NSPasteboard.general
        let previousItems = GeneralPasteboardStaging.copyItems(from: pasteboard)
        let clearedChangeCount = pasteboard.clearContents()
        guard pasteboard.writeObjects([item]) else {
            // Restore only the empty pasteboard we still own, not a third
            // party's newer copy. Successful copies deliberately stay put.
            if pasteboard.changeCount == clearedChangeCount, !previousItems.isEmpty {
                pasteboard.writeObjects(previousItems)
            }
            throw AskDraftStagerError.clipboardWriteFailed
        }
        return mode.confirmation(hasText: !trimmed.isEmpty)
    }
}

@MainActor
enum AskDraftStager {
    /// Heuristic waits (nanoseconds). The target app gives no completion
    /// signal, so these are best-effort and documented as such.
    private static let imageSettleNanoseconds: UInt64 = 800_000_000
    private static let restoreDelayNanoseconds: UInt64 = 1_500_000_000

    /// Inserts image then text into the target app's focused composer,
    /// skipping pieces `progress` says already went in. Returns a short
    /// human-readable summary including clipboard and timing caveats.
    static func insertDraft(
        image: CGImage,
        text: String,
        targetBundleIdentifier: String,
        progress: inout AskInsertionProgress
    ) async throws -> String {
        guard AXIsProcessTrusted() else {
            throw AskDraftStagerError.accessibilityNotGranted
        }
        progress.prepare(forTarget: targetBundleIdentifier)

        let targetApplication = try await resolvedFrontmostApplication(
            bundleIdentifier: targetBundleIdentifier
        )
        let appName = targetApplication.localizedName ?? targetBundleIdentifier
        let targetPID = targetApplication.processIdentifier

        let composerFocus: ComposerFocus
        switch ComposerFocus.capture(in: targetPID) {
        case .focused(let focus):
            composerFocus = focus
        case .unsupportedRole(let role, _):
            throw AskDraftStagerError.composerRoleUnsupported(appName: appName, role: role)
        case .noFocusedElement:
            throw AskDraftStagerError.composerNotFocused(appName: appName)
        }

        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let needsImage = !progress.imagePasted
        let needsText = !trimmedText.isEmpty && !progress.textPasted
        guard needsImage || needsText else {
            return "The image and question were already paste-attempted toward \(appName), so nothing was pasted again. Check the draft there and copy anything missing from this preview yourself. Nothing was sent."
        }

        // PNG encoding is CPU-heavy; keep it off the main actor.
        let pngData: Data = try await Task.detached(priority: .userInitiated) {
            let bitmap = NSBitmapImageRep(cgImage: image)
            guard let data = bitmap.representation(using: .png, properties: [:]) else {
                throw AskDraftStagerError.imageEncodingFailed
            }
            return data
        }.value

        let staging = GeneralPasteboardStaging(pngData: pngData, text: trimmedText)
        let ownership = AskClipboardOwnership(pasteboard: staging)

        func assertTargetStillFocused() throws {
            guard NSWorkspace.shared.frontmostApplication?.processIdentifier == targetPID,
                  composerFocus.isStillFocused() else {
                throw AskDraftStagerError.focusLostDuringInsertion(appName: appName)
            }
        }

        do {
            if needsImage {
                try assertTargetStillFocused()
                try ownership.stage(AskStagedPayload(kind: .image))
                try ownership.assertOwnedBeforePaste()
                postCommandV(to: targetPID)
                progress.imagePasted = true
                // Heuristic settle; see the limits in the file header.
                try await Task.sleep(nanoseconds: imageSettleNanoseconds)
            }

            if needsText {
                try assertTargetStillFocused()
                try ownership.stage(AskStagedPayload(kind: .text))
                try ownership.assertOwnedBeforePaste()
                postCommandV(to: targetPID)
                progress.textPasted = true
                // Give the target time to read the pasteboard before restore.
                try await Task.sleep(nanoseconds: restoreDelayNanoseconds)
            }
        } catch {
            // Failure or cancellation: put the user's clipboard back if it
            // is still ours, and never touch a newer copy.
            ownership.restoreIfStillOwned()
            if let clipboardError = error as? AskClipboardError, clipboardError == .clipboardChangedByOthers {
                print("[Ask] clipboard changed during staging; stopped without overwriting it")
                throw AskDraftStagerError.clipboardChangedDuringInsertion(appName: appName, pastedImage: progress.imagePasted)
            }
            throw error
        }

        let restored = ownership.restoreIfStillOwned()
        let clipboardNote = restored
            ? "Your previous clipboard was restored after a short delay."
            : "Your clipboard kept a newer copy instead of the previous contents."
        return "Paste attempted into \(appName): the image and question went to its composer, but TipTour can't confirm the app accepted them. Check the draft in \(appName) yourself before sending (images are app-dependent). \(clipboardNote) Nothing was sent."
    }

    /// Activates the target and verifies it actually came to the front;
    /// pasting into a different frontmost app would drop the screenshot and
    /// question into the wrong conversation, so that case fails closed.
    private static func resolvedFrontmostApplication(
        bundleIdentifier: String
    ) async throws -> NSRunningApplication {
        var application = NSWorkspace.shared.runningApplications.first {
            $0.bundleIdentifier == bundleIdentifier
        }

        if application == nil {
            guard let applicationURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleIdentifier) else {
                throw AskDraftStagerError.targetAppNotInstalled(bundleIdentifier: bundleIdentifier)
            }
            let configuration = NSWorkspace.OpenConfiguration()
            configuration.activates = false
            application = try await withCheckedThrowingContinuation { continuation in
                NSWorkspace.shared.openApplication(at: applicationURL, configuration: configuration) { launchedApplication, error in
                    if let launchedApplication {
                        continuation.resume(returning: launchedApplication)
                    } else {
                        continuation.resume(throwing: error ?? AskDraftStagerError.targetAppNotInstalled(bundleIdentifier: bundleIdentifier))
                    }
                }
            }
        }

        guard let application else {
            throw AskDraftStagerError.targetAppNotInstalled(bundleIdentifier: bundleIdentifier)
        }

        application.activate(options: [.activateAllWindows])
        for _ in 0..<30 {
            if NSWorkspace.shared.frontmostApplication?.bundleIdentifier == bundleIdentifier {
                // A short settle so the composer has keyboard focus before
                // the synthetic paste arrives.
                try await Task.sleep(nanoseconds: 400_000_000)
                return application
            }
            try await Task.sleep(nanoseconds: 100_000_000)
        }

        throw AskDraftStagerError.targetAppDidNotBecomeFrontmost(bundleIdentifier: bundleIdentifier)
    }

    private static func postCommandV(to processIdentifier: pid_t) {
        let source = CGEventSource(stateID: .hidSystemState)
        let vKeyCode: CGKeyCode = 9
        let keyDown = CGEvent(keyboardEventSource: source, virtualKey: vKeyCode, keyDown: true)
        keyDown?.flags = .maskCommand
        let keyUp = CGEvent(keyboardEventSource: source, virtualKey: vKeyCode, keyDown: false)
        keyUp?.flags = .maskCommand
        keyDown?.postToPid(processIdentifier)
        keyUp?.postToPid(processIdentifier)
    }
}

/// The exact focused window + element of a verified composer. Equality is
/// object identity as reported by Accessibility (CFEqual), so a different
/// field, tab or window in the same app does not pass.
@MainActor
private struct ComposerFocus {
    /// Why a composer capture succeeded or failed. The cases matter for the
    /// user message: clicking into the field and retrying can fix a missing
    /// focus, but it can never change a field's unsupported role.
    enum CaptureResult {
        case focused(ComposerFocus)
        case unsupportedRole(role: String?, subrole: String?)
        case noFocusedElement
    }

    let processIdentifier: pid_t
    let window: AXUIElement
    let element: AXUIElement

    static func capture(in processIdentifier: pid_t) -> CaptureResult {
        guard let (window, element) = currentFocus(in: processIdentifier) else {
            return .noFocusedElement
        }
        // An unreadable role (AX error/timeout) means we cannot confirm
        // what is focused at all: the retryable "click into the field"
        // advice applies, not the unsupported-role verdict.
        guard let role = stringAttribute(kAXRoleAttribute, of: element) else {
            return .noFocusedElement
        }
        let subrole = stringAttribute(kAXSubroleAttribute, of: element)
        guard AskComposerPolicy.isComposerRole(role: role, subrole: subrole) else {
            return .unsupportedRole(role: role, subrole: subrole)
        }
        return .focused(ComposerFocus(processIdentifier: processIdentifier, window: window, element: element))
    }

    func isStillFocused() -> Bool {
        guard let (currentWindow, currentElement) = Self.currentFocus(in: processIdentifier) else { return false }
        return CFEqual(currentWindow, window) && CFEqual(currentElement, element)
    }

    private static func currentFocus(in processIdentifier: pid_t) -> (AXUIElement, AXUIElement)? {
        let applicationElement = AXUIElementCreateApplication(processIdentifier)
        AXUIElementSetMessagingTimeout(applicationElement, 0.4)
        guard let element = elementAttribute(kAXFocusedUIElementAttribute, of: applicationElement),
              let window = elementAttribute(kAXFocusedWindowAttribute, of: applicationElement) else {
            return nil
        }
        return (window, element)
    }

    private static func elementAttribute(_ attribute: String, of element: AXUIElement) -> AXUIElement? {
        var value: AnyObject?
        guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success,
              let value, CFGetTypeID(value) == AXUIElementGetTypeID() else { return nil }
        return (value as! AXUIElement)
    }

    private static func stringAttribute(_ attribute: String, of element: AXUIElement) -> String? {
        var value: AnyObject?
        guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success else { return nil }
        return value as? String
    }
}
