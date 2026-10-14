//
//  TutorialTourController.swift
//  TipTour
//
//  UI-facing state for "Learn from a video": the saved tours, the build in
//  progress, and the tour being played. Owned by CompanionManager and
//  observed by the menu bar panel.
//

import AppKit
import Combine
import Foundation
import UniformTypeIdentifiers

@MainActor
final class TutorialTourController: ObservableObject {
    @Published private(set) var savedTours: [TutorialTour] = []
    @Published private(set) var hasElorianAPIKey = false
    @Published private(set) var isBuildingTour = false
    @Published private(set) var buildStatusText: String?
    @Published private(set) var buildStartedAt: Date?
    @Published private(set) var lastBuildErrorText: String?
    @Published private(set) var playbackState: TutorialTourPlaybackState?

    private let tutorialTourPlayer: TutorialTourPlayer
    private var tourBuildTask: Task<Void, Never>?

    init(pointerControls: TutorialTourPointerControls) {
        tutorialTourPlayer = TutorialTourPlayer(pointerControls: pointerControls)
        tutorialTourPlayer.onPlaybackStateChange = { [weak self] playbackState in
            self?.playbackState = playbackState
        }
        refresh()
    }

    func refresh() {
        savedTours = TutorialTourLibrary.loadAllTours()
        hasElorianAPIKey = !(KeychainStore.elorianAPIKey ?? "").isEmpty
    }

    /// Accepts a YouTube/Loom/direct video link or a local file path.
    func learnTutorial(fromUserInput userInput: String) {
        let trimmedInput = userInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedInput.isEmpty, !isBuildingTour else { return }
        refresh()
        guard hasElorianAPIKey else {
            lastBuildErrorText = ElorianError.missingAPIKey.localizedDescription
            return
        }

        isBuildingTour = true
        lastBuildErrorText = nil
        buildStartedAt = Date()
        buildStatusText = "Starting…"

        tourBuildTask = Task { [weak self] in
            do {
                let builtTour = try await TutorialTourBuilder.buildTour(fromUserInput: trimmedInput) { progressText in
                    self?.buildStatusText = progressText
                }
                guard let self else { return }
                self.finishBuild(errorText: nil)
                self.refresh()
                print("[Tutorials] built \"\(builtTour.title)\": \(builtTour.steps.count) steps, ~$\(String(format: "%.2f", builtTour.estimatedCostInDollars))")
            } catch is CancellationError {
                self?.finishBuild(errorText: nil)
            } catch {
                self?.finishBuild(errorText: error.localizedDescription)
            }
        }
    }

    func chooseVideoFileAndLearn() {
        let openPanel = NSOpenPanel()
        openPanel.allowedContentTypes = [.movie, .mpeg4Movie, .quickTimeMovie]
        openPanel.allowsMultipleSelection = false
        openPanel.canChooseDirectories = false
        openPanel.message = "Choose a screen-recorded tutorial"
        NSApp.activate(ignoringOtherApps: true)
        guard openPanel.runModal() == .OK, let chosenVideoFileURL = openPanel.url else { return }
        learnTutorial(fromUserInput: chosenVideoFileURL.path)
    }

    func cancelBuild() {
        tourBuildTask?.cancel()
    }

    func play(_ tour: TutorialTour) {
        tutorialTourPlayer.play(tour)
    }

    func stopPlayback() {
        tutorialTourPlayer.stop()
    }

    func delete(_ tour: TutorialTour) {
        if playbackState?.tour.id == tour.id { tutorialTourPlayer.stop() }
        TutorialTourLibrary.delete(tour)
        refresh()
    }

    private func finishBuild(errorText: String?) {
        isBuildingTour = false
        buildStatusText = nil
        buildStartedAt = nil
        lastBuildErrorText = errorText
        tourBuildTask = nil
    }
}
