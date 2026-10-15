//
//  TutorialTourCardPanel.swift
//  TipTour
//
//  The small card at the bottom of the screen while a tutorial tour plays:
//  step number, instruction, what to look for, and the target as it looked
//  in the tutorial video. It ignores the mouse so it never blocks a click
//  in the app the user is following along in, and it has no buttons:
//  steps advance when the user does them, and Escape stops the tour.
//

import AppKit
import Combine
import SwiftUI

@MainActor
final class TutorialTourCardModel: ObservableObject {
    @Published var tourTitle = ""
    @Published var stepCounterText = ""
    @Published var instructionText = ""
    @Published var detailText = ""
    @Published var targetStatusText = ""
    @Published var targetCropImage: NSImage?
    @Published var isFinished = false
}

@MainActor
final class TutorialTourCardPanelController {
    private let cardModel = TutorialTourCardModel()
    private var panel: NSPanel?
    private let panelSize = NSSize(width: 440, height: 132)
    private let bottomMargin: CGFloat = 28

    func show(playbackState: TutorialTourPlaybackState, targetCropImage: NSImage?) {
        let currentStep = playbackState.currentStep
        cardModel.isFinished = false
        cardModel.tourTitle = playbackState.tour.title
        cardModel.stepCounterText = "Step \(playbackState.currentStepIndex + 1) of \(playbackState.tour.steps.count)"
        cardModel.instructionText = currentStep.instructionText
        cardModel.detailText = currentStep.targetDescription.isEmpty ? currentStep.expectedResult : currentStep.targetDescription
        cardModel.targetStatusText = playbackState.targetStatusText
        cardModel.targetCropImage = targetCropImage
        presentPanel()
    }

    func showFinished(tour: TutorialTour) {
        cardModel.isFinished = true
        cardModel.tourTitle = tour.title
        cardModel.stepCounterText = "Done"
        cardModel.instructionText = "You finished the tutorial"
        cardModel.detailText = tour.goal
        cardModel.targetStatusText = ""
        cardModel.targetCropImage = nil
        presentPanel()
    }

    func hide() {
        panel?.orderOut(nil)
    }

    private func presentPanel() {
        if panel == nil { createPanel() }
        positionPanelOnCursorScreen()
        panel?.orderFrontRegardless()
    }

    private func createPanel() {
        let hostingView = NSHostingView(rootView: TutorialTourCardView(cardModel: cardModel))
        hostingView.frame = NSRect(origin: .zero, size: panelSize)
        hostingView.wantsLayer = true
        hostingView.layer?.backgroundColor = .clear

        let cardPanel = NSPanel(
            contentRect: NSRect(origin: .zero, size: panelSize),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        cardPanel.isFloatingPanel = true
        cardPanel.level = .statusBar
        cardPanel.backgroundColor = .clear
        cardPanel.isOpaque = false
        cardPanel.hasShadow = true
        // The card is read-only; clicks must reach the app underneath.
        cardPanel.ignoresMouseEvents = true
        cardPanel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        cardPanel.contentView = hostingView
        panel = cardPanel
    }

    private func positionPanelOnCursorScreen() {
        let mouseLocation = NSEvent.mouseLocation
        let cursorScreen = NSScreen.screens.first { $0.frame.contains(mouseLocation) } ?? NSScreen.main
        guard let visibleFrame = cursorScreen?.visibleFrame else { return }
        panel?.setFrame(
            NSRect(
                x: visibleFrame.midX - panelSize.width / 2,
                y: visibleFrame.minY + bottomMargin,
                width: panelSize.width,
                height: panelSize.height
            ),
            display: true
        )
    }
}

private struct TutorialTourCardView: View {
    @ObservedObject var cardModel: TutorialTourCardModel

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            targetPreview

            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 6) {
                    Text(cardModel.stepCounterText)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(DS.Colors.accent)
                    Text(cardModel.tourTitle)
                        .font(.system(size: 11))
                        .foregroundColor(DS.Colors.textTertiary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }

                Text(cardModel.instructionText)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(DS.Colors.textPrimary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                if !cardModel.detailText.isEmpty {
                    Text(cardModel.detailText)
                        .font(.system(size: 11))
                        .foregroundColor(DS.Colors.textSecondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)

                HStack {
                    Text(cardModel.targetStatusText)
                        .font(.system(size: 10))
                        .foregroundColor(DS.Colors.textTertiary)
                        .lineLimit(1)
                    Spacer()
                    if !cardModel.isFinished {
                        Text("Esc to stop")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(DS.Colors.textTertiary)
                    }
                }
            }
        }
        .padding(14)
        .frame(width: 440, height: 132, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(DS.Colors.background.opacity(0.96))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(DS.Colors.borderSubtle, lineWidth: 1)
        )
    }

    @ViewBuilder
    private var targetPreview: some View {
        if let targetCropImage = cardModel.targetCropImage {
            VStack(spacing: 4) {
                Image(nsImage: targetCropImage)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .frame(width: 84, height: 72)
                    .background(Color.white.opacity(0.04))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                Text("from the video")
                    .font(.system(size: 9))
                    .foregroundColor(DS.Colors.textTertiary)
            }
        } else {
            Image(systemName: cardModel.isFinished ? "checkmark.circle.fill" : "play.rectangle")
                .font(.system(size: 30, weight: .regular))
                .foregroundColor(cardModel.isFinished ? DS.Colors.success : DS.Colors.textTertiary)
                .frame(width: 84, height: 72)
        }
    }
}
