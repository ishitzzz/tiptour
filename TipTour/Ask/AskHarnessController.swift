//
//  AskHarnessController.swift
//  TipTour
//
//  Orchestrates the ask harness: while the hotkey is held it captures the
//  cursor screen, composites the user's scribble onto it, and transcribes
//  the spoken question on-device; on release it opens the preview panel.
//  Insertion into the chosen app happens only from the preview, always as
//  a draft.
//

import AppKit
import Combine
import Foundation

struct AskTargetApp: Identifiable, Equatable {
    let bundleIdentifier: String
    let name: String
    let isInstalled: Bool

    var id: String { bundleIdentifier }
}

@MainActor
final class AskHarnessController: ObservableObject {
    @Published private(set) var isCapturing = false
    @Published var draftImage: NSImage?
    @Published var draftText: String = ""
    @Published var targetBundleIdentifier: String = TipTourDefaults.askTargetBundleIdentifier
    @Published private(set) var targetApps: [AskTargetApp] = []
    @Published private(set) var insertionStatus: String?
    @Published private(set) var isInserting = false
    @Published private(set) var capturedAt: Date?
    @Published private(set) var markingsCommittedAt: Date?

    private weak var companionManager: CompanionManager?
    private let transcriber = OnDeviceSpeechTranscriber()
    private lazy var previewPanelManager = AskPreviewPanelManager(controller: self)

    private var pendingCapture: Task<CompanionScreenCGImageCapture, Error>?
    private var pendingTrailPoints: [CGPoint] = []
    private var pendingMarkingsCommittedAt: Date?
    private var pendingCapturedAt: Date?
    private var sessionActive = false

    init(companionManager: CompanionManager) {
        self.companionManager = companionManager
    }

    func handleTransition(_ transition: AskHarnessShortcut.ShortcutTransition) {
        switch transition {
        case .pressed:
            beginCapture()
        case .released:
            finishCapture()
        case .none:
            break
        }
    }

    func cancelActiveCapture() {
        guard sessionActive else { return }
        sessionActive = false
        pendingCapture?.cancel()
        pendingCapture = nil
        Task { [transcriber] in _ = await transcriber.stop() }
        isCapturing = false
    }

    private func beginCapture() {
        guard let companionManager, !sessionActive else { return }

        guard companionManager.hasScreenRecordingPermission else {
            companionManager.presentAskHarnessHint("Screen recording permission is required for the ask screenshot.")
            return
        }

        if let readinessError = OnDeviceSpeechTranscriber.onDeviceReadinessError() {
            companionManager.presentAskHarnessHint(readinessError.errorDescription ?? "On-device speech recognition is unavailable.")
            return
        }

        sessionActive = true
        isCapturing = true
        insertionStatus = nil

        // Snapshot the scribble at the same gesture boundary as the
        // capture: adding Option while Ctrl+Shift is held commits the focus
        // highlight, and both this snapshot and the screenshot are taken at
        // that moment, so the markings always match the captured content.
        let trail = companionManager.currentScribbleTrail()
        pendingTrailPoints = trail?.points ?? []
        pendingMarkingsCommittedAt = trail?.committedAt
        pendingCapturedAt = Date()

        pendingCapture = Task {
            try await CompanionScreenCaptureUtility.captureCursorScreenAsCGImage()
        }

        Task { [weak self, transcriber] in
            do {
                try await transcriber.start()
            } catch {
                await MainActor.run {
                    guard let self, self.sessionActive else { return }
                    self.sessionActive = false
                    self.isCapturing = false
                    self.pendingCapture?.cancel()
                    self.pendingCapture = nil
                    self.companionManager?.presentAskHarnessHint(error.localizedDescription)
                }
            }
        }
    }

    private func finishCapture() {
        guard sessionActive else { return }
        sessionActive = false

        Task { [weak self, transcriber] in
            let transcript = await transcriber.stop()

            guard let self else { return }
            self.isCapturing = false

            do {
                guard let captureTask = self.pendingCapture else { return }
                self.pendingCapture = nil
                let capture = try await captureTask.value

                let composited = AskMarkingCompositor.compositingTrail(
                    self.pendingTrailPoints,
                    onto: capture.image,
                    displayFrame: capture.displayFrame
                )
                self.pendingTrailPoints = []

                self.capturedAt = self.pendingCapturedAt
                self.markingsCommittedAt = self.pendingMarkingsCommittedAt
                self.pendingCapturedAt = nil
                self.pendingMarkingsCommittedAt = nil
                self.draftImage = NSImage(
                    cgImage: composited,
                    size: NSSize(width: capture.displayFrame.width, height: capture.displayFrame.height)
                )
                self.draftText = transcript
                self.targetBundleIdentifier = TipTourDefaults.askTargetBundleIdentifier
                self.refreshTargetApps()
                self.previewPanelManager.show()
            } catch is CancellationError {
                return
            } catch {
                self.companionManager?.presentAskHarnessHint("Couldn't capture the screen: \(error.localizedDescription)")
            }
        }
    }

    private func refreshTargetApps() {
        var targets = NSWorkspace.shared.runningApplications
            .filter { application in
                application.activationPolicy == .regular
                    && application.bundleIdentifier != nil
                    && application.bundleIdentifier != Bundle.main.bundleIdentifier
            }
            .compactMap { application -> AskTargetApp? in
                guard let bundleIdentifier = application.bundleIdentifier else { return nil }
                return AskTargetApp(
                    bundleIdentifier: bundleIdentifier,
                    name: application.localizedName ?? bundleIdentifier,
                    isInstalled: true
                )
            }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }

        let configuredIdentifier = TipTourDefaults.askTargetBundleIdentifier
        if !targets.contains(where: { $0.bundleIdentifier == configuredIdentifier }) {
            let isInstalled = NSWorkspace.shared.urlForApplication(withBundleIdentifier: configuredIdentifier) != nil
            targets.insert(
                AskTargetApp(
                    bundleIdentifier: configuredIdentifier,
                    name: Self.displayName(forBundleIdentifier: configuredIdentifier),
                    isInstalled: isInstalled
                ),
                at: 0
            )
        }

        targetApps = targets
    }

    private static func displayName(forBundleIdentifier bundleIdentifier: String) -> String {
        if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleIdentifier),
           let bundle = Bundle(url: url),
           let name = bundle.object(forInfoDictionaryKey: "CFBundleName") as? String {
            return name
        }
        return bundleIdentifier
    }

    func persistTargetSelection() {
        TipTourDefaults.askTargetBundleIdentifier = targetBundleIdentifier
    }

    func insertDraft() {
        guard !isInserting,
              let image = draftImage?.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }

        isInserting = true
        insertionStatus = nil
        let text = draftText
        let bundleIdentifier = targetBundleIdentifier
        persistTargetSelection()

        Task { [weak self] in
            do {
                let summary = try await AskDraftStager.insertDraft(
                    image: image,
                    text: text,
                    targetBundleIdentifier: bundleIdentifier
                )
                guard let self else { return }
                self.isInserting = false
                self.previewPanelManager.hide()
                self.companionManager?.presentAskHarnessHint(summary)
            } catch {
                guard let self else { return }
                self.isInserting = false
                self.insertionStatus = error.localizedDescription
            }
        }
    }

    func cancelPreview() {
        previewPanelManager.hide()
        draftImage = nil
        draftText = ""
        insertionStatus = nil
        capturedAt = nil
        markingsCommittedAt = nil
    }
}
