//
//  TutorialVideoPreparer.swift
//  TipTour
//
//  Gets a tutorial video ready for Elorian: downloads a YouTube (or other
//  site) link with the user's own yt-dlp, or reads a local file, cuts it
//  into overlapping parts with AVFoundation, and later cuts each step's
//  target out of the video as a reference image.
//
//  Parts are capped at 90 s because one Elorian answer can hold only so
//  many steps; longer parts hit the output cap and lose their ending.
//

import AppKit
import AVFoundation
import Foundation

struct TutorialVideoSource {
    let localVideoFileURL: URL
    let captionsFileURL: URL?
    let title: String
    let sourceDescription: String
}

struct TutorialVideoPart {
    let fileURL: URL
    let startSeconds: Double
    let durationSeconds: Double
    let widthInPixels: Int
    let heightInPixels: Int
}

enum TutorialVideoPreparerError: LocalizedError {
    case ytDlpMissing
    case downloadFailed(String)
    case unsupportedInput
    case unreadableVideo(String)
    case exportFailed(String)

    var errorDescription: String? {
        switch self {
        case .ytDlpMissing:
            return "Downloading from YouTube needs yt-dlp. Install it with “brew install yt-dlp”, or choose a video file instead."
        case let .downloadFailed(detail):
            return "Could not download the video: \(detail.prefix(300))"
        case .unsupportedInput:
            return "Paste a video link (YouTube, Loom, or a direct .mp4) or choose a video file."
        case let .unreadableVideo(detail):
            return "TipTour could not read that video (\(detail)). MP4 and MOV files work best."
        case let .exportFailed(detail):
            return "Could not prepare the video: \(detail.prefix(300))"
        }
    }
}

enum TutorialVideoPreparer {

    static let maximumPartLengthSeconds: Double = 90
    static let partOverlapSeconds: Double = 4

    // MARK: - Source

    static func prepareSource(fromUserInput userInput: String, workDirectoryURL: URL) async throws -> TutorialVideoSource {
        let trimmedInput = userInput.trimmingCharacters(in: .whitespacesAndNewlines)

        let localFileURL: URL? = {
            if trimmedInput.hasPrefix("file://") { return URL(string: trimmedInput) }
            let expandedPath = (trimmedInput as NSString).expandingTildeInPath
            return expandedPath.hasPrefix("/") ? URL(fileURLWithPath: expandedPath) : nil
        }()
        if let localFileURL {
            guard FileManager.default.fileExists(atPath: localFileURL.path) else {
                throw TutorialVideoPreparerError.unreadableVideo("file not found")
            }
            return TutorialVideoSource(
                localVideoFileURL: localFileURL,
                captionsFileURL: nil,
                title: localFileURL.deletingPathExtension().lastPathComponent,
                sourceDescription: localFileURL.lastPathComponent
            )
        }

        guard let remoteURL = URL(string: trimmedInput),
              let scheme = remoteURL.scheme?.lowercased(),
              scheme == "https" || scheme == "http" else {
            throw TutorialVideoPreparerError.unsupportedInput
        }

        let directVideoExtensions: Set<String> = ["mp4", "mov", "m4v"]
        if directVideoExtensions.contains(remoteURL.pathExtension.lowercased()) {
            return try await downloadDirectVideo(from: remoteURL, workDirectoryURL: workDirectoryURL)
        }
        return try await downloadWithYtDlp(from: remoteURL, workDirectoryURL: workDirectoryURL)
    }

    private static func downloadDirectVideo(from remoteURL: URL, workDirectoryURL: URL) async throws -> TutorialVideoSource {
        let (temporaryDownloadURL, urlResponse) = try await URLSession.shared.download(from: remoteURL)
        let statusCode = (urlResponse as? HTTPURLResponse)?.statusCode ?? 200
        guard (200..<300).contains(statusCode) else {
            throw TutorialVideoPreparerError.downloadFailed("HTTP \(statusCode)")
        }
        let localVideoFileURL = workDirectoryURL.appendingPathComponent("video.\(remoteURL.pathExtension.lowercased())")
        try? FileManager.default.removeItem(at: localVideoFileURL)
        try FileManager.default.moveItem(at: temporaryDownloadURL, to: localVideoFileURL)
        return TutorialVideoSource(
            localVideoFileURL: localVideoFileURL,
            captionsFileURL: nil,
            title: remoteURL.deletingPathExtension().lastPathComponent,
            sourceDescription: remoteURL.absoluteString
        )
    }

    /// TipTour does not bundle a downloader; it uses the yt-dlp the user
    /// installed. GUI apps get a minimal PATH, so look in the usual places.
    static func locateYtDlp() -> URL? {
        let homeDirectoryPath = FileManager.default.homeDirectoryForCurrentUser.path
        let candidatePaths = [
            "/opt/homebrew/bin/yt-dlp",
            "/usr/local/bin/yt-dlp",
            "\(homeDirectoryPath)/.local/bin/yt-dlp",
            "/usr/bin/yt-dlp",
        ]
        return candidatePaths.first { FileManager.default.isExecutableFile(atPath: $0) }.map(URL.init(fileURLWithPath:))
    }

    private static func downloadWithYtDlp(from remoteURL: URL, workDirectoryURL: URL) async throws -> TutorialVideoSource {
        guard let ytDlpURL = locateYtDlp() else { throw TutorialVideoPreparerError.ytDlpMissing }

        // H.264 MP4 only (AVFoundation cannot decode VP9/WebM), at most
        // 1080p, video only: Elorian ignores audio anyway.
        let videoFormatSelector = "bv*[ext=mp4][vcodec^=avc1][height<=1080]/bv*[ext=mp4][height<=1080]/b[ext=mp4][height<=1080]/b[ext=mp4]"
        let sharedArguments = ["--no-playlist", "--no-progress", "--write-info-json", "-f", videoFormatSelector,
                               "-o", workDirectoryURL.appendingPathComponent("video.%(ext)s").path]

        // YouTube's default client answered 403 during testing while the
        // embedded-player client returned 1080p, so try that first.
        var downloadResult = try await runProcess(
            executableURL: ytDlpURL,
            arguments: sharedArguments + ["--extractor-args", "youtube:player_client=web_embedded", remoteURL.absoluteString]
        )
        if downloadResult.exitCode != 0 {
            downloadResult = try await runProcess(executableURL: ytDlpURL, arguments: sharedArguments + [remoteURL.absoluteString])
        }
        guard downloadResult.exitCode == 0 else {
            let lastErrorLine = downloadResult.standardError
                .split(separator: "\n")
                .last { $0.contains("ERROR") } ?? Substring(downloadResult.standardError.suffix(300))
            throw TutorialVideoPreparerError.downloadFailed(String(lastErrorLine))
        }

        // Captions are best effort: many tutorials have none.
        _ = try? await runProcess(
            executableURL: ytDlpURL,
            arguments: ["--no-playlist", "--skip-download", "--write-auto-subs", "--write-subs",
                        "--sub-langs", "en.*,en", "--sub-format", "vtt",
                        "-o", workDirectoryURL.appendingPathComponent("captions.%(ext)s").path,
                        remoteURL.absoluteString]
        )

        let workDirectoryFileURLs = (try? FileManager.default.contentsOfDirectory(
            at: workDirectoryURL,
            includingPropertiesForKeys: nil
        )) ?? []
        guard let downloadedVideoFileURL = workDirectoryFileURLs.first(where: { fileURL in
            fileURL.lastPathComponent.hasPrefix("video.") && ["mp4", "mov", "m4v"].contains(fileURL.pathExtension.lowercased())
        }) else {
            throw TutorialVideoPreparerError.downloadFailed("yt-dlp finished but no MP4 was found")
        }
        let captionsFileURL = workDirectoryFileURLs
            .filter { $0.lastPathComponent.hasPrefix("captions.") && $0.pathExtension.lowercased() == "vtt" }
            .sorted { $0.lastPathComponent.count < $1.lastPathComponent.count }
            .first

        var videoTitle = remoteURL.absoluteString
        let infoFileURL = workDirectoryURL.appendingPathComponent("video.info.json")
        if let infoData = try? Data(contentsOf: infoFileURL),
           let infoObject = try? JSONSerialization.jsonObject(with: infoData) as? [String: Any],
           let titleFromInfo = infoObject["title"] as? String, !titleFromInfo.isEmpty {
            videoTitle = titleFromInfo
        }

        return TutorialVideoSource(
            localVideoFileURL: downloadedVideoFileURL,
            captionsFileURL: captionsFileURL,
            title: videoTitle,
            sourceDescription: remoteURL.absoluteString
        )
    }

    private struct ProcessResult {
        let exitCode: Int32
        let standardError: String
    }

    private static func runProcess(executableURL: URL, arguments: [String]) async throws -> ProcessResult {
        let process = Process()
        process.executableURL = executableURL
        process.arguments = arguments
        var processEnvironment = ProcessInfo.processInfo.environment
        processEnvironment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + (processEnvironment["PATH"] ?? "")
        process.environment = processEnvironment

        let standardErrorPipe = Pipe()
        process.standardError = standardErrorPipe
        process.standardOutput = FileHandle.nullDevice

        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                process.terminationHandler = { finishedProcess in
                    let standardErrorData = standardErrorPipe.fileHandleForReading.readDataToEndOfFile()
                    continuation.resume(returning: ProcessResult(
                        exitCode: finishedProcess.terminationStatus,
                        standardError: String(data: standardErrorData, encoding: .utf8) ?? ""
                    ))
                }
                do {
                    try process.run()
                } catch {
                    continuation.resume(throwing: TutorialVideoPreparerError.downloadFailed(error.localizedDescription))
                }
            }
        } onCancel: {
            process.terminate()
        }
    }

    // MARK: - Parts

    static func videoDurationSeconds(of videoFileURL: URL) async throws -> Double {
        let videoAsset = AVURLAsset(url: videoFileURL)
        let reportedDurationSeconds: Double
        do {
            reportedDurationSeconds = CMTimeGetSeconds(try await videoAsset.load(.duration))
        } catch {
            throw TutorialVideoPreparerError.unreadableVideo(error.localizedDescription)
        }
        guard reportedDurationSeconds.isFinite, reportedDurationSeconds > 0 else {
            throw TutorialVideoPreparerError.unreadableVideo("no duration")
        }

        // YouTube's fragmented MP4s end with a zero-length sample stamped at
        // twice the real duration, so AVFoundation reports double the length
        // and parts cut past the real end are blank (Elorian rejects them).
        // The last sample that has a duration marks the true end.
        if let measuredEndSeconds = await lastTimedVideoSampleEndSeconds(of: videoFileURL), measuredEndSeconds > 0.5 {
            return min(reportedDurationSeconds, measuredEndSeconds)
        }
        return reportedDurationSeconds
    }

    /// Reads compressed video samples without decoding (about 0.1 s for a
    /// five-minute 1080p video) and returns where the last real frame ends.
    /// `@concurrent` keeps the synchronous sample loop off the main actor.
    @concurrent
    private nonisolated static func lastTimedVideoSampleEndSeconds(of videoFileURL: URL) async -> Double? {
        let videoAsset = AVURLAsset(url: videoFileURL)
        guard let videoTrack = try? await videoAsset.loadTracks(withMediaType: .video).first,
              let assetReader = try? AVAssetReader(asset: videoAsset) else { return nil }

        let passthroughSampleOutput = AVAssetReaderTrackOutput(track: videoTrack, outputSettings: nil)
        passthroughSampleOutput.alwaysCopiesSampleData = false
        guard assetReader.canAdd(passthroughSampleOutput) else { return nil }
        assetReader.add(passthroughSampleOutput)
        guard assetReader.startReading() else { return nil }

        var lastSampleEndSeconds: Double?
        while let sampleBuffer = passthroughSampleOutput.copyNextSampleBuffer() {
            let presentationSeconds = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sampleBuffer))
            let sampleDurationSeconds = CMTimeGetSeconds(CMSampleBufferGetDuration(sampleBuffer))
            guard presentationSeconds.isFinite, sampleDurationSeconds.isFinite, sampleDurationSeconds > 0 else { continue }
            lastSampleEndSeconds = max(lastSampleEndSeconds ?? 0, presentationSeconds + sampleDurationSeconds)
        }
        return assetReader.status == .completed ? lastSampleEndSeconds : nil
    }

    /// Splits the video into parts of at most 90 s that overlap by 4 s, so
    /// a click on a part boundary is seen whole by one of them. Parts are
    /// re-encoded at no more than 1920×1080 (Elorian's 1080p cap is 200 s).
    static func exportParts(
        of videoFileURL: URL,
        videoDurationSeconds: Double,
        workDirectoryURL: URL
    ) async throws -> [TutorialVideoPart] {
        let videoAsset = AVURLAsset(url: videoFileURL)
        guard let videoTrack = try await videoAsset.loadTracks(withMediaType: .video).first else {
            throw TutorialVideoPreparerError.unreadableVideo("no video track")
        }
        let (naturalSize, preferredTransform) = try await videoTrack.load(.naturalSize, .preferredTransform)
        let displayedSize = naturalSize.applying(preferredTransform)
        let sourceWidthInPixels = Int(abs(displayedSize.width))
        let sourceHeightInPixels = Int(abs(displayedSize.height))
        let sourceFitsIn1080p = max(sourceWidthInPixels, sourceHeightInPixels) <= 1920
            && min(sourceWidthInPixels, sourceHeightInPixels) <= 1080
        let exportPresetName = sourceFitsIn1080p ? AVAssetExportPresetHighestQuality : AVAssetExportPreset1920x1080

        let partCount = max(1, Int(ceil(videoDurationSeconds / maximumPartLengthSeconds)))
        var exportedParts: [TutorialVideoPart] = []

        for partIndex in 0..<partCount {
            try Task.checkCancellation()
            let partStartSeconds = Double(partIndex) * maximumPartLengthSeconds
            let partEndSeconds = min(videoDurationSeconds, partStartSeconds + maximumPartLengthSeconds + partOverlapSeconds)
            let partDurationSeconds = partEndSeconds - partStartSeconds
            guard partDurationSeconds > 0.5 else { continue }

            guard let exportSession = AVAssetExportSession(asset: videoAsset, presetName: exportPresetName) else {
                throw TutorialVideoPreparerError.exportFailed("this video cannot be re-encoded")
            }
            let partFileURL = workDirectoryURL.appendingPathComponent("part-\(partIndex + 1).mp4")
            try? FileManager.default.removeItem(at: partFileURL)
            exportSession.outputURL = partFileURL
            exportSession.outputFileType = .mp4
            exportSession.timeRange = CMTimeRange(
                start: CMTime(seconds: partStartSeconds, preferredTimescale: 600),
                duration: CMTime(seconds: partDurationSeconds, preferredTimescale: 600)
            )
            await exportSession.export()
            guard exportSession.status == .completed else {
                throw TutorialVideoPreparerError.exportFailed(exportSession.error?.localizedDescription ?? "export did not complete")
            }

            let exportedPixelSize = try await pixelSize(of: partFileURL)
            exportedParts.append(TutorialVideoPart(
                fileURL: partFileURL,
                startSeconds: partStartSeconds,
                durationSeconds: partDurationSeconds,
                widthInPixels: exportedPixelSize.width,
                heightInPixels: exportedPixelSize.height
            ))
        }
        return exportedParts
    }

    private static func pixelSize(of videoFileURL: URL) async throws -> (width: Int, height: Int) {
        let videoAsset = AVURLAsset(url: videoFileURL)
        guard let videoTrack = try await videoAsset.loadTracks(withMediaType: .video).first else { return (0, 0) }
        let (naturalSize, preferredTransform) = try await videoTrack.load(.naturalSize, .preferredTransform)
        let displayedSize = naturalSize.applying(preferredTransform)
        return (Int(abs(displayedSize.width)), Int(abs(displayedSize.height)))
    }

    // MARK: - Target crops

    /// Cuts a step's target out of the original video as a PNG, from the
    /// frame at the step's time: that is the frame Elorian checked its box
    /// against, and in zooming tutorials even 0.3 s earlier can be a
    /// different view. Near-blank crops are dropped, since a white patch
    /// only misleads the card and the pointing request.
    static func targetCropPNGData(
        videoFileURL: URL,
        videoTimeSeconds: Double,
        normalizedTargetBox2D: [Double]
    ) async -> Data? {
        guard normalizedTargetBox2D.count == 4 else { return nil }
        let videoAsset = AVURLAsset(url: videoFileURL)
        let imageGenerator = AVAssetImageGenerator(asset: videoAsset)
        imageGenerator.appliesPreferredTrackTransform = true
        imageGenerator.requestedTimeToleranceBefore = CMTime(seconds: 0.1, preferredTimescale: 600)
        imageGenerator.requestedTimeToleranceAfter = CMTime(seconds: 0.1, preferredTimescale: 600)

        guard let (frameImage, _) = try? await imageGenerator.image(at: CMTime(seconds: max(0, videoTimeSeconds), preferredTimescale: 600)) else {
            return nil
        }

        let frameWidth = CGFloat(frameImage.width)
        let frameHeight = CGFloat(frameImage.height)
        let boxTop = CGFloat(normalizedTargetBox2D[0]) / 1000 * frameHeight
        let boxLeft = CGFloat(normalizedTargetBox2D[1]) / 1000 * frameWidth
        let boxBottom = CGFloat(normalizedTargetBox2D[2]) / 1000 * frameHeight
        let boxRight = CGFloat(normalizedTargetBox2D[3]) / 1000 * frameWidth
        guard boxRight > boxLeft, boxBottom > boxTop else { return nil }

        // 20% padding gives the element some context; never crop smaller
        // than 56 px so tiny icons stay recognisable.
        let paddedWidth = max(56, (boxRight - boxLeft) * 1.4)
        let paddedHeight = max(56, (boxBottom - boxTop) * 1.4)
        let cropRect = CGRect(
            x: (boxLeft + boxRight) / 2 - paddedWidth / 2,
            y: (boxTop + boxBottom) / 2 - paddedHeight / 2,
            width: paddedWidth,
            height: paddedHeight
        ).intersection(CGRect(x: 0, y: 0, width: frameWidth, height: frameHeight)).integral

        guard !cropRect.isEmpty, let croppedImage = frameImage.cropping(to: cropRect) else { return nil }
        guard luminanceStandardDeviation(of: croppedImage) >= minimumCropLuminanceStandardDeviation else { return nil }
        return NSBitmapImageRep(cgImage: croppedImage).representation(using: .png, properties: [:])
    }

    /// Below this, a crop is a flat patch (blank page, empty panel) rather
    /// than a control. Real buttons and icons in tested tutorials measured 25+.
    private static let minimumCropLuminanceStandardDeviation = 12.0

    private static func luminanceStandardDeviation(of image: CGImage) -> Double {
        let sampleSide = 48
        var grayscalePixels = [UInt8](repeating: 0, count: sampleSide * sampleSide)
        let didDraw = grayscalePixels.withUnsafeMutableBytes { pixelBuffer -> Bool in
            guard let grayscaleContext = CGContext(
                data: pixelBuffer.baseAddress,
                width: sampleSide,
                height: sampleSide,
                bitsPerComponent: 8,
                bytesPerRow: sampleSide,
                space: CGColorSpaceCreateDeviceGray(),
                bitmapInfo: CGImageAlphaInfo.none.rawValue
            ) else { return false }
            grayscaleContext.draw(image, in: CGRect(x: 0, y: 0, width: sampleSide, height: sampleSide))
            return true
        }
        guard didDraw else { return .infinity }
        let pixelValues = grayscalePixels.map(Double.init)
        let meanValue = pixelValues.reduce(0, +) / Double(pixelValues.count)
        let variance = pixelValues.reduce(0) { runningSum, pixelValue in
            runningSum + (pixelValue - meanValue) * (pixelValue - meanValue)
        } / Double(pixelValues.count)
        return variance.squareRoot()
    }
}
