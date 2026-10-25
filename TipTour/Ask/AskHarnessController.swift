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
    @Published var draftImage: NSImage? {
        didSet { invalidateCopyForPreviewEdit() }
    }
    @Published var draftText: String = "" {
        didSet {
            if draftText != oldValue { invalidateCopyForPreviewEdit() }
        }
    }
    @Published var targetBundleIdentifier: String = TipTourDefaults.askTargetBundleIdentifier
    @Published private(set) var targetApps: [AskTargetApp] = []
    @Published private(set) var insertionStatus: String?
    @Published private(set) var copyConfirmation: String?
    @Published private(set) var isInserting = false
    @Published private(set) var isCopying = false
    @Published private(set) var captureCaption: String = ""

    private weak var companionManager: CompanionManager?
    private let transcriber = OnDeviceSpeechTranscriber()
    private lazy var previewPanelManager = AskPreviewPanelManager(controller: self)

    /// State of the session in flight. Owned per session and moved out
    /// atomically at release, so a re-press can never overwrite it.
    private struct ActiveSession {
        let generation: Int
        let pressedAt: Date
        let trailPoints: [CGPoint]
        var capture: Task<CompanionScreenCGImageCapture, Error>
    }

    private var sessionGate = AskSessionGate()
    private var activeSession: ActiveSession?
    private var finishTask: Task<Void, Never>?
    private var insertionProgress = AskInsertionProgress()
    private var copyRequestGate = AskCopyRequestGate()
    private var hasCopyOutcome = false

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
        sessionGate.cancel()
        activeSession?.capture.cancel()
        activeSession = nil
        finishTask?.cancel()
        Task { [transcriber] in _ = await transcriber.stop() }
        isCapturing = false
    }

    private func beginCapture() {
        guard let companionManager else { return }
        guard sessionGate.phase == .idle else {
            if sessionGate.phase == .finishing {
                companionManager.presentAskHarnessHint("Still finishing the previous ask. Try again in a moment.")
            }
            return
        }

        guard companionManager.hasScreenRecordingPermission else {
            companionManager.presentAskHarnessHint("Screen recording permission is required for the ask screenshot.")
            return
        }

        if let readinessError = OnDeviceSpeechTranscriber.onDeviceReadinessError() {
            companionManager.presentAskHarnessHint(readinessError.errorDescription ?? "On-device speech recognition is unavailable.")
            return
        }

        guard let generation = sessionGate.begin() else { return }
        isCapturing = true
        insertionStatus = nil

        // Markings are strictly gesture-bound: only a highlight still in
        // flight, or one committed by this ask chord moments ago. Anything
        // older is not reused. The trail is not part of the capture itself
        // (ScreenCaptureKit excludes our windows); it is drawn afterwards.
        let trail = companionManager.currentScribbleTrail()
        let pressedAt = Date()

        activeSession = ActiveSession(
            generation: generation,
            pressedAt: pressedAt,
            trailPoints: trail ?? [],
            capture: Task {
                try await CompanionScreenCaptureUtility.captureCursorScreenAsCGImage(atNativePixelScale: true)
            }
        )

        Task { [weak self, transcriber] in
            do {
                let epoch = try await transcriber.start()
                await MainActor.run {
                    guard let self else { return }
                    // The session ended or was superseded while start was
                    // in flight: this recording has no owner, so tear it
                    // down - but only if it is still the current one. A
                    // newer session's recording (different epoch) must
                    // never be stopped here.
                    guard self.sessionGate.isCurrent(generation),
                          self.sessionGate.phase == .capturing else {
                        Task { [transcriber] in
                            _ = await transcriber.stopIfCurrent(epoch)
                        }
                        return
                    }
                }
            } catch {
                await MainActor.run {
                    guard let self else { return }
                    // stop()/cancel or a newer press superseded this start
                    // while it waited on a prompt: expected control flow,
                    // nothing to report.
                    if error is AskSpeechStartCoordinator.Supersession { return }
                    // A genuine failure (permission denied, recognizer
                    // gone, engine failed to start) is durable state: tell
                    // the user even if they already released, so the
                    // missing preview is explained instead of silent.
                    if self.sessionGate.isCurrent(generation),
                       self.sessionGate.phase == .capturing {
                        self.sessionGate.cancel()
                        self.isCapturing = false
                        self.activeSession?.capture.cancel()
                        self.activeSession = nil
                    }
                    self.companionManager?.presentAskHarnessHint(error.localizedDescription)
                }
            }
        }
    }

    private func finishCapture() {
        guard let generation = sessionGate.beginFinish(),
              let session = activeSession, session.generation == generation else { return }
        activeSession = nil

        finishTask = Task { [weak self, transcriber] in
            let transcript = await transcriber.stop()
            guard let self else { return }
            defer {
                self.sessionGate.finished()
                self.finishTask = nil
            }
            guard self.sessionGate.mayPublish(generation) else { return }
            self.isCapturing = false

            do {
                let capture = try await session.capture.value
                let capturedAt = Date()
                guard self.sessionGate.mayPublish(generation) else { return }

                let displayFrame = capture.displayFrame
                let onDisplayCount = session.trailPoints.filter {
                    displayFrame.insetBy(dx: -24, dy: -24).contains($0)
                }.count
                let decision = AskMarkingPolicy.decide(
                    pointCount: session.trailPoints.count,
                    pointsOnDisplayCount: onDisplayCount
                )

                var composited = capture.image
                if case .draw = decision {
                    let points = session.trailPoints
                    let baseImage = capture.image
                    // Compositing is CPU/GPU heavy; keep it off the main actor.
                    composited = await Task.detached(priority: .userInitiated) {
                        AskMarkingCompositor.compositingTrail(points, onto: baseImage, displayFrame: displayFrame)
                    }.value
                }
                guard self.sessionGate.mayPublish(generation) else { return }

                self.captureCaption = AskPreviewCaption.text(
                    completedTimeText: capturedAt.formatted(date: .omitted, time: .standard),
                    delaySeconds: capturedAt.timeIntervalSince(session.pressedAt),
                    decision: decision
                )
                self.insertionProgress = AskInsertionProgress()
                self.copyConfirmation = nil
                self.insertionStatus = nil
                self.draftImage = NSImage(
                    cgImage: composited,
                    size: NSSize(width: displayFrame.width, height: displayFrame.height)
                )
                self.draftText = transcript
                self.targetBundleIdentifier = TipTourDefaults.askTargetBundleIdentifier
                self.refreshTargetApps()
                self.previewPanelManager.show()
            } catch is CancellationError {
                return
            } catch {
                guard self.sessionGate.mayPublish(generation) else { return }
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
        if !configuredIdentifier.isEmpty, !targets.contains(where: { $0.bundleIdentifier == configuredIdentifier }) {
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

    private func invalidateCopyForPreviewEdit() {
        copyRequestGate.invalidate()
        if isCopying || hasCopyOutcome {
            insertionStatus = "The preview changed. Copy again to put the current image and question on the clipboard."
        }
        isCopying = false
        hasCopyOutcome = false
        copyConfirmation = nil
    }

    func copyToClipboard(_ mode: AskCopyMode) {
        guard !isInserting else {
            insertionStatus = "Wait for insertion to finish, then copy again."
            return
        }
        let generation = copyRequestGate.begin()
        hasCopyOutcome = true
        copyConfirmation = nil
        isCopying = false
        let text = draftText
        let hasText = !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        guard !mode.flavors(hasText: hasText).isEmpty else {
            insertionStatus = mode.confirmation(hasText: false)
            return
        }
        // Text-only must not depend on converting the preview image.
        let image = mode == .textOnly ? nil
            : draftImage?.cgImage(forProposedRect: nil, context: nil, hints: nil)
        guard mode == .textOnly || image != nil else {
            insertionStatus = AskDraftStagerError.copyImageUnavailable.localizedDescription
            return
        }
        isCopying = true
        insertionStatus = "Copying to clipboard..."
        Task { [weak self] in
            do {
                let message = try await AskClipboardHandoff.copy(
                    image: image, text: text, mode: mode,
                    isCurrent: { [weak self] in
                        self?.copyRequestGate.isCurrent(generation) == true
                    }
                )
                guard let self, self.copyRequestGate.isCurrent(generation) else { return }
                self.isCopying = false
                if mode == .imageAndText && !hasText {
                    self.insertionStatus = message
                } else {
                    self.copyConfirmation = message
                    self.insertionStatus = nil
                }
            } catch {
                guard let self, self.copyRequestGate.isCurrent(generation) else { return }
                self.isCopying = false
                self.copyConfirmation = nil
                self.insertionStatus = error.localizedDescription
            }
        }
    }

    func insertDraft() {
        guard !targetBundleIdentifier.isEmpty else {
            insertionStatus = "Pick an app to insert into, or use the copy buttons and paste yourself."
            return
        }
        guard !isInserting,
              let image = draftImage?.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }

        copyRequestGate.invalidate()
        isCopying = false
        hasCopyOutcome = false
        isInserting = true
        insertionStatus = nil
        copyConfirmation = nil
        let text = draftText
        let bundleIdentifier = targetBundleIdentifier
        persistTargetSelection()

        Task { [weak self] in
            do {
                var progress = self?.insertionProgress ?? AskInsertionProgress()
                defer { self?.insertionProgress = progress }
                let summary = try await AskDraftStager.insertDraft(
                    image: image,
                    text: text,
                    targetBundleIdentifier: bundleIdentifier,
                    progress: &progress
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
        copyConfirmation = nil
        captureCaption = ""
        insertionProgress = AskInsertionProgress()
    }
}
