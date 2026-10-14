//
//  TutorialTourPlayer.swift
//  TipTour
//
//  Walks the user through a saved tutorial tour on their own screen. For
//  each step it finds the target, flies the pointer there, and waits for
//  the user to do the step. There are no Next buttons: a step moves on
//  when the user clicks the target, types, presses the shortcut, or
//  scrolls; read-only steps move on after a reading pause. Escape stops.
//
//  Finding a target uses TipTour's own grounding first (accessibility
//  tree, browser DOM, local detection) by the step's label. Only when that
//  misses, and Remote Screenshots is on, does Elorian point at it on a
//  screenshot, with the crop cut from the tutorial video as a reference.
//  The user does every action; the player never clicks.
//

import AppKit
import Foundation

/// What the tour card and the menu bar panel show while a tour plays.
struct TutorialTourPlaybackState: Equatable {
    let tour: TutorialTour
    let currentStepIndex: Int
    let targetStatusText: String

    var currentStep: TutorialTourStep { tour.steps[currentStepIndex] }
}

/// The pieces of CompanionManager the player needs, passed as closures so
/// the player never reaches into overlay internals.
struct TutorialTourPointerControls {
    let showOverlayIfNeeded: () -> Void
    let pointAtScreenLocation: (_ globalScreenPoint: CGPoint, _ displayFrame: CGRect, _ bubbleText: String) -> Void
    let clearPointer: () -> Void
    let setPointerHeldOnTarget: (Bool) -> Void
    let areRemoteScreenshotsAllowed: () -> Bool
}

@MainActor
final class TutorialTourPlayer {

    var onPlaybackStateChange: ((TutorialTourPlaybackState?) -> Void)?

    private let pointerControls: TutorialTourPointerControls
    private let tourCardPanelController = TutorialTourCardPanelController()

    private var playingTour: TutorialTour?
    private var currentStepIndex = 0
    private var currentTargetResolution: ElementResolver.Resolution?
    private var isWaitingForUserToDoStep = false
    private var clicksAwayFromTargetCount = 0
    private var typedCharacterCount = 0
    private var dragStartLocation: CGPoint?

    private var globalEventMonitor: Any?
    private var localEventMonitor: Any?
    private var targetLocatingTask: Task<Void, Never>?
    private var pendingStepCompletionTask: Task<Void, Never>?
    private var idleCompletionTask: Task<Void, Never>?

    init(pointerControls: TutorialTourPointerControls) {
        self.pointerControls = pointerControls
    }

    var isPlaying: Bool { playingTour != nil }

    func play(_ tour: TutorialTour) {
        stop()
        guard !tour.steps.isEmpty else { return }
        playingTour = tour
        currentStepIndex = 0
        pointerControls.showOverlayIfNeeded()
        pointerControls.setPointerHeldOnTarget(true)
        installEventMonitors()
        beginCurrentStep()
    }

    func stop() {
        guard playingTour != nil else { return }
        targetLocatingTask?.cancel()
        pendingStepCompletionTask?.cancel()
        idleCompletionTask?.cancel()
        removeEventMonitors()
        playingTour = nil
        currentTargetResolution = nil
        isWaitingForUserToDoStep = false
        pointerControls.setPointerHeldOnTarget(false)
        pointerControls.clearPointer()
        tourCardPanelController.hide()
        onPlaybackStateChange?(nil)
    }

    // MARK: - Steps

    private func beginCurrentStep() {
        guard let playingTour, playingTour.steps.indices.contains(currentStepIndex) else { return }
        let currentStep = playingTour.steps[currentStepIndex]

        currentTargetResolution = nil
        clicksAwayFromTargetCount = 0
        typedCharacterCount = 0
        dragStartLocation = nil
        isWaitingForUserToDoStep = true
        idleCompletionTask?.cancel()

        if currentStep.action.needsPointerTarget {
            publishState(targetStatusText: "Finding it on your screen…")
            locateAndPointAtCurrentTarget()
        } else {
            publishState(targetStatusText: Self.waitingHint(for: currentStep))
            if currentStep.action == .wait {
                completeCurrentStep(afterSeconds: Self.readingPauseSeconds(for: currentStep))
            }
        }
    }

    private func locateAndPointAtCurrentTarget() {
        guard let playingTour else { return }
        let stepIndexBeingLocated = currentStepIndex
        let currentStep = playingTour.steps[stepIndexBeingLocated]
        targetLocatingTask?.cancel()
        targetLocatingTask = Task { [weak self] in
            guard let self else { return }
            let locatedTarget = await self.locateTarget(for: currentStep, in: playingTour)
            guard !Task.isCancelled,
                  self.playingTour?.id == playingTour.id,
                  self.currentStepIndex == stepIndexBeingLocated,
                  self.isWaitingForUserToDoStep else { return }

            if let (targetResolution, statusText) = locatedTarget {
                self.currentTargetResolution = targetResolution
                self.pointerControls.pointAtScreenLocation(
                    targetResolution.globalScreenPoint,
                    targetResolution.displayFrame,
                    self.pointerBubbleText(for: currentStep, in: playingTour)
                )
                self.publishState(targetStatusText: statusText)
            } else {
                self.publishState(targetStatusText: "Couldn't spot it on your screen. Look for it, then do the step.")
            }
        }
    }

    /// Returns the resolved target and a short status line, or nil.
    private func locateTarget(
        for tutorialTourStep: TutorialTourStep,
        in tour: TutorialTour
    ) async -> (ElementResolver.Resolution, String)? {
        // 1. TipTour's own grounding by label: accessibility tree, browser
        //    DOM, local detection. Fast, exact, and nothing leaves the Mac.
        if !tutorialTourStep.targetLabel.isEmpty,
           let localResolution = await ElementResolver.shared.resolve(
               label: tutorialTourStep.targetLabel,
               llmHintInScreenshotPixels: nil,
               latestCapture: nil
           ) {
            return (localResolution, "Found it on your screen.")
        }

        // 2. Elorian on a screenshot, only when the user allows remote
        //    screenshots and has an Elorian key.
        guard pointerControls.areRemoteScreenshotsAllowed(),
              !(KeychainStore.elorianAPIKey ?? "").isEmpty,
              let screenCaptures = try? await CompanionScreenCaptureUtility.captureAllScreensAsJPEG(),
              let cursorScreenCapture = screenCaptures.first(where: { $0.isCursorScreen }) ?? screenCaptures.first,
              let squareScreenshotJPEGData = Self.squareJPEGData(from: cursorScreenCapture.imageData, sideInPixels: Self.pointingImageSideInPixels) else {
            return nil
        }
        guard let pointResult = try? await ElorianClient.shared.locateTarget(
            squareScreenshotJPEGData: squareScreenshotJPEGData,
            squareImageSideInPixels: Self.pointingImageSideInPixels,
            referenceCropPNGData: TutorialTourLibrary.targetCropPNGData(for: tutorialTourStep, in: tour),
            targetLabel: tutorialTourStep.targetLabel,
            targetDescription: tutorialTourStep.targetDescription
        ), let pointInSquareImage = pointResult.pointInSentImagePixels else {
            return nil
        }

        let side = Double(Self.pointingImageSideInPixels)
        let pointInScreenshotPixels = CGPoint(
            x: pointInSquareImage.x / side * Double(cursorScreenCapture.screenshotWidthInPixels),
            y: pointInSquareImage.y / side * Double(cursorScreenCapture.screenshotHeightInPixels)
        )
        let statusText = "Elorian found it in \(String(format: "%.1f", Double(pointResult.milliseconds) / 1000)) s."

        // Let local detection snap Elorian's point onto the real control
        // when it can; otherwise trust the point as-is.
        if !tutorialTourStep.targetLabel.isEmpty,
           let refinedResolution = await ElementResolver.shared.resolve(
               label: tutorialTourStep.targetLabel,
               llmHintInScreenshotPixels: pointInScreenshotPixels,
               latestCapture: cursorScreenCapture
           ) {
            return (refinedResolution, statusText)
        }
        let rawResolution = ElementResolver.shared.rawLLMCoordinate(
            label: tutorialTourStep.targetLabel.isEmpty ? tutorialTourStep.targetDescription : tutorialTourStep.targetLabel,
            llmHintInScreenshotPixels: pointInScreenshotPixels,
            capture: cursorScreenCapture
        )
        return (rawResolution, statusText)
    }

    private func completeCurrentStep(afterSeconds settleSeconds: Double) {
        guard isWaitingForUserToDoStep else { return }
        isWaitingForUserToDoStep = false
        targetLocatingTask?.cancel()
        idleCompletionTask?.cancel()
        pendingStepCompletionTask?.cancel()
        let completedStepIndex = currentStepIndex

        // Wait for menus and panels opened by the step to settle before
        // grounding the next target on the changed screen.
        pendingStepCompletionTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(settleSeconds * 1_000_000_000))
            guard let self, !Task.isCancelled, let playingTour = self.playingTour,
                  self.currentStepIndex == completedStepIndex else { return }
            self.pointerControls.clearPointer()
            if completedStepIndex + 1 < playingTour.steps.count {
                self.currentStepIndex = completedStepIndex + 1
                self.beginCurrentStep()
            } else {
                self.finishTour()
            }
        }
    }

    private func finishTour() {
        guard let playingTour else { return }
        tourCardPanelController.showFinished(tour: playingTour)
        removeEventMonitors()
        self.playingTour = nil
        pointerControls.setPointerHeldOnTarget(false)
        pointerControls.clearPointer()
        onPlaybackStateChange?(nil)
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard let self, self.playingTour == nil else { return }
            self.tourCardPanelController.hide()
        }
    }

    // MARK: - Watching the user do the step

    private func installEventMonitors() {
        removeEventMonitors()
        let watchedEventTypes: NSEvent.EventTypeMask = [.leftMouseDown, .rightMouseDown, .leftMouseUp, .keyDown, .scrollWheel]
        // Global monitors see events sent to other apps (the tutorial's app).
        globalEventMonitor = NSEvent.addGlobalMonitorForEvents(matching: watchedEventTypes) { [weak self] event in
            self?.handleUserEvent(event)
        }
        // A local monitor catches Escape while a TipTour window is focused.
        localEventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown]) { [weak self] event in
            if event.keyCode == Self.escapeKeyCode, self?.isPlaying == true {
                self?.stop()
                return nil
            }
            return event
        }
    }

    private func removeEventMonitors() {
        if let globalEventMonitor { NSEvent.removeMonitor(globalEventMonitor) }
        if let localEventMonitor { NSEvent.removeMonitor(localEventMonitor) }
        globalEventMonitor = nil
        localEventMonitor = nil
    }

    private func handleUserEvent(_ event: NSEvent) {
        guard let playingTour else { return }
        if event.type == .keyDown && event.keyCode == Self.escapeKeyCode {
            stop()
            return
        }
        guard isWaitingForUserToDoStep else { return }
        let currentStep = playingTour.steps[currentStepIndex]
        let eventLocation = NSEvent.mouseLocation

        switch currentStep.action {
        case .click, .doubleClick, .rightClick:
            guard event.type == .leftMouseDown || event.type == .rightMouseDown else { return }
            handleClick(at: eventLocation, for: currentStep)

        case .drag:
            if event.type == .leftMouseDown {
                dragStartLocation = eventLocation
            } else if event.type == .leftMouseUp, let dragStartLocation,
                      hypot(eventLocation.x - dragStartLocation.x, eventLocation.y - dragStartLocation.y) > 12 {
                completeCurrentStep(afterSeconds: 0.6)
            }

        case .type:
            guard event.type == .keyDown else { return }
            let commandOrControlHeld = !event.modifierFlags.intersection([.command, .control]).isEmpty
            if Self.submitKeyCodes.contains(event.keyCode), typedCharacterCount > 0 {
                completeCurrentStep(afterSeconds: 0.5)
            } else if !commandOrControlHeld, !(event.characters ?? "").isEmpty {
                typedCharacterCount += 1
                // The user stopped typing for a moment: treat the text as entered.
                completeCurrentStep(whenIdleForSeconds: 1.6)
            }

        case .key:
            guard event.type == .keyDown else { return }
            let expectsModifier = ["cmd", "command", "ctrl", "control", "alt", "option", "shift", "⌘", "⌃", "⌥"]
                .contains { currentStep.keys.lowercased().contains($0) }
            let modifierHeld = !event.modifierFlags.intersection([.command, .control, .option]).isEmpty
            if !expectsModifier || modifierHeld {
                completeCurrentStep(afterSeconds: 0.6)
            }

        case .scroll:
            guard event.type == .scrollWheel else { return }
            completeCurrentStep(whenIdleForSeconds: 1.0)

        case .wait:
            break
        }
    }

    private func handleClick(at clickLocation: CGPoint, for tutorialTourStep: TutorialTourStep) {
        guard let currentTargetResolution else {
            // TipTour could not find the target; the user found it themselves.
            completeCurrentStep(afterSeconds: 0.7)
            return
        }

        let targetHitRect = currentTargetResolution.globalScreenRect?.insetBy(dx: -16, dy: -16)
        let clickedOnTarget = targetHitRect?.contains(clickLocation)
            ?? (hypot(clickLocation.x - currentTargetResolution.globalScreenPoint.x,
                      clickLocation.y - currentTargetResolution.globalScreenPoint.y) < 44)
        if clickedOnTarget {
            completeCurrentStep(afterSeconds: tutorialTourStep.action == .doubleClick ? 0.9 : 0.7)
            return
        }

        // A click elsewhere may have changed the screen (or the pointer was
        // off). Look again; after a second click away, assume the user did
        // the step their own way and move on rather than getting stuck.
        clicksAwayFromTargetCount += 1
        if clicksAwayFromTargetCount >= 2 {
            completeCurrentStep(afterSeconds: 0.7)
        } else {
            pointerControls.clearPointer()
            self.currentTargetResolution = nil
            publishState(targetStatusText: "Looking again…")
            Task { [weak self] in
                try? await Task.sleep(nanoseconds: 700_000_000)
                guard let self, self.isWaitingForUserToDoStep else { return }
                self.locateAndPointAtCurrentTarget()
            }
        }
    }

    private func completeCurrentStep(whenIdleForSeconds idleSeconds: Double) {
        idleCompletionTask?.cancel()
        idleCompletionTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(idleSeconds * 1_000_000_000))
            guard let self, !Task.isCancelled else { return }
            self.completeCurrentStep(afterSeconds: 0.2)
        }
    }

    // MARK: - Presentation

    private func publishState(targetStatusText: String) {
        guard let playingTour else { return }
        let playbackState = TutorialTourPlaybackState(
            tour: playingTour,
            currentStepIndex: currentStepIndex,
            targetStatusText: targetStatusText
        )
        tourCardPanelController.show(
            playbackState: playbackState,
            targetCropImage: TutorialTourLibrary.targetCropPNGData(for: playbackState.currentStep, in: playingTour)
                .flatMap(NSImage.init(data:))
        )
        onPlaybackStateChange?(playbackState)
    }

    private func pointerBubbleText(for tutorialTourStep: TutorialTourStep, in tour: TutorialTour) -> String {
        let instructionText = tutorialTourStep.instructionText
        let shortInstructionText = instructionText.count > 34 ? "\(instructionText.prefix(33))…" : instructionText
        return "\(currentStepIndex + 1)/\(tour.steps.count) · \(shortInstructionText)"
    }

    private static func waitingHint(for tutorialTourStep: TutorialTourStep) -> String {
        switch tutorialTourStep.action {
        case .type: return "Type it, then pause or press Return."
        case .key: return "Press the shortcut."
        case .scroll: return "Scroll, then stop."
        case .wait: return "Moving on in a moment…"
        case .click, .doubleClick, .rightClick, .drag: return ""
        }
    }

    /// 3–10 s, longer for longer text, so read-only steps never dead-end.
    private static func readingPauseSeconds(for tutorialTourStep: TutorialTourStep) -> Double {
        let readableCharacterCount = tutorialTourStep.expectedResult.count + tutorialTourStep.targetDescription.count
        return min(10, max(3, Double(readableCharacterCount) / 15))
    }

    // MARK: - Screenshots

    /// See `TutorialTourPrompts.pointingPrompt` for why the image is square.
    private static let pointingImageSideInPixels = 1000

    private static func squareJPEGData(from screenshotJPEGData: Data, sideInPixels: Int) -> Data? {
        guard let imageSource = CGImageSourceCreateWithData(screenshotJPEGData as CFData, nil),
              let screenshotImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil),
              let drawingContext = CGContext(
                  data: nil,
                  width: sideInPixels,
                  height: sideInPixels,
                  bitsPerComponent: 8,
                  bytesPerRow: 0,
                  space: CGColorSpaceCreateDeviceRGB(),
                  bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
              ) else {
            return nil
        }
        drawingContext.interpolationQuality = .high
        drawingContext.draw(screenshotImage, in: CGRect(x: 0, y: 0, width: sideInPixels, height: sideInPixels))
        guard let squareImage = drawingContext.makeImage() else { return nil }
        return NSBitmapImageRep(cgImage: squareImage).representation(using: .jpeg, properties: [.compressionFactor: 0.85])
    }

    private static let escapeKeyCode: UInt16 = 53
    /// Return, Tab, and keypad Enter.
    private static let submitKeyCodes: Set<UInt16> = [36, 48, 76]
}
