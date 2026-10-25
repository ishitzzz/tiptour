//
//  AskPreviewView.swift
//  TipTour
//
//  Preview of the captured screenshot (with the scribble composited) and
//  the transcribed question. The user picks the target app, edits the
//  text if recognition misheard, and inserts the pair as a draft.
//

import SwiftUI

struct AskPreviewView: View {
    @ObservedObject var controller: AskHarnessController

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Ask with screenshot")
                .font(.system(size: 15, weight: .semibold))

            if let image = controller.draftImage {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(maxWidth: .infinity, maxHeight: 240)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(Color.primary.opacity(0.12), lineWidth: 1)
                    )

                Text(controller.captureCaption)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Your question")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                TextEditor(text: $controller.draftText)
                    .font(.system(size: 13))
                    .frame(minHeight: 64, maxHeight: 96)
                    .padding(4)
                    .background(Color.primary.opacity(0.04))
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Or insert directly into an app (optional)")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                Picker("Insert into", selection: $controller.targetBundleIdentifier) {
                    Text("None (copy and paste myself)").tag("")
                    ForEach(controller.targetApps) { target in
                        Text(target.isInstalled ? target.name : "\(target.name) (not installed)")
                            .tag(target.bundleIdentifier)
                    }
                }
                .labelsHidden()
                .onChange(of: controller.targetBundleIdentifier) { _, _ in
                    controller.persistTargetSelection()
                }
            }

            if let confirmation = controller.copyConfirmation {
                Text(confirmation)
                    .font(.system(size: 12))
                    .foregroundColor(.green)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let status = controller.insertionStatus {
                Text(status)
                    .font(.system(size: 12))
                    .foregroundColor(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text("Copy puts the marked image and your question on the clipboard so you can paste them into any app, site or guide. Nothing is sent. Transcription ran on this Mac.")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack {
                Button("Close") {
                    controller.cancelPreview()
                }
                .keyboardShortcut(.cancelAction)

                Spacer()

                Button("Copy image") { controller.copyToClipboard(.imageOnly) }
                    .disabled(controller.draftImage == nil)
                Button("Copy text") { controller.copyToClipboard(.textOnly) }
                    .disabled(controller.draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Copy both") { controller.copyToClipboard(.imageAndText) }
                    .keyboardShortcut(.defaultAction)
                    .disabled(controller.draftImage == nil)

                Button(action: { controller.insertDraft() }) {
                    if controller.isInserting {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Text("Insert")
                    }
                }
                .disabled(controller.isInserting || controller.draftImage == nil || controller.targetBundleIdentifier.isEmpty)
            }
        }
        .padding(16)
        .frame(width: 460, height: 560)
    }
}
