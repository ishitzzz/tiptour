import Foundation
import Testing
@testable import TipTour

@Suite(.serialized) @MainActor
struct JevTests {
    @Test func targetContinuityAllowsJitterButRejectsDifferentControls() {
        func matches(_ box: [Double], label: String = "New Tab", source: String = "ocr",
                     display: [Double] = [0, 0, 1512, 982]) -> Bool {
            LocalTargetContinuity.matches(label: label, source: source, box: box, display: display,
                previousLabel: "New Tab", previousSource: "ocr", previousBox: [100, 50, 160, 65],
                previousDisplay: [0, 0, 1512, 982])
        }
        #expect(matches([101, 49, 161, 66]))
        #expect(!matches([500, 50, 560, 65]))
        #expect(!matches([100, 50, 160, 65], label: "Close Tab"))
        #expect(!matches([100, 50, 160, 65], display: [1512, 0, 1512, 982]))
        #expect(!matches([100, 50, 160, 65], source: "yolo"))
        #expect(!matches([100, 50]))
    }

    private let metrics = JevCallMetrics(milliseconds: 1, inputTokens: 100, model: "jev-latest")
    private func candidate(_ id: String = "save", label: String = "Save") -> JevCandidate {
        JevCandidate(id: id, label: label, source: "ocr", confidence: 1, centre: .zero)
    }
    private func answers(choice: String = "save", absent: Double = 0.1,
                         probability: Double = 0.9, kind: String = "click") throws -> [String: JevAnswer] {
        let data = try JSONSerialization.data(withJSONObject: [
            "pick": ["choice": choice, "probabilities": [choice: probability]],
            "done": ["noul": 0.1], "absent": ["noul": absent], "kind": ["choice": kind]
        ])
        return try JSONDecoder().decode([String: JevAnswer].self, from: data)
    }

    @Test func defaultModeIsJevAndSavedChoiceIsRespected() {
        #expect(TipTourMode.restored(from: nil) == .jev)
        #expect(TipTourMode.restored(from: "obsolete-provider") == .jev)
        #expect(TipTourMode.restored(from: "gemini") == .gemini)
        #expect(TipTourMode.restored(from: "jev") == .jev)
    }

    @Test func microphoneIsRequiredOnlyForGemini() {
        #expect(TipTourMode.jev.permissionsReady(desktop: true, microphone: false))
        #expect(!TipTourMode.gemini.permissionsReady(desktop: true, microphone: false))
        #expect(TipTourMode.gemini.permissionsReady(desktop: true, microphone: true))
        #expect(!TipTourMode.jev.permissionsReady(desktop: false, microphone: true))
    }

    @Test func selectedModeUsesItsOwnKeyAndShortcut() {
        // Assert the explicit per-connection config, not the saved default:
        // `TipTourMode.jev.keyName` follows `JevConnection.saved`, so reading it
        // here would make the result depend on whatever a previous test saved.
        #expect(JevConnection.typesafeDirect.keyName == "jevAPIKey")
        #expect(JevConnection.openRouter.keyName == "openRouterJevAPIKey")
        #expect(TipTourMode.gemini.keyName == "geminiAPIKey")
        #expect(TipTourMode.jev.shortcut == "Ctrl+K")
        #expect(TipTourMode.gemini.shortcut == "Ctrl+Option")
    }

    @Test func jevKeyGateFollowsTheSavedConnection() {
        // The key card and the run gate read the key for the *saved* connection,
        // so saving OpenRouter must gate on the OpenRouter key, never the direct
        // one. UserDefaults is isolated and restored so this stays deterministic.
        let key = JevConnection.defaultsKey
        let previous = UserDefaults.standard.string(forKey: key)
        defer {
            if let previous { UserDefaults.standard.set(previous, forKey: key) }
            else { UserDefaults.standard.removeObject(forKey: key) }
        }
        UserDefaults.standard.set(JevConnection.typesafeDirect.rawValue, forKey: key)
        #expect(TipTourMode.jev.keyName == "jevAPIKey")
        #expect(!TipTourMode.jev.privacySummary.contains("OpenRouter"))
        UserDefaults.standard.set(JevConnection.openRouter.rawValue, forKey: key)
        #expect(TipTourMode.jev.keyName == "openRouterJevAPIKey")
        #expect(TipTourMode.jev.privacySummary.contains("OpenRouter"))
    }

    @Test func requestsStayUnderAPILimitAndKeepNoneOption() {
        let candidates = (0..<300).map { candidate("id-\($0)", label: "Button \($0)") }
        let request = JevGrounding.request(task: "Save", candidates: candidates, history: [], excluding: [])
        #expect(request?.pool.count == 200)
        if case let .choice(_, criteria) = request?.questions["pick"] {
            #expect(criteria.count == 201)
            #expect(criteria[JevGrounding.noneKey] != nil)
        } else { Issue.record("Missing bounded choice question") }
    }

    @Test func duplicateAndReservedIDsCannotCrashCandidateDictionary() {
        let request = JevGrounding.request(task: "Save", candidates: [
            candidate(), candidate(label: "Different label"), candidate("__none__"), candidate("")
        ], history: [], excluding: [])
        #expect(request?.pool.count == 1)
    }

    @Test func noneChoiceStopsInsteadOfClickingRunnerUp() throws {
        var payload = try answers(choice: "__none__")
        payload["pick"] = try JSONDecoder().decode(JevAnswer.self, from: Data(
            #"{"choice":"__none__","probabilities":{"__none__":0.9,"save":0.1}}"#.utf8))
        let result = try JevGrounding.decision(from: payload, pool: [candidate()], metrics: metrics)
        #expect(result.best?.candidate.id == "save")
        #expect(result.stopReason == "target_absent")
    }

    @Test func topTargetIsAllowedRegardlessOfAbsentScoreOrProbability() throws {
        let absent = try JevGrounding.decision(from: answers(absent: 0.9), pool: [candidate()], metrics: metrics)
        let weak = try JevGrounding.decision(from: answers(probability: 0.2), pool: [candidate()], metrics: metrics)
        #expect(absent.stopReason == nil)
        #expect(absent.best?.candidate.id == "save")
        #expect(weak.stopReason == nil)
        #expect(weak.best?.candidate.id == "save")
    }

    @Test func inventedTargetOrActionAndIncompleteResponsesAreRejected() throws {
        #expect(throws: JevError.self) {
            try JevGrounding.decision(from: answers(choice: "invented"), pool: [candidate()], metrics: metrics)
        }
        #expect(throws: JevError.self) {
            try JevGrounding.decision(from: answers(kind: "type"), pool: [candidate()], metrics: metrics)
        }
        #expect(throws: JevError.self) {
            try JevGrounding.decision(from: [:], pool: [candidate()], metrics: metrics)
        }
    }

    @Test func pickWithoutProbabilitiesIsRejected() throws {
        // A choice answer with no probability map is incomplete: the loop must
        // refuse it rather than act on the bare choice.
        var payload = try answers()
        payload["pick"] = try JSONDecoder().decode(JevAnswer.self, from: Data(
            #"{"choice":"save"}"#.utf8))
        #expect(throws: JevError.self) {
            try JevGrounding.decision(from: payload, pool: [candidate()], metrics: metrics)
        }
    }

    @Test func invalidProbabilitiesAreRejected() throws {
        // Out-of-range probability.
        var over = try answers()
        over["pick"] = try JSONDecoder().decode(JevAnswer.self, from: Data(
            #"{"choice":"save","probabilities":{"save":1.5}}"#.utf8))
        #expect(throws: JevError.self) {
            try JevGrounding.decision(from: over, pool: [candidate()], metrics: metrics)
        }
        // The named choice must be the reported maximum; a response that picks
        // the weaker option is rejected, not trusted.
        var notTop = try answers()
        notTop["pick"] = try JSONDecoder().decode(JevAnswer.self, from: Data(
            #"{"choice":"save","probabilities":{"save":0.3,"cancel":0.7}}"#.utf8))
        #expect(throws: JevError.self) {
            try JevGrounding.decision(from: notTop,
                pool: [candidate(), candidate("cancel", label: "Cancel")], metrics: metrics)
        }
        // Out-of-range noul probabilities are rejected too.
        #expect(throws: JevError.self) {
            try JevGrounding.decision(from: answers(absent: 1.4), pool: [candidate()], metrics: metrics)
        }
    }

    @Test func validClickUsesSuppliedTarget() throws {
        let decision = try JevGrounding.decision(from: answers(), pool: [candidate()], metrics: metrics)
        #expect(decision.best?.candidate.id == "save")
        #expect(decision.actionKind == "click")
        #expect(decision.stopReason == nil)
    }

    @Test func roundedTieHonorsTheSelectedOption() throws {
        var payload = try answers()
        payload["pick"] = try JSONDecoder().decode(JevAnswer.self, from: Data(
            #"{"choice":"save","probabilities":{"cancel":0.5,"save":0.5}}"#.utf8))
        let result = try JevGrounding.decision(from: payload,
            pool: [candidate(), candidate("cancel", label: "Cancel")], metrics: metrics)
        #expect(result.best?.candidate.id == "save")
    }

    @Test func missingKeyFailsBeforeNetworkRequest() async {
        let client = JevClient(apiKeyProvider: { nil })
        await #expect(throws: JevError.self) {
            try await client.ask(state: [:], questions: [:])
        }
    }

    @Test func connectionsUseSeparateEndpointsModelsAndKeys() {
        #expect(JevConnection.restored(from: nil) == .typesafeDirect)
        #expect(JevConnection.restored(from: "unknown") == .typesafeDirect)
        #expect(JevConnection.restored(from: "openRouter") == .openRouter)
        #expect(JevConnection.typesafeDirect.endpoint.absoluteString == "https://api.typesafe.ai/v1/systemone")
        #expect(JevConnection.typesafeDirect.model == "jev-latest")
        #expect(JevConnection.openRouter.endpoint.absoluteString == "https://openrouter.ai/api/v1/systemone")
        #expect(JevConnection.openRouter.model == "~typesafe/jev-latest")
        #expect(JevConnection.typesafeDirect.keyName != JevConnection.openRouter.keyName)
        #expect(JevConnection.typesafeDirect.keyName == "jevAPIKey")
    }

    @Test func openRouterRequestUsesItsEndpointModelAndKeyAndReadsExtraFields() async throws {
        let body = #"{"id":"gen-1","model":"typesafe/jev-1.14","provider":"TypeSafe","answers":{"done":{"noul":0.2}},"usage":{"input_tokens":42,"output_tokens":0,"cost":0.000002}}"#
        JevStubProtocol.reset(status: 200, body: body)
        let client = JevClient(connection: .openRouter, apiKeyProvider: { "or-test-key" }, session: JevStubProtocol.session())
        let result = try await client.ask(state: ["a": 1], questions: ["done": .noul(instructions: "Is it done?")])
        let request = try #require(JevStubProtocol.lastRequest)
        #expect(request.url?.absoluteString == "https://openrouter.ai/api/v1/systemone")
        #expect(request.value(forHTTPHeaderField: "authorization") == "Bearer or-test-key")
        let sent = try #require(JevStubProtocol.lastBody)
        let json = try #require(try JSONSerialization.jsonObject(with: sent) as? [String: Any])
        #expect(json["model"] as? String == "~typesafe/jev-latest")
        #expect(json["state"] != nil && json["questions"] != nil)
        #expect(result.answers["done"]?.noul == 0.2)
        #expect(result.metrics.inputTokens == 42)
        #expect(result.metrics.cost == 0.000002)
        #expect(result.metrics.provider == "TypeSafe")
    }

    @Test func directRequestIsUnchanged() async throws {
        JevStubProtocol.reset(status: 200, body: #"{"model":"jev-latest","answers":{"done":{"noul":0.5}},"usage":{"input_tokens":7}}"#)
        let client = JevClient(connection: .typesafeDirect, apiKeyProvider: { "ts-test-key" }, session: JevStubProtocol.session())
        let result = try await client.ask(state: [:], questions: ["done": .noul(instructions: "Done?")])
        #expect(JevStubProtocol.lastRequest?.url?.absoluteString == "https://api.typesafe.ai/v1/systemone")
        #expect(result.metrics.cost == nil)
        #expect(result.metrics.provider == nil)
    }

    @Test func oddProviderOrCostShapesDoNotFailValidAnswers() async throws {
        JevStubProtocol.reset(status: 200, body: #"{"provider":{"name":"x"},"answers":{"done":{"noul":0.5}},"usage":{"input_tokens":3,"cost":"free"}}"#)
        let client = JevClient(connection: .openRouter, apiKeyProvider: { "k" }, session: JevStubProtocol.session())
        let result = try await client.ask(state: [:], questions: ["done": .noul(instructions: "Done?")])
        #expect(result.answers["done"]?.noul == 0.5)
        #expect(result.metrics.cost == nil)
        #expect(result.metrics.provider == nil)
    }

    @Test func httpErrorsNeverShowTheServerBody() async {
        JevStubProtocol.reset(status: 401, body: "bad key or-secret-123")
        let client = JevClient(connection: .openRouter, apiKeyProvider: { "or-secret-123" }, session: JevStubProtocol.session())
        do {
            _ = try await client.ask(state: [:], questions: [:])
            Issue.record("expected an error")
        } catch {
            let text = error.localizedDescription
            #expect(text.contains("401"))
            #expect(!text.contains("or-secret-123"))
        }
        let payment = JevError.http(status: 402, body: "x").localizedDescription
        #expect(payment.contains("402"))
    }

    @Test func missingOpenRouterKeyFailsBeforeNetworkRequest() async {
        JevStubProtocol.reset(status: 200, body: "{}")
        let client = JevClient(connection: .openRouter, apiKeyProvider: { "" }, session: JevStubProtocol.session())
        await #expect(throws: JevError.self) {
            try await client.ask(state: [:], questions: [:])
        }
        #expect(JevStubProtocol.lastRequest == nil)
    }
}

/// Serves a canned response so connection tests never touch the network.
final class JevStubProtocol: URLProtocol {
    nonisolated(unsafe) static var status = 200
    nonisolated(unsafe) static var body = "{}"
    nonisolated(unsafe) static var lastRequest: URLRequest?
    nonisolated(unsafe) static var lastBody: Data?

    static func reset(status: Int, body: String) {
        self.status = status
        self.body = body
        lastRequest = nil
        lastBody = nil
    }

    static func session() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [JevStubProtocol.self]
        return URLSession(configuration: configuration)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lastRequest = request
        if let stream = request.httpBodyStream {
            stream.open()
            var data = Data()
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count <= 0 { break }
                data.append(buffer, count: count)
            }
            stream.close()
            Self.lastBody = data
        } else {
            Self.lastBody = request.httpBody
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status,
            httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(Self.body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
