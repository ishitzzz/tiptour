//
//  AskPreviewPanelManager.swift
//  TipTour
//
//  Floating panel that shows the captured image and transcribed question
//  before anything is inserted into another app.
//

import AppKit
import SwiftUI

private final class AskPreviewKeyablePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
    var onEscape: (() -> Void)?

    override func sendEvent(_ event: NSEvent) {
        if event.type == .keyDown, event.keyCode == 53 {
            onEscape?()
            return
        }
        super.sendEvent(event)
    }
}

@MainActor
final class AskPreviewPanelManager {
    private weak var controller: AskHarnessController?
    private var panel: NSPanel?

    private let panelSize = NSSize(width: 460, height: 560)

    init(controller: AskHarnessController) {
        self.controller = controller
    }

    func show() {
        guard let controller else { return }

        if panel == nil {
            createPanel(controller: controller)
        }

        centerPanelOnCursorScreen()
        panel?.makeKeyAndOrderFront(nil)
        panel?.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
    }

    func hide() {
        panel?.orderOut(nil)
    }

    private func createPanel(controller: AskHarnessController) {
        let previewView = AskPreviewView(controller: controller)
        let hostingView = NSHostingView(rootView: previewView)
        hostingView.frame = NSRect(origin: .zero, size: panelSize)

        let previewPanel = AskPreviewKeyablePanel(
            contentRect: NSRect(origin: .zero, size: panelSize),
            styleMask: [.titled, .closable, .nonactivatingPanel, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        previewPanel.onEscape = { [weak controller] in
            controller?.cancelPreview()
        }
        previewPanel.title = "Ask with screenshot"
        previewPanel.titlebarAppearsTransparent = true
        previewPanel.isFloatingPanel = true
        previewPanel.level = .floating
        previewPanel.hidesOnDeactivate = false
        previewPanel.isExcludedFromWindowsMenu = true
        previewPanel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        previewPanel.isReleasedWhenClosed = false
        previewPanel.contentView = hostingView

        panel = previewPanel
    }

    private func centerPanelOnCursorScreen() {
        guard let panel else { return }
        let mouseLocation = NSEvent.mouseLocation
        let screen = NSScreen.screens.first { $0.frame.contains(mouseLocation) } ?? NSScreen.main
        guard let visibleFrame = screen?.visibleFrame else { return }

        let origin = CGPoint(
            x: visibleFrame.midX - panelSize.width / 2,
            y: visibleFrame.midY - panelSize.height / 2
        )
        panel.setFrame(NSRect(origin: origin, size: panelSize), display: true)
    }
}
