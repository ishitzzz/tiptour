//
//  TutorialToursPanelSection.swift
//  TipTour
//
//  "Learn from a video" in the menu bar panel: paste a tutorial link (or
//  choose a file), watch the build progress, and play or delete saved
//  tours.
//

import SwiftUI

struct TutorialToursPanelSection: View {
    @ObservedObject var tutorialTourController: TutorialTourController
    @State private var videoLinkInput = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Learn from a video")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(DS.Colors.textPrimary)
                Spacer()
                Text("Elorian")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(DS.Colors.textTertiary)
            }

            if let playbackState = tutorialTourController.playbackState {
                playingRow(playbackState)
            } else if tutorialTourController.isBuildingTour {
                buildingRow
            } else if !tutorialTourController.hasElorianAPIKey {
                Text("Add an Elorian key in Settings → Models to turn tutorial videos into tours.")
                    .font(.system(size: 11))
                    .foregroundColor(DS.Colors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                linkInputRow
            }

            if let lastBuildErrorText = tutorialTourController.lastBuildErrorText {
                Text(lastBuildErrorText)
                    .font(.system(size: 10))
                    .foregroundColor(DS.Colors.warningText)
                    .fixedSize(horizontal: false, vertical: true)
            }

            ForEach(tutorialTourController.savedTours.prefix(5)) { savedTour in
                SavedTutorialTourRow(
                    savedTour: savedTour,
                    isPlaying: tutorialTourController.playbackState?.tour.id == savedTour.id,
                    onPlay: { tutorialTourController.play(savedTour) },
                    onDelete: { tutorialTourController.delete(savedTour) }
                )
            }
        }
        .onAppear { tutorialTourController.refresh() }
    }

    private var linkInputRow: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                TextField("Paste a YouTube or video link", text: $videoLinkInput)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 11))
                    .onSubmit(learnFromLink)
                Button("Learn", action: learnFromLink)
                    .disabled(videoLinkInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .pointerCursor()
            }
            Button {
                tutorialTourController.chooseVideoFileAndLearn()
            } label: {
                Text("or choose a video file…")
                    .font(.system(size: 10))
                    .foregroundColor(DS.Colors.accentText)
            }
            .buttonStyle(.plain)
            .pointerCursor()
        }
    }

    private var buildingRow: some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small)
            VStack(alignment: .leading, spacing: 2) {
                Text(tutorialTourController.buildStatusText ?? "Working…")
                    .font(.system(size: 11))
                    .foregroundColor(DS.Colors.textSecondary)
                    .lineLimit(2)
                if let buildStartedAt = tutorialTourController.buildStartedAt {
                    // Elorian takes several minutes per part; show it's alive.
                    TimelineView(.periodic(from: buildStartedAt, by: 1)) { timelineContext in
                        Text(Self.elapsedText(from: buildStartedAt, to: timelineContext.date) + " · usually 2–10 min")
                            .font(.system(size: 10))
                            .foregroundColor(DS.Colors.textTertiary)
                    }
                }
            }
            Spacer()
            Button("Cancel") { tutorialTourController.cancelBuild() }
                .controlSize(.small)
                .pointerCursor()
        }
    }

    private func playingRow(_ playbackState: TutorialTourPlaybackState) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "play.circle.fill")
                .foregroundColor(DS.Colors.accent)
            VStack(alignment: .leading, spacing: 2) {
                Text("Step \(playbackState.currentStepIndex + 1) of \(playbackState.tour.steps.count)")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(DS.Colors.textPrimary)
                Text(playbackState.currentStep.instructionText)
                    .font(.system(size: 10))
                    .foregroundColor(DS.Colors.textSecondary)
                    .lineLimit(1)
            }
            Spacer()
            Button("Stop") { tutorialTourController.stopPlayback() }
                .controlSize(.small)
                .pointerCursor()
        }
    }

    private func learnFromLink() {
        let submittedInput = videoLinkInput
        guard !submittedInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        videoLinkInput = ""
        tutorialTourController.learnTutorial(fromUserInput: submittedInput)
    }

    private static func elapsedText(from startDate: Date, to currentDate: Date) -> String {
        let elapsedSeconds = max(0, Int(currentDate.timeIntervalSince(startDate)))
        return String(format: "%d:%02d", elapsedSeconds / 60, elapsedSeconds % 60)
    }
}

private struct SavedTutorialTourRow: View {
    let savedTour: TutorialTour
    let isPlaying: Bool
    let onPlay: () -> Void
    let onDelete: () -> Void
    @State private var isHovering = false

    var body: some View {
        HStack(spacing: 8) {
            Button(action: onPlay) {
                HStack(spacing: 8) {
                    Image(systemName: isPlaying ? "play.circle.fill" : "play.circle")
                        .font(.system(size: 15))
                        .foregroundColor(isHovering || isPlaying ? DS.Colors.accent : DS.Colors.textSecondary)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(savedTour.title)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(DS.Colors.textPrimary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                        Text(subtitleText)
                            .font(.system(size: 10))
                            .foregroundColor(DS.Colors.textTertiary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .pointerCursor()
            .help("Walk me through this tutorial")

            if isHovering {
                Button(action: onDelete) {
                    Image(systemName: "trash")
                        .font(.system(size: 10))
                        .foregroundColor(DS.Colors.textTertiary)
                }
                .buttonStyle(.plain)
                .pointerCursor()
                .help("Delete this tour")
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(isHovering ? Color.white.opacity(0.06) : DS.Colors.surface1)
        )
        .onHover { isHovering = $0 }
    }

    private var subtitleText: String {
        let appPrefix = savedTour.appName.isEmpty ? "" : "\(savedTour.appName) · "
        return "\(appPrefix)\(savedTour.steps.count) steps"
    }
}
