import CoreGraphics
import Foundation
import Testing
@testable import TipTour

@MainActor
struct TutorialTourTests {

    // MARK: - Parsing Elorian's answer

    @Test func parsesFencedAnswerAndNormalizesSteps() throws {
        let answerText = """
        ```json
        {"source": "https://youtu.be/x", "app": "Google Sheets", "goal": "Make a chart",
         "steps": [
          {"n": 1, "t": 7.7, "action": "click", "target_label": "Insert", "target_description": "menu bar item",
           "target_box_2d": [10, 200, 40, 260], "text": "", "keys": "", "expect": "Insert menu opens"},
          {"n": 2, "t": "11.0", "action": "Double-Click", "target_label": "", "target_description": "chart icon",
           "target_box_2d": [-5, 300, 1200, 340], "text": "", "keys": "", "expect": ""},
          {"n": 3, "t": 15, "action": "keyboard_shortcut", "target_label": "", "target_description": "",
           "target_box_2d": [], "text": "", "keys": "cmd+z", "expect": ""}
         ]}
        ```
        """
        let partAnswer = try #require(TutorialTourAnswerParser.parse(answerText))
        #expect(partAnswer.appName == "Google Sheets")
        #expect(partAnswer.goal == "Make a chart")
        #expect(!partAnswer.wasSalvagedFromTruncatedAnswer)
        #expect(partAnswer.steps.count == 3)
        #expect(partAnswer.steps[0].action == .click)
        #expect(partAnswer.steps[0].instructionText == "Click “Insert”")
        #expect(partAnswer.steps[1].videoTimeSeconds == 11.0)
        #expect(partAnswer.steps[1].action == .doubleClick)
        #expect(partAnswer.steps[1].targetBox2D == [0, 300, 1000, 340])
        #expect(partAnswer.steps[2].action == .key)
        #expect(partAnswer.steps[2].targetBox2D == nil)
        #expect(partAnswer.steps[2].instructionText == "Press cmd+z")
    }

    @Test func parsesAnswerWrappedInProse() throws {
        let answerText = #"Here is the tour: {"app": "Excalidraw", "goal": "", "steps": [{"t": 2.5, "action": "click", "target_label": "Rectangle"}]} Hope this helps."#
        let partAnswer = try #require(TutorialTourAnswerParser.parse(answerText))
        #expect(partAnswer.steps.map(\.targetLabel) == ["Rectangle"])
        #expect(partAnswer.steps[0].stepNumber == 1)
    }

    @Test func salvagesCompleteStepsFromTruncatedAnswer() throws {
        // Cut off by the output-length cap in the middle of step 3, with a
        // brace inside a string to make sure strings are respected.
        let truncatedAnswerText = #"{"source": "x", "app": "draw.io", "goal": "Draw a flowchart", "steps": [{"n": 1, "t": 1.0, "action": "click", "target_label": "Shape {A"}, {"n": 2, "t": 4.5, "action": "drag", "target_label": "Connector"}, {"n": 3, "t": 9.0, "action": "cli"#
        let partAnswer = try #require(TutorialTourAnswerParser.parse(truncatedAnswerText))
        #expect(partAnswer.wasSalvagedFromTruncatedAnswer)
        #expect(partAnswer.appName == "draw.io")
        #expect(partAnswer.goal == "Draw a flowchart")
        #expect(partAnswer.steps.map(\.targetLabel) == ["Shape {A", "Connector"])
        #expect(partAnswer.steps[1].action == .drag)
    }

    @Test func rejectsAnswerWithoutSteps() {
        #expect(TutorialTourAnswerParser.parse("I could not see any software in this video.") == nil)
        #expect(TutorialTourAnswerParser.parse(#"{"app": "x"}"#) == nil)
    }

    // MARK: - Stitching parts

    @Test func stitchingKeepsOverlapStepsOnceWithVideoTimes() {
        func step(_ partTimeSeconds: Double, _ targetLabel: String) -> TutorialTourStep {
            TutorialTourStep(stepNumber: 0, videoTimeSeconds: partTimeSeconds, action: .click, targetLabel: targetLabel,
                             targetDescription: "", targetBox2D: nil, typedText: "", keys: "", expectedResult: "",
                             targetCropFileName: nil)
        }
        func answer(_ steps: [TutorialTourStep]) -> TutorialTourPartAnswer {
            TutorialTourPartAnswer(appName: "", goal: "", steps: steps, wasSalvagedFromTruncatedAnswer: false)
        }
        // Part 1 covers 0–94 s, part 2 covers 90–130 s; both saw the 91 s click.
        let stitchedSteps = TutorialTourPartStitcher.stitch([
            .init(partStartSeconds: 90, partDurationSeconds: 40, answer: answer([step(1.0, "Save"), step(20, "Export")])),
            .init(partStartSeconds: 0, partDurationSeconds: 94, answer: answer([step(5, "File"), step(91, "Save")])),
        ])
        #expect(stitchedSteps.map(\.targetLabel) == ["File", "Save", "Export"])
        #expect(stitchedSteps.map(\.videoTimeSeconds) == [5, 91, 110])
        #expect(stitchedSteps.map(\.stepNumber) == [1, 2, 3])
    }

    // MARK: - Captions

    @Test func captionParserDropsRollingDuplicatesAndTags() {
        let webVTTText = """
        WEBVTT
        Kind: captions
        Language: en

        00:00:01.120 --> 00:00:03.590 align:start position:0%
        click<00:00:01.440><c> on</c><00:00:01.600><c> insert</c>

        00:00:03.590 --> 00:00:03.600 align:start position:0%
        click on insert

        00:01:02.000 --> 00:01:04.000
        then choose chart &amp; done
        """
        let captionLines = TutorialCaptionParser.parseWebVTT(webVTTText)
        #expect(captionLines == [
            TutorialCaptionLine(startSeconds: 1.12, text: "click on insert"),
            TutorialCaptionLine(startSeconds: 62, text: "then choose chart & done"),
        ])
        let partLines = TutorialCaptionParser.promptLines(from: captionLines, partStartSeconds: 60, partEndSeconds: 90)
        #expect(partLines == ["[2.0] then choose chart & done"])
    }

    // MARK: - Prompts

    @Test func extractionPromptMentionsCaptionsAndPartsOnlyWhenPresent() {
        let singlePartPrompt = TutorialTourPrompts.extractionPrompt(
            tutorialTitle: "Charts", sourceDescription: "https://youtu.be/\"x\"", partNumber: 1, partCount: 1,
            partStartSeconds: 0, partDurationSeconds: 52, frameWidthInPixels: 1920, frameHeightInPixels: 1080,
            captionPromptLines: []
        )
        #expect(!singlePartPrompt.contains("<captions>"))
        #expect(!singlePartPrompt.contains("part 1 of"))
        #expect(singlePartPrompt.contains("1920x1080"))
        #expect(singlePartPrompt.contains(#""source": "https://youtu.be/'x'""#))

        let secondPartPrompt = TutorialTourPrompts.extractionPrompt(
            tutorialTitle: "Charts", sourceDescription: "x", partNumber: 2, partCount: 3,
            partStartSeconds: 90, partDurationSeconds: 94, frameWidthInPixels: 1280, frameHeightInPixels: 720,
            captionPromptLines: ["[1.0] click insert"]
        )
        #expect(secondPartPrompt.contains("part 2 of 3"))
        #expect(secondPartPrompt.contains("<captions>\n[1.0] click insert\n</captions>"))
    }

    @Test func pointingPromptUsesSquareImageSize() {
        let pointingPrompt = TutorialTourPrompts.pointingPrompt(
            squareImageSideInPixels: 1000, targetLabel: "Insert", targetDescription: "top menu", hasReferenceCrop: true
        )
        #expect(pointingPrompt.contains("1000x1000"))
        #expect(pointingPrompt.contains("SECOND image"))
        #expect(pointingPrompt.contains("“Insert”"))
    }

    // MARK: - Pointing answers and pricing

    @Test func pointParserReadsLastCoordinateObject() {
        #expect(ElorianPointAnswerParser.point(from: #"{"x": 755, "y": 255}"#) == CGPoint(x: 755, y: 255))
        #expect(ElorianPointAnswerParser.point(from: "Looking… {\"note\": 1} final: {\"x\": 12.5, \"y\": 40}") == CGPoint(x: 12.5, y: 40))
        #expect(ElorianPointAnswerParser.point(from: #"{"x": null, "y": null}"#) == nil)
        #expect(ElorianPointAnswerParser.point(from: "not visible") == nil)
    }

    @Test func pricingMatchesPublishedRates() {
        let costInDollars = ElorianPricing.estimatedCostInDollars(
            promptTokens: 1_000_000, cachedPromptTokens: 400_000, completionTokens: 100_000
        )
        #expect(abs(costInDollars - (0.36 + 0.024 + 0.30)) < 0.000001)
    }

    // MARK: - Client

    @Test func clientPollsBackgroundRunUntilCompleted() async throws {
        let stubbedResponses = StubbedElorianResponses([
            (200, #"{"id": "run_1", "object": "agent.run", "status": "queued"}"#),
            (200, #"{"id": "run_1", "status": "completed", "completion": {"choices": [{"finish_reason": "stop", "message": {"content": "{\"steps\": []}"}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "prompt_tokens_details": {"cached_tokens": 0}}}}"#),
        ])
        let elorianClient = ElorianClient(apiKeyProvider: { "elor_sk_test" }, session: stubbedResponses.session)
        let runID = try await elorianClient.startTutorialExtractionRun(fileID: "file-1", prompt: "p", videoFramesPerSecond: 3)
        #expect(runID == "run_1")
        let completion = try await elorianClient.waitForRunCompletion(runID: runID)
        #expect(completion.content == #"{"steps": []}"#)
        #expect(abs(completion.estimatedCostInDollars - 0.0009) < 0.000001)

        let sentRequests = stubbedResponses.recordedRequests()
        #expect(sentRequests.first?.value(forHTTPHeaderField: "Authorization") == "Bearer elor_sk_test")
        #expect(sentRequests.last?.url?.path == "/v1/runs/run_1")
    }

    @Test func clientExplainsExhaustedCredits() async {
        let stubbedResponses = StubbedElorianResponses([
            (429, #"{"error": {"code": "credits_exhausted", "message": "No credits left."}}"#),
        ])
        let elorianClient = ElorianClient(apiKeyProvider: { "elor_sk_test" }, session: stubbedResponses.session)
        do {
            _ = try await elorianClient.startTutorialExtractionRun(fileID: "file-1", prompt: "p", videoFramesPerSecond: 3)
            Issue.record("expected an error")
        } catch {
            #expect(error.localizedDescription.contains("credits are used up"))
            // Exhausted credits are not retried.
            #expect(stubbedResponses.recordedRequests().count == 1)
        }
    }

    @Test func clientRequiresKey() async {
        let elorianClient = ElorianClient(apiKeyProvider: { nil }, session: StubbedElorianResponses([]).session)
        await #expect(throws: ElorianError.self) {
            _ = try await elorianClient.waitForRunCompletion(runID: "run_1")
        }
    }
}

/// Serves canned HTTP responses in order and records the requests.
final class StubbedElorianResponses: @unchecked Sendable {
    let session: URLSession
    private let stubIdentifier = UUID().uuidString

    init(_ responses: [(statusCode: Int, body: String)]) {
        StubbedElorianURLProtocol.register(stubIdentifier: stubIdentifier, responses: responses)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubbedElorianURLProtocol.self]
        configuration.httpAdditionalHeaders = ["X-Stub-Identifier": stubIdentifier]
        session = URLSession(configuration: configuration)
    }

    func recordedRequests() -> [URLRequest] {
        StubbedElorianURLProtocol.recordedRequests(stubIdentifier: stubIdentifier)
    }
}

final class StubbedElorianURLProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var pendingResponsesByStub: [String: [(statusCode: Int, body: String)]] = [:]
    nonisolated(unsafe) private static var requestsByStub: [String: [URLRequest]] = [:]

    static func register(stubIdentifier: String, responses: [(statusCode: Int, body: String)]) {
        lock.lock(); defer { lock.unlock() }
        pendingResponsesByStub[stubIdentifier] = responses
        requestsByStub[stubIdentifier] = []
    }

    static func recordedRequests(stubIdentifier: String) -> [URLRequest] {
        lock.lock(); defer { lock.unlock() }
        return requestsByStub[stubIdentifier] ?? []
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let stubIdentifier = request.value(forHTTPHeaderField: "X-Stub-Identifier") ?? ""
        Self.lock.lock()
        Self.requestsByStub[stubIdentifier, default: []].append(request)
        let nextResponse = Self.pendingResponsesByStub[stubIdentifier]?.isEmpty == false
            ? Self.pendingResponsesByStub[stubIdentifier]!.removeFirst()
            : (statusCode: 500, body: #"{"error": {"message": "no stubbed response left"}}"#)
        Self.lock.unlock()

        let httpResponse = HTTPURLResponse(url: request.url!, statusCode: nextResponse.statusCode, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: httpResponse, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(nextResponse.body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
