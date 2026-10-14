//
//  ElorianClient.swift
//  TipTour
//
//  Keychain-authenticated client for Elorian's OpenAI-compatible API
//  (https://api.elorian.ai/v1). Elorian watches tutorial videos for
//  "Learn from a video" and, when local grounding cannot find an icon-only
//  target, points at it on a screenshot.
//
//  Elorian is an agent, not a bare model: a video question runs Python in
//  a hosted sandbox for minutes. Extraction therefore uses background runs
//  that are polled, instead of holding one HTTP request open that long.
//

import Foundation

nonisolated enum ElorianError: LocalizedError {
    case missingAPIKey
    case http(status: Int, code: String?, message: String)
    case runFailed(status: String, message: String)
    case fileProcessingFailed(String)
    case malformed(String)
    case timedOut(String)

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "No Elorian API key. Add one in Settings → Models to learn from videos."
        case let .http(status, code, message):
            if code == "credits_exhausted" || code == "insufficient_quota" {
                return "Elorian credits are used up. Top up the account, then try again."
            }
            if status == 401 {
                return "Elorian rejected the API key. Check it in Settings → Models."
            }
            return "Elorian returned \(status)\(code.map { " (\($0))" } ?? ""): \(message.prefix(300))"
        case let .runFailed(status, message):
            return "Elorian's run \(status): \(message.prefix(300))"
        case let .fileProcessingFailed(detail):
            return "Elorian could not read the video: \(detail.prefix(300))"
        case let .malformed(detail):
            return "Elorian sent something unreadable: \(detail.prefix(300))"
        case let .timedOut(detail):
            return "Elorian took too long: \(detail)"
        }
    }
}

/// The final answer of one Elorian request.
nonisolated struct ElorianCompletion {
    let content: String
    let finishReason: String?
    let estimatedCostInDollars: Double
}

nonisolated struct ElorianPointResult {
    /// Center of the target in the coordinate space of the image that was
    /// sent, or nil when Elorian said the target is not visible.
    let pointInSentImagePixels: CGPoint?
    let estimatedCostInDollars: Double
    let milliseconds: Int
}

actor ElorianClient {
    static let baseURL = URL(string: "https://api.elorian.ai/v1")!
    static let model = "elorian-1-agent"

    static let shared = ElorianClient()

    private let session: URLSession
    private let apiKeyProvider: @MainActor @Sendable () -> String?

    init(
        apiKeyProvider: @escaping @MainActor @Sendable () -> String? = { KeychainStore.elorianAPIKey },
        session: URLSession? = nil
    ) {
        self.apiKeyProvider = apiKeyProvider
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.default
            // Uploads of a 90 s 1080p part can take a while on slow links;
            // every other request returns quickly because runs are polled.
            configuration.timeoutIntervalForRequest = 120
            configuration.timeoutIntervalForResource = 900
            self.session = URLSession(configuration: configuration)
        }
    }

    // MARK: - Files

    /// Uploads a video with `POST /v1/files`. Returns the file ID to
    /// reference as `file://<id>` once `waitUntilFileIsReady` returns. The
    /// two are separate so a caller always learns the ID it must delete.
    func uploadVideo(at videoFileURL: URL) async throws -> String {
        let apiKey = try await requireAPIKey()
        let videoData = try Data(contentsOf: videoFileURL)

        let multipartBoundary = "TipTourBoundary\(UUID().uuidString)"
        var multipartBody = Data()
        func appendText(_ text: String) { multipartBody.append(Data(text.utf8)) }
        appendText("--\(multipartBoundary)\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nvision\r\n")
        appendText("--\(multipartBoundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(videoFileURL.lastPathComponent)\"\r\nContent-Type: video/mp4\r\n\r\n")
        multipartBody.append(videoData)
        appendText("\r\n--\(multipartBoundary)--\r\n")

        var uploadRequest = URLRequest(url: Self.baseURL.appendingPathComponent("files"))
        uploadRequest.httpMethod = "POST"
        uploadRequest.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        uploadRequest.setValue("multipart/form-data; boundary=\(multipartBoundary)", forHTTPHeaderField: "Content-Type")

        let uploadResponseObject = try await sendWithRetries(uploadRequest, body: multipartBody)
        guard let fileID = uploadResponseObject["id"] as? String else {
            throw ElorianError.malformed("upload response had no file id")
        }
        return fileID
    }

    func waitUntilFileIsReady(fileID: String) async throws {
        let deadline = Date().addingTimeInterval(10 * 60)
        while Date() < deadline {
            try Task.checkCancellation()
            let fileObject = try await getJSON(path: "files/\(fileID)")
            let fileStatus = fileObject["status"] as? String ?? ""
            if fileStatus == "ready" { return }
            if fileStatus == "failed" || fileStatus == "error" {
                throw ElorianError.fileProcessingFailed(Self.errorMessage(in: fileObject) ?? fileStatus)
            }
            try await Task.sleep(nanoseconds: 1_500_000_000)
        }
        throw ElorianError.timedOut("the uploaded video was not ready after 10 minutes")
    }

    /// Deletes an uploaded file. Elorian keeps uploads until deleted and has
    /// no published retention terms yet, so TipTour always cleans up.
    func deleteFile(fileID: String) async {
        guard let apiKey = await apiKeyProvider(), !apiKey.isEmpty else { return }
        var deleteRequest = URLRequest(url: Self.baseURL.appendingPathComponent("files/\(fileID)"))
        deleteRequest.httpMethod = "DELETE"
        deleteRequest.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        _ = try? await session.data(for: deleteRequest)
    }

    // MARK: - Tutorial extraction runs

    /// Starts a background agent run that watches one uploaded video part.
    /// Returns the run ID to poll with `waitForRunCompletion`.
    func startTutorialExtractionRun(fileID: String, prompt: String, videoFramesPerSecond: Double) async throws -> String {
        let requestBody: [String: Any] = [
            "model": Self.model,
            "reasoning_effort": "medium",
            "video_fps": videoFramesPerSecond,
            "background": true,
            "messages": [[
                "role": "user",
                "content": [
                    ["type": "video_url", "video_url": ["url": "file://\(fileID)"]],
                    ["type": "text", "text": prompt],
                ],
            ]],
        ]
        let runObject = try await postJSON(path: "chat/completions", body: requestBody)
        guard let runID = runObject["id"] as? String else {
            throw ElorianError.malformed("background run response had no id")
        }
        return runID
    }

    /// Polls `GET /v1/runs/{id}` until the run finishes. A tutorial part
    /// usually takes 2–12 minutes.
    func waitForRunCompletion(runID: String, maximumWaitSeconds: Double = 40 * 60) async throws -> ElorianCompletion {
        let deadline = Date().addingTimeInterval(maximumWaitSeconds)
        while Date() < deadline {
            try Task.checkCancellation()
            let runObject = try await getJSON(path: "runs/\(runID)")
            let runStatus = runObject["status"] as? String ?? ""
            switch runStatus {
            case "queued", "in_progress", "running", "":
                try await Task.sleep(nanoseconds: 4_000_000_000)
            case "completed":
                guard let completionObject = runObject["completion"] as? [String: Any] else {
                    throw ElorianError.malformed("completed run had no completion")
                }
                return try Self.completion(from: completionObject)
            default:
                throw ElorianError.runFailed(status: runStatus, message: Self.errorMessage(in: runObject) ?? "no detail")
            }
        }
        throw ElorianError.timedOut("the run did not finish within \(Int(maximumWaitSeconds / 60)) minutes")
    }

    func cancelRun(runID: String) async {
        guard let apiKey = await apiKeyProvider(), !apiKey.isEmpty else { return }
        var cancelRequest = URLRequest(url: Self.baseURL.appendingPathComponent("runs/\(runID)/cancel"))
        cancelRequest.httpMethod = "POST"
        cancelRequest.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        _ = try? await session.data(for: cancelRequest)
    }

    // MARK: - Pointing

    /// Fast-mode pointing: `tool_choice: "none"` turns the agent loop off,
    /// so one screenshot question takes about 5 s instead of about 24 s.
    /// The screenshot must already be resized to a square (see
    /// `TutorialTourPrompts.pointingPrompt`).
    func locateTarget(
        squareScreenshotJPEGData: Data,
        squareImageSideInPixels: Int,
        referenceCropPNGData: Data?,
        targetLabel: String,
        targetDescription: String
    ) async throws -> ElorianPointResult {
        let startedAt = Date()
        var contentParts: [[String: Any]] = [[
            "type": "image_url",
            "image_url": ["url": "data:image/jpeg;base64,\(squareScreenshotJPEGData.base64EncodedString())"],
        ]]
        if let referenceCropPNGData {
            contentParts.append([
                "type": "image_url",
                "image_url": ["url": "data:image/png;base64,\(referenceCropPNGData.base64EncodedString())"],
            ])
        }
        contentParts.append([
            "type": "text",
            "text": TutorialTourPrompts.pointingPrompt(
                squareImageSideInPixels: squareImageSideInPixels,
                targetLabel: targetLabel,
                targetDescription: targetDescription,
                hasReferenceCrop: referenceCropPNGData != nil
            ),
        ])

        let requestBody: [String: Any] = [
            "model": Self.model,
            "reasoning_effort": "low",
            "tool_choice": "none",
            "max_completion_tokens": 600,
            "messages": [["role": "user", "content": contentParts]],
        ]
        let completionObject = try await postJSON(path: "chat/completions", body: requestBody)
        let completion = try Self.completion(from: completionObject)
        return ElorianPointResult(
            pointInSentImagePixels: ElorianPointAnswerParser.point(from: completion.content),
            estimatedCostInDollars: completion.estimatedCostInDollars,
            milliseconds: Int(Date().timeIntervalSince(startedAt) * 1000)
        )
    }

    // MARK: - HTTP

    private func requireAPIKey() async throws -> String {
        guard let apiKey = await apiKeyProvider(), !apiKey.isEmpty else { throw ElorianError.missingAPIKey }
        return apiKey
    }

    private func getJSON(path: String) async throws -> [String: Any] {
        let apiKey = try await requireAPIKey()
        var getRequest = URLRequest(url: Self.baseURL.appendingPathComponent(path))
        getRequest.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        return try await sendWithRetries(getRequest, body: nil)
    }

    private func postJSON(path: String, body: [String: Any]) async throws -> [String: Any] {
        let apiKey = try await requireAPIKey()
        var postRequest = URLRequest(url: Self.baseURL.appendingPathComponent(path))
        postRequest.httpMethod = "POST"
        postRequest.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        postRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let bodyData = try JSONSerialization.data(withJSONObject: body)
        return try await sendWithRetries(postRequest, body: bodyData)
    }

    /// Retries rate limits (the account allows 8 concurrent requests) and
    /// transient server errors, honouring `retry-after`.
    private func sendWithRetries(_ request: URLRequest, body: Data?) async throws -> [String: Any] {
        var attemptNumber = 0
        while true {
            attemptNumber += 1
            try Task.checkCancellation()
            let (responseData, urlResponse): (Data, URLResponse)
            if let body {
                (responseData, urlResponse) = try await session.upload(for: request, from: body)
            } else {
                (responseData, urlResponse) = try await session.data(for: request)
            }
            let statusCode = (urlResponse as? HTTPURLResponse)?.statusCode ?? -1
            // Long non-streamed runs pad with whitespace keep-alives; JSON
            // parsing ignores leading whitespace, so no stripping is needed.
            let responseObject = (try? JSONSerialization.jsonObject(with: responseData)) as? [String: Any] ?? [:]

            if (200..<300).contains(statusCode) { return responseObject }

            let errorCode = Self.errorCode(in: responseObject)
            let isRetryable = statusCode == 429 && errorCode != "credits_exhausted" && errorCode != "insufficient_quota"
                || statusCode == 502 || statusCode == 503
            if isRetryable && attemptNumber < 5 {
                let retryAfterSeconds = (urlResponse as? HTTPURLResponse)?
                    .value(forHTTPHeaderField: "retry-after")
                    .flatMap(Double.init) ?? Double(attemptNumber * 5)
                try await Task.sleep(nanoseconds: UInt64(min(retryAfterSeconds, 60) * 1_000_000_000))
                continue
            }

            let fallbackMessage = String(data: responseData.prefix(300), encoding: .utf8) ?? ""
            throw ElorianError.http(
                status: statusCode,
                code: errorCode,
                message: Self.errorMessage(in: responseObject) ?? fallbackMessage
            )
        }
    }

    private static func completion(from completionObject: [String: Any]) throws -> ElorianCompletion {
        guard let firstChoice = (completionObject["choices"] as? [[String: Any]])?.first,
              let message = firstChoice["message"] as? [String: Any],
              let content = message["content"] as? String else {
            throw ElorianError.malformed("completion had no message content")
        }
        let usage = completionObject["usage"] as? [String: Any] ?? [:]
        let promptTokens = (usage["prompt_tokens"] as? NSNumber)?.intValue ?? 0
        let completionTokens = (usage["completion_tokens"] as? NSNumber)?.intValue ?? 0
        let cachedPromptTokens = ((usage["prompt_tokens_details"] as? [String: Any])?["cached_tokens"] as? NSNumber)?.intValue ?? 0
        return ElorianCompletion(
            content: content,
            finishReason: firstChoice["finish_reason"] as? String,
            estimatedCostInDollars: ElorianPricing.estimatedCostInDollars(
                promptTokens: promptTokens,
                cachedPromptTokens: cachedPromptTokens,
                completionTokens: completionTokens
            )
        )
    }

    private static func errorMessage(in responseObject: [String: Any]) -> String? {
        if let errorObject = responseObject["error"] as? [String: Any] {
            return errorObject["message"] as? String
        }
        return responseObject["error"] as? String
    }

    private static func errorCode(in responseObject: [String: Any]) -> String? {
        (responseObject["error"] as? [String: Any])?["code"] as? String
    }
}
