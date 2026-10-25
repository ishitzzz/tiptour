//
//  AskHarnessShortcut.swift
//  TipTour
//
//  Modifier encoding for the "ask about this" hotkey (control + option +
//  shift held together). Translates raw CGEvents into press/release
//  transitions for GlobalAskHarnessShortcutMonitor.
//
//  The three-modifier combination stays clear of the existing shortcuts:
//  push-to-talk is control+option without shift, focus highlight is
//  control+shift without option, and the input chooser is
//  control+option+command.
//

import AppKit
import CoreGraphics

enum AskHarnessShortcut {
    enum ShortcutTransition {
        case pressed
        case released
        case none
    }

    static func shortcutTransition(
        for eventType: CGEventType,
        modifierFlagsRawValue: UInt64,
        wasShortcutPreviouslyPressed: Bool
    ) -> ShortcutTransition {
        guard eventType == .flagsChanged else { return .none }

        let modifierFlags = NSEvent.ModifierFlags(rawValue: UInt(modifierFlagsRawValue))
        let isShortcutHeld = modifierFlags.contains(.control)
            && modifierFlags.contains(.option)
            && modifierFlags.contains(.shift)
            && !modifierFlags.contains(.command)

        if isShortcutHeld && !wasShortcutPreviouslyPressed {
            return .pressed
        }
        if !isShortcutHeld && wasShortcutPreviouslyPressed {
            return .released
        }
        return .none
    }
}
