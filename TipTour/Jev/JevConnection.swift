import Foundation

/// Where JEV decisions are requested from. Both options speak the same
/// System One request and response shape, so the decision logic is shared.
nonisolated enum JevConnection: String, CaseIterable, Identifiable {
    case typesafeDirect
    case openRouter

    static let defaultsKey = "jevConnection"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .typesafeDirect: return "TypeSafe direct"
        case .openRouter: return "OpenRouter"
        }
    }

    var endpoint: URL {
        switch self {
        case .typesafeDirect: return URL(string: "https://api.typesafe.ai/v1/systemone")!
        case .openRouter: return URL(string: "https://openrouter.ai/api/v1/systemone")!
        }
    }

    var model: String {
        switch self {
        case .typesafeDirect: return "jev-latest"
        case .openRouter: return "~typesafe/jev-latest"
        }
    }

    /// Keychain account for this connection's key. The two keys never mix.
    var keyName: String {
        switch self {
        case .typesafeDirect: return "jevAPIKey"
        case .openRouter: return "openRouterJevAPIKey"
        }
    }

    var keyTitle: String {
        switch self {
        case .typesafeDirect: return "JEV / TypeSafe key"
        case .openRouter: return "JEV / OpenRouter key"
        }
    }

    var summary: String {
        switch self {
        case .typesafeDirect: return "Your TypeSafe account and key."
        case .openRouter:
            return "TypeSafe Jev through OpenRouter, using your OpenRouter key. Input tokens are billed to your OpenRouter balance; output tokens are free. See openrouter.ai/typesafe/jev-1.14 for the current price. Nothing falls back or tops up automatically."
        }
    }

    var privacySummary: String {
        switch self {
        case .typesafeDirect:
            return "Your task and detected screen labels go to TypeSafe. Images stay on your Mac."
        case .openRouter:
            return "Your task and detected screen labels go to OpenRouter and TypeSafe. Images stay on your Mac."
        }
    }

    static func restored(from value: String?) -> Self {
        value.flatMap(Self.init(rawValue:)) ?? .typesafeDirect
    }

    /// The saved choice. Defaults to TypeSafe direct.
    static var saved: Self {
        restored(from: UserDefaults.standard.string(forKey: defaultsKey))
    }
}
