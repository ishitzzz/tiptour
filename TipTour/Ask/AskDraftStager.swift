//
//  AskDraftStager.swift
//  TipTour
//
//  Places the composited screenshot and the transcribed question into the
//  chosen app's composer as a DRAFT. It stages each piece on the general
//  pasteboard, pastes with a synthesized Cmd+V aimed at the target app's
//  pid, and never presses Return — sending is always the user's action.
//
//  Pasting goes only into a verified editable composer: after the target
//  app is frontmost, its focused AX element must be a text-editing role,
//  and focus is re-verified before the second paste. Otherwise the image
//  or text could land in a search field, another conversation, or nowhere
//  editable — those cases fail closed and say what to do.
//
//  The user's prior clipboard contents are restored afterwards, but only
//  when the pasteboard's changeCount shows nothing else was copied while
//  the staging was in flight; clobbering a concurrent user copy is worse
//  than leaving the staged content behind. A skipped restore is logged
//  and surfaced in the returned summary.
//
//  The staged window is deliberately short because Universal Clipboard can
//  sync pasteboard contents to the user's other devices while staged.
//

import AppKit

enum AskDraftStagerError: LocalizedError {
    case accessibilityNotGranted
    case targetAppNotInstalled(bundleIdentifier: String)
    case targetAppDidNotBecomeFrontmost(bundleIdentifier: String)
    case composerNotEditable(appName: String)
    case focusLostDuringInsertion(appName: String)
    case imageEncodingFailed

    var errorDescription: String? {
        switch self {
        case .accessibilityNotGranted:
            return "Accessibility permission is required to paste into another app. Grant it in System Settings > Privacy & Security > Accessibility."
        case .targetAppNotInstalled(let bundleIdentifier):
            return "No installed app matches bundle identifier \(bundleIdentifier). Pick another target in the ask preview or in Settings."
        case .targetAppDidNotBecomeFrontmost(let bundleIdentifier):
            return "\(bundleIdentifier) did not come to the front, so nothing was pasted. The draft was not inserted."
        case .composerNotEditable(let appName):
            return "Couldn't confirm an editable composer is focused in \(appName). Click into its message field, then press Insert as draft again."
        case .focusLostDuringInsertion(let appName):
            return "Focus moved in \(appName) after the image was placed, so the question text was not pasted. Check the app before trying again."
        case .imageEncodingFailed:
            return "Could not encode the captured image for the clipboard."
        }
    }
}

@MainActor
enum AskDraftStager {
    /// Inserts image then text into the target app's focused composer.
    /// Returns a short human-readable summary including any clipboard
    /// restore caveat.
    static func insertDraft(
        image: CGImage,
        text: String,
        targetBundleIdentifier: String
    ) async throws -> String {
        guard AXIsProcessTrusted() else {
            throw AskDraftStagerError.accessibilityNotGranted
        }

        let targetApplication = try await resolvedFrontmostApplication(
            bundleIdentifier: targetBundleIdentifier
        )
        let appName = targetApplication.localizedName ?? targetBundleIdentifier

        guard isEditableComposerFocused(in: targetApplication.processIdentifier) else {
            throw AskDraftStagerError.composerNotEditable(appName: appName)
        }

        let pasteboard = NSPasteboard.general
        let previousItems = copyPasteboardItems(from: pasteboard)

        guard let bitmap = NSBitmapImageRep(cgImage: image),
              let pngData = bitmap.representation(using: .png, properties: [:]) else {
            throw AskDraftStagerError.imageEncodingFailed
        }

        let imageItem = NSPasteboardItem()
        imageItem.setData(pngData, forType: .png)
        pasteboard.clearContents()
        pasteboard.writeObjects([imageItem])
        postCommandV(to: targetApplication.processIdentifier)
        // Attachment handling in the target is asynchronous; give it time
        // before the text paste so the two don't interleave.
        try await Task.sleep(nanoseconds: 600_000_000)

        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmedText.isEmpty {
            guard NSWorkspace.shared.frontmostApplication?.processIdentifier == targetApplication.processIdentifier,
                  isEditableComposerFocused(in: targetApplication.processIdentifier) else {
                throw AskDraftStagerError.focusLostDuringInsertion(appName: appName)
            }
            let textItem = NSPasteboardItem()
            textItem.setString(trimmedText, forType: .string)
            pasteboard.clearContents()
            pasteboard.writeObjects([textItem])
            postCommandV(to: targetApplication.processIdentifier)
            try await Task.sleep(nanoseconds: 400_000_000)
        }

        let stagedChangeCount = pasteboard.changeCount
        if pasteboard.changeCount == stagedChangeCount {
            restorePasteboard(pasteboard, items: previousItems)
            return "Draft placed in \(appName). Review it there — nothing was sent."
        }

        print("[Ask] pasteboard changed during staging; leaving the user's clipboard as-is")
        return "Draft placed in \(appName). Your clipboard kept its newest copy instead of the previous contents. Nothing was sent."
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

    /// The focused element in the target must be a text-editing role for a
    /// composer paste to be safe. Electron apps expose their AX tree only
    /// after AXManualAccessibility is set, which app-activation tracking in
    /// CompanionManager already applies; when the tree stays unreadable
    /// this returns false and the insert fails closed.
    private static func isEditableComposerFocused(in processIdentifier: pid_t) -> Bool {
        let applicationElement = AXUIElementCreateApplication(processIdentifier)
        AXUIElementSetMessagingTimeout(applicationElement, 0.4)

        var focusedValue: AnyObject?
        guard AXUIElementCopyAttributeValue(
            applicationElement,
            kAXFocusedUIElementAttribute as CFString,
            &focusedValue
        ) == .success, let focusedValue, CFGetTypeID(focusedValue) == AXUIElementGetTypeID() else {
            return false
        }

        let focusedElement = focusedValue as! AXUIElement
        var roleValue: AnyObject?
        guard AXUIElementCopyAttributeValue(
            focusedElement,
            kAXRoleAttribute as CFString,
            &roleValue
        ) == .success, let role = roleValue as? String else {
            return false
        }

        let editableRoles: Set<String> = [
            kAXTextAreaRole,
            kAXTextFieldRole,
            kAXComboBoxRole,
            "AXSearchField"
        ]
        return editableRoles.contains(role)
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

    private static func copyPasteboardItems(from pasteboard: NSPasteboard) -> [NSPasteboardItem] {
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

    private static func restorePasteboard(_ pasteboard: NSPasteboard, items: [NSPasteboardItem]) {
        pasteboard.clearContents()
        guard !items.isEmpty else { return }
        pasteboard.writeObjects(items)
    }
}
