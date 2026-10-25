import Foundation

nonisolated enum TipTourMode: String, CaseIterable, Identifiable {
    case jev
    case gemini

    var id: String { rawValue }
    var title: String { self == .jev ? "JEV" : "Gemini" }
    var keyName: String { self == .jev ? JevConnection.saved.keyName : "geminiAPIKey" }
    var shortcut: String { self == .jev ? "Ctrl+K" : "Ctrl+Option" }
    var systemImage: String { self == .jev ? "text.cursor" : "waveform" }
    var summary: String {
        self == .jev ? "Type a task. JEV finds and clicks screen controls."
            : "Talk naturally. Gemini can click, type, and guide you."
    }
    var privacySummary: String {
        self == .jev ? JevConnection.saved.privacySummary
            : "Your voice and optional screenshots go to Google."
    }

    static func restored(from value: String?) -> Self {
        value.flatMap(Self.init(rawValue:)) ?? .jev
    }

    func permissionsReady(desktop: Bool, microphone: Bool) -> Bool {
        desktop && (self == .jev || microphone)
    }
}
