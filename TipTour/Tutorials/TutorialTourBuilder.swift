//
//  TutorialTourBuilder.swift
//  TipTour
//
//  Turns a tutorial video into a saved TutorialTour:
//  download/read → cut into ≤90 s parts → upload each part to Elorian →
//  one background run per part (at most two at a time) → stitch the steps →
//  cut a reference crop per step → save.
//
//  Every uploaded part is deleted from Elorian afterwards, also when the
//  build fails or is cancelled.
//

import Foundation

enum TutorialTourBuilderError: LocalizedError {
    case noStepsFound(String)

    var errorDescription: String? {
        switch self {
        case let .noStepsFound(detail):
            return "Elorian did not find any steps in this video. \(detail)"
        }
    }
}

enum TutorialTourBuilder {

    /// Elorian's account limit is 8 concurrent requests; two parts at a
    /// time keeps room for pointing requests during playback.
    private static let maximumConcurrentParts = 2
    /// Frames per second Elorian samples from each part. Its own agent
    /// re-reads full-resolution frames where it needs precision.
    private static let videoFramesPerSecond = 3.0

    static func buildTour(
        fromUserInput userInput: String,
        onProgress: @escaping @MainActor (String) -> Void
    ) async throws -> TutorialTour {
        let workDirectoryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("TipTourTutorial-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: workDirectoryURL, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: workDirectoryURL) }

        onProgress("Getting the video…")
        let videoSource = try await TutorialVideoPreparer.prepareSource(
            fromUserInput: userInput,
            workDirectoryURL: workDirectoryURL
        )
        let videoDurationSeconds = try await TutorialVideoPreparer.videoDurationSeconds(of: videoSource.localVideoFileURL)

        onProgress("Preparing the video…")
        let videoParts = try await TutorialVideoPreparer.exportParts(
            of: videoSource.localVideoFileURL,
            videoDurationSeconds: videoDurationSeconds,
            workDirectoryURL: workDirectoryURL
        )

        let captionLines: [TutorialCaptionLine] = videoSource.captionsFileURL
            .flatMap { try? String(contentsOf: $0, encoding: .utf8) }
            .map(TutorialCaptionParser.parseWebVTT) ?? []

        let partCount = videoParts.count
        onProgress(partCount == 1
            ? "Elorian is watching the video…"
            : "Elorian is watching \(partCount) parts…")

        var answeredParts: [TutorialTourPartStitcher.AnsweredPart] = []
        var totalEstimatedCostInDollars = 0.0
        var unreadableAnswerPreviews: [String] = []
        var finishedPartCount = 0

        try await withThrowingTaskGroup(of: (TutorialTourPartStitcher.AnsweredPart?, Double, String?).self) { partTaskGroup in
            var nextPartIndex = 0

            func addNextPartTask() {
                guard nextPartIndex < videoParts.count else { return }
                let videoPart = videoParts[nextPartIndex]
                let partNumber = nextPartIndex + 1
                nextPartIndex += 1
                partTaskGroup.addTask {
                    do {
                        return try await watchPart(
                            videoPart,
                            partNumber: partNumber,
                            partCount: partCount,
                            tutorialTitle: videoSource.title,
                            sourceDescription: videoSource.sourceDescription,
                            captionLines: captionLines
                        )
                    } catch let elorianError as ElorianError {
                        // One part Elorian could not watch leaves a gap in
                        // the tour rather than failing the whole build. Key,
                        // credit, and rate problems affect every part, so
                        // those still stop the build.
                        switch elorianError {
                        case .runFailed, .malformed, .timedOut, .fileProcessingFailed:
                            return (nil, 0, "part \(partNumber) failed: \(elorianError.localizedDescription)")
                        case .missingAPIKey, .http:
                            throw elorianError
                        }
                    }
                }
            }

            for _ in 0..<min(maximumConcurrentParts, videoParts.count) { addNextPartTask() }

            while let (answeredPart, partCostInDollars, unreadableAnswerPreview) = try await partTaskGroup.next() {
                totalEstimatedCostInDollars += partCostInDollars
                if let answeredPart { answeredParts.append(answeredPart) }
                if let unreadableAnswerPreview { unreadableAnswerPreviews.append(unreadableAnswerPreview) }
                finishedPartCount += 1
                if finishedPartCount < partCount {
                    onProgress("Elorian watched \(finishedPartCount) of \(partCount) parts…")
                }
                addNextPartTask()
            }
        }

        let stitchedSteps = TutorialTourPartStitcher.stitch(answeredParts)
        guard !stitchedSteps.isEmpty else {
            let detail = unreadableAnswerPreviews.first.map { "Its answer began: \($0)" } ?? "Try a video that shows the clicks on screen."
            throw TutorialTourBuilderError.noStepsFound(detail)
        }

        onProgress("Saving \(stitchedSteps.count) steps…")
        var stepsWithCrops = stitchedSteps
        var targetCropPNGDataByFileName: [String: Data] = [:]
        for stepIndex in stepsWithCrops.indices {
            try Task.checkCancellation()
            let tutorialTourStep = stepsWithCrops[stepIndex]
            guard tutorialTourStep.hasUsableTargetBox, let targetBox2D = tutorialTourStep.targetBox2D else { continue }
            if let cropPNGData = await TutorialVideoPreparer.targetCropPNGData(
                videoFileURL: videoSource.localVideoFileURL,
                videoTimeSeconds: tutorialTourStep.videoTimeSeconds,
                normalizedTargetBox2D: targetBox2D
            ) {
                let cropFileName = "step-\(tutorialTourStep.stepNumber).png"
                targetCropPNGDataByFileName[cropFileName] = cropPNGData
                stepsWithCrops[stepIndex].targetCropFileName = cropFileName
            }
        }

        let firstAnswerWithApp = answeredParts.sorted { $0.partStartSeconds < $1.partStartSeconds }.first { !$0.answer.appName.isEmpty }
        let firstAnswerWithGoal = answeredParts.sorted { $0.partStartSeconds < $1.partStartSeconds }.first { !$0.answer.goal.isEmpty }
        let tour = TutorialTour(
            id: "tour-\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(6).lowercased())",
            title: videoSource.title,
            sourceDescription: videoSource.sourceDescription,
            appName: firstAnswerWithApp?.answer.appName ?? "",
            goal: firstAnswerWithGoal?.answer.goal ?? "",
            createdAt: Date(),
            videoDurationSeconds: videoDurationSeconds,
            estimatedCostInDollars: totalEstimatedCostInDollars,
            steps: stepsWithCrops
        )
        try TutorialTourLibrary.save(tour, targetCropPNGDataByFileName: targetCropPNGDataByFileName)
        return tour
    }

    /// Uploads one part, waits for Elorian's answer, and deletes the upload
    /// whatever happens. Returns the parsed answer (nil if unreadable), its
    /// cost, and a preview of an unreadable answer for the error message.
    private static func watchPart(
        _ videoPart: TutorialVideoPart,
        partNumber: Int,
        partCount: Int,
        tutorialTitle: String,
        sourceDescription: String,
        captionLines: [TutorialCaptionLine]
    ) async throws -> (TutorialTourPartStitcher.AnsweredPart?, Double, String?) {
        let elorianClient = ElorianClient.shared
        let uploadedFileID = try await elorianClient.uploadVideo(at: videoPart.fileURL)

        let extractionPrompt = TutorialTourPrompts.extractionPrompt(
            tutorialTitle: tutorialTitle,
            sourceDescription: sourceDescription,
            partNumber: partNumber,
            partCount: partCount,
            partStartSeconds: videoPart.startSeconds,
            partDurationSeconds: videoPart.durationSeconds,
            frameWidthInPixels: videoPart.widthInPixels,
            frameHeightInPixels: videoPart.heightInPixels,
            captionPromptLines: TutorialCaptionParser.promptLines(
                from: captionLines,
                partStartSeconds: videoPart.startSeconds,
                partEndSeconds: videoPart.startSeconds + videoPart.durationSeconds
            )
        )

        var startedRunID: String?
        do {
            try await elorianClient.waitUntilFileIsReady(fileID: uploadedFileID)
            let runID = try await elorianClient.startTutorialExtractionRun(
                fileID: uploadedFileID,
                prompt: extractionPrompt,
                videoFramesPerSecond: videoFramesPerSecond
            )
            startedRunID = runID
            let completion = try await elorianClient.waitForRunCompletion(runID: runID)
            await elorianClient.deleteFile(fileID: uploadedFileID)

            guard let partAnswer = TutorialTourAnswerParser.parse(completion.content) else {
                return (nil, completion.estimatedCostInDollars, String(completion.content.prefix(160)))
            }
            let answeredPart = TutorialTourPartStitcher.AnsweredPart(
                partStartSeconds: videoPart.startSeconds,
                partDurationSeconds: videoPart.durationSeconds,
                answer: partAnswer
            )
            return (answeredPart, completion.estimatedCostInDollars, nil)
        } catch {
            if let startedRunID { await elorianClient.cancelRun(runID: startedRunID) }
            await elorianClient.deleteFile(fileID: uploadedFileID)
            throw error
        }
    }
}
