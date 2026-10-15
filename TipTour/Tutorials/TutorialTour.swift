//
//  TutorialTour.swift
//  TipTour
//
//  A tutorial tour is a step list Elorian extracted from a screen-recorded
//  tutorial video. This file holds the plain data model plus the pure
//  helpers around it: parsing Elorian's JSON answer (including answers cut
//  off by the output-length cap), stitching the answers for each video part
//  back into one tour, reading YouTube captions, and the prompts. Nothing
//  here touches AppKit, so it is unit-tested outside Xcode by
//  scripts/test-tutorials.sh.
//

import Foundation

// MARK: - Model

nonisolated enum TutorialTourStepAction: String, Codable, CaseIterable {
    case click
    case doubleClick = "double_click"
    case rightClick = "right_click"
    case type
    case key
    case scroll
    case drag
    case wait

    /// Elorian usually answers with the snake_case names from the prompt,
    /// but tolerate the spellings models drift into.
    static func parsed(from rawAction: String?) -> TutorialTourStepAction {
        let normalizedAction = (rawAction ?? "")
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
            .replacingOccurrences(of: " ", with: "_")
        switch normalizedAction {
        case "click", "left_click", "tap", "select": return .click
        case "double_click", "doubleclick": return .doubleClick
        case "right_click", "rightclick", "context_click": return .rightClick
        case "type", "typing", "input", "enter_text": return .type
        case "key", "keys", "shortcut", "keyboard_shortcut", "press", "press_key", "hotkey": return .key
        case "scroll", "scroll_up", "scroll_down": return .scroll
        case "drag", "drag_and_drop": return .drag
        default: return .wait
        }
    }

    /// Steps the user completes with the mouse on a specific on-screen target.
    var needsPointerTarget: Bool {
        switch self {
        case .click, .doubleClick, .rightClick, .drag: return true
        case .type, .key, .scroll, .wait: return false
        }
    }
}

nonisolated struct TutorialTourStep: Codable, Equatable, Identifiable {
    var id: Int { stepNumber }

    var stepNumber: Int
    /// Seconds into the ORIGINAL video (after stitching parts back together).
    var videoTimeSeconds: Double
    var action: TutorialTourStepAction
    var targetLabel: String
    var targetDescription: String
    /// [y1, x1, y2, x2] normalized 0–1000 on the video frame at `videoTimeSeconds`.
    var targetBox2D: [Double]?
    var typedText: String
    var keys: String
    var expectedResult: String
    /// File name of the target crop cut from the video, inside the tour's folder.
    var targetCropFileName: String?

    /// Short instruction for the pointer bubble and the tour card.
    var instructionText: String {
        let quotedLabel = targetLabel.isEmpty ? "" : " “\(targetLabel)”"
        switch action {
        case .click:
            return targetLabel.isEmpty ? "Click here" : "Click\(quotedLabel)"
        case .doubleClick:
            return targetLabel.isEmpty ? "Double-click here" : "Double-click\(quotedLabel)"
        case .rightClick:
            return targetLabel.isEmpty ? "Right-click here" : "Right-click\(quotedLabel)"
        case .type:
            return typedText.isEmpty ? "Type your text" : "Type “\(typedText)”"
        case .key:
            return keys.isEmpty ? "Press the shortcut" : "Press \(keys)"
        case .scroll:
            return targetLabel.isEmpty ? "Scroll" : "Scroll\(quotedLabel)"
        case .drag:
            return targetLabel.isEmpty ? "Drag here" : "Drag\(quotedLabel)"
        case .wait:
            return expectedResult.isEmpty ? "Watch the screen" : expectedResult
        }
    }

    var hasUsableTargetBox: Bool {
        guard let targetBox2D, targetBox2D.count == 4 else { return false }
        return targetBox2D[2] > targetBox2D[0] && targetBox2D[3] > targetBox2D[1]
    }
}

nonisolated struct TutorialTour: Codable, Equatable, Identifiable {
    var id: String
    var title: String
    /// The link or file name the user gave TipTour.
    var sourceDescription: String
    var appName: String
    var goal: String
    var createdAt: Date
    var videoDurationSeconds: Double
    var estimatedCostInDollars: Double
    var steps: [TutorialTourStep]
}

// MARK: - Parsing Elorian's answer

/// One video part's answer, with step times still relative to that part.
nonisolated struct TutorialTourPartAnswer: Equatable {
    var appName: String
    var goal: String
    var steps: [TutorialTourStep]
    /// True when the answer hit the output-length cap and only the complete
    /// steps before the cut were kept.
    var wasSalvagedFromTruncatedAnswer: Bool
}

nonisolated enum TutorialTourAnswerParser {

    static func parse(_ answerText: String) -> TutorialTourPartAnswer? {
        let unfencedAnswerText = stripCodeFences(answerText)

        if let wholeObject = jsonObject(from: unfencedAnswerText) {
            return partAnswer(from: wholeObject, wasSalvagedFromTruncatedAnswer: false)
        }

        // Models sometimes wrap the JSON in a sentence: take the outermost braces.
        if let firstBraceIndex = unfencedAnswerText.firstIndex(of: "{"),
           let lastBraceIndex = unfencedAnswerText.lastIndex(of: "}"),
           firstBraceIndex < lastBraceIndex,
           let embeddedObject = jsonObject(from: String(unfencedAnswerText[firstBraceIndex...lastBraceIndex])) {
            return partAnswer(from: embeddedObject, wasSalvagedFromTruncatedAnswer: false)
        }

        return salvageTruncatedAnswer(unfencedAnswerText)
    }

    static func stripCodeFences(_ text: String) -> String {
        var trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmedText.hasPrefix("```") {
            if let firstNewlineIndex = trimmedText.firstIndex(of: "\n") {
                trimmedText = String(trimmedText[trimmedText.index(after: firstNewlineIndex)...])
            } else {
                trimmedText = String(trimmedText.dropFirst(3))
            }
        }
        if trimmedText.hasSuffix("```") {
            trimmedText = String(trimmedText.dropLast(3))
        }
        return trimmedText.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Recover the complete step objects from an answer that was cut off
    /// mid-JSON. Long tutorials hit Elorian's output cap; the steps before
    /// the cut are still correct and worth keeping.
    static func salvageTruncatedAnswer(_ text: String) -> TutorialTourPartAnswer? {
        guard let stepsKeyRange = text.range(of: "\"steps\""),
              let stepsArrayStartIndex = text[stepsKeyRange.upperBound...].firstIndex(of: "[") else {
            return nil
        }

        let completeStepObjectTexts = completeTopLevelObjectTexts(
            in: text[text.index(after: stepsArrayStartIndex)...]
        )
        let salvagedStepDictionaries = completeStepObjectTexts.compactMap { jsonObject(from: $0) }
        guard !salvagedStepDictionaries.isEmpty else { return nil }

        // The header before "steps" holds app/goal; close it to read them.
        let headerText = String(text[..<stepsKeyRange.lowerBound])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let closedHeaderText = headerText.hasSuffix(",")
            ? String(headerText.dropLast()) + "}"
            : headerText + "}"
        var salvagedObject = jsonObject(from: closedHeaderText) ?? [:]
        salvagedObject["steps"] = salvagedStepDictionaries
        return partAnswer(from: salvagedObject, wasSalvagedFromTruncatedAnswer: true)
    }

    /// Scans for balanced `{...}` objects at the top level of a JSON array
    /// body, respecting strings and escapes. Stops at the closing `]` or at
    /// the first incomplete object.
    static func completeTopLevelObjectTexts(in arrayBody: Substring) -> [String] {
        var objectTexts: [String] = []
        var currentObjectStartIndex: Substring.Index?
        var braceDepth = 0
        var isInsideString = false
        var previousCharacterWasEscape = false

        var characterIndex = arrayBody.startIndex
        while characterIndex < arrayBody.endIndex {
            let character = arrayBody[characterIndex]
            if isInsideString {
                if previousCharacterWasEscape {
                    previousCharacterWasEscape = false
                } else if character == "\\" {
                    previousCharacterWasEscape = true
                } else if character == "\"" {
                    isInsideString = false
                }
            } else {
                switch character {
                case "\"":
                    isInsideString = true
                case "{":
                    if braceDepth == 0 { currentObjectStartIndex = characterIndex }
                    braceDepth += 1
                case "}":
                    braceDepth -= 1
                    if braceDepth == 0, let objectStartIndex = currentObjectStartIndex {
                        objectTexts.append(String(arrayBody[objectStartIndex...characterIndex]))
                        currentObjectStartIndex = nil
                    }
                case "]" where braceDepth == 0:
                    return objectTexts
                default:
                    break
                }
            }
            characterIndex = arrayBody.index(after: characterIndex)
        }
        return objectTexts
    }

    static func partAnswer(
        from answerObject: [String: Any],
        wasSalvagedFromTruncatedAnswer: Bool
    ) -> TutorialTourPartAnswer? {
        guard let rawStepDictionaries = answerObject["steps"] as? [[String: Any]] else { return nil }
        let parsedSteps = rawStepDictionaries.enumerated().compactMap { stepOffset, rawStepDictionary in
            step(from: rawStepDictionary, fallbackStepNumber: stepOffset + 1)
        }
        return TutorialTourPartAnswer(
            appName: stringValue(answerObject["app"]),
            goal: stringValue(answerObject["goal"]),
            steps: parsedSteps,
            wasSalvagedFromTruncatedAnswer: wasSalvagedFromTruncatedAnswer
        )
    }

    static func step(from rawStepDictionary: [String: Any], fallbackStepNumber: Int) -> TutorialTourStep? {
        guard let videoTimeSeconds = doubleValue(rawStepDictionary["t"]) else { return nil }
        let rawBox = (rawStepDictionary["target_box_2d"] as? [Any])?.compactMap { doubleValue($0) }
        let validatedBox = rawBox.flatMap { boxValues -> [Double]? in
            guard boxValues.count == 4 else { return nil }
            return boxValues.map { min(1000, max(0, $0)) }
        }
        return TutorialTourStep(
            stepNumber: intValue(rawStepDictionary["n"]) ?? fallbackStepNumber,
            videoTimeSeconds: max(0, videoTimeSeconds),
            action: TutorialTourStepAction.parsed(from: rawStepDictionary["action"] as? String),
            targetLabel: stringValue(rawStepDictionary["target_label"]),
            targetDescription: stringValue(rawStepDictionary["target_description"]),
            targetBox2D: validatedBox,
            typedText: stringValue(rawStepDictionary["text"]),
            keys: stringValue(rawStepDictionary["keys"]),
            expectedResult: stringValue(rawStepDictionary["expect"]),
            targetCropFileName: nil
        )
    }

    private static func jsonObject(from text: String) -> [String: Any]? {
        guard let textData = text.data(using: .utf8),
              let parsedObject = try? JSONSerialization.jsonObject(with: textData) as? [String: Any] else {
            return nil
        }
        return parsedObject
    }

    private static func stringValue(_ value: Any?) -> String {
        if let stringValue = value as? String {
            return stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if let numberValue = value as? NSNumber { return numberValue.stringValue }
        return ""
    }

    private static func doubleValue(_ value: Any?) -> Double? {
        if let numberValue = value as? NSNumber { return numberValue.doubleValue }
        if let stringValue = value as? String { return Double(stringValue.trimmingCharacters(in: .whitespaces)) }
        return nil
    }

    private static func intValue(_ value: Any?) -> Int? {
        doubleValue(value).map { Int($0.rounded()) }
    }
}

// MARK: - Stitching video parts

/// Long tutorials are split into overlapping parts because one Elorian
/// answer can only hold so many steps. Each part owns the steps up to the
/// middle of its overlap with the next part, so a click inside the overlap
/// is kept exactly once.
nonisolated enum TutorialTourPartStitcher {

    struct AnsweredPart {
        let partStartSeconds: Double
        let partDurationSeconds: Double
        let answer: TutorialTourPartAnswer
    }

    static func stitch(_ answeredParts: [AnsweredPart]) -> [TutorialTourStep] {
        let partsInVideoOrder = answeredParts.sorted { $0.partStartSeconds < $1.partStartSeconds }
        var stitchedSteps: [TutorialTourStep] = []

        for (partIndex, answeredPart) in partsInVideoOrder.enumerated() {
            let ownershipStartSeconds: Double
            if partIndex == 0 {
                ownershipStartSeconds = -Double.infinity
            } else {
                let previousPart = partsInVideoOrder[partIndex - 1]
                let previousPartEndSeconds = previousPart.partStartSeconds + previousPart.partDurationSeconds
                ownershipStartSeconds = (answeredPart.partStartSeconds + previousPartEndSeconds) / 2
            }

            let ownershipEndSeconds: Double
            if partIndex == partsInVideoOrder.count - 1 {
                ownershipEndSeconds = Double.infinity
            } else {
                let nextPart = partsInVideoOrder[partIndex + 1]
                let thisPartEndSeconds = answeredPart.partStartSeconds + answeredPart.partDurationSeconds
                ownershipEndSeconds = (nextPart.partStartSeconds + thisPartEndSeconds) / 2
            }

            for partStep in answeredPart.answer.steps {
                var videoStep = partStep
                videoStep.videoTimeSeconds = partStep.videoTimeSeconds + answeredPart.partStartSeconds
                if videoStep.videoTimeSeconds >= ownershipStartSeconds && videoStep.videoTimeSeconds < ownershipEndSeconds {
                    stitchedSteps.append(videoStep)
                }
            }
        }

        stitchedSteps.sort { $0.videoTimeSeconds < $1.videoTimeSeconds }
        for stepIndex in stitchedSteps.indices {
            stitchedSteps[stepIndex].stepNumber = stepIndex + 1
        }
        return stitchedSteps
    }
}

// MARK: - Captions

nonisolated struct TutorialCaptionLine: Equatable {
    let startSeconds: Double
    let text: String
}

/// Reads YouTube WebVTT captions. Elorian ignores a video's audio, so the
/// narration only reaches it as text; in testing this cut invented steps
/// and fixed keyboard shortcuts.
nonisolated enum TutorialCaptionParser {

    static func parseWebVTT(_ webVTTText: String) -> [TutorialCaptionLine] {
        var captionLines: [TutorialCaptionLine] = []
        var currentCueStartSeconds: Double?
        var lastEmittedCaptionText = ""

        for rawLine in webVTTText.components(separatedBy: .newlines) {
            let trimmedLine = rawLine.trimmingCharacters(in: .whitespaces)
            if trimmedLine.contains("-->") {
                let cueStartText = trimmedLine.components(separatedBy: "-->").first ?? ""
                currentCueStartSeconds = timestampSeconds(cueStartText.trimmingCharacters(in: .whitespaces))
                continue
            }
            guard let cueStartSeconds = currentCueStartSeconds else { continue }
            if trimmedLine.isEmpty {
                currentCueStartSeconds = nil
                continue
            }

            // Auto-captions carry per-word timing tags and repeat the
            // previous line as they roll; keep each spoken line once.
            let captionText = trimmedLine
                .replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
                .replacingOccurrences(of: "&nbsp;", with: " ")
                .replacingOccurrences(of: "&amp;", with: "&")
                .trimmingCharacters(in: .whitespaces)
            guard !captionText.isEmpty, captionText != lastEmittedCaptionText else { continue }
            captionLines.append(TutorialCaptionLine(startSeconds: cueStartSeconds, text: captionText))
            lastEmittedCaptionText = captionText
        }
        return captionLines
    }

    /// Accepts `HH:MM:SS.mmm` and `MM:SS.mmm`.
    static func timestampSeconds(_ timestampText: String) -> Double? {
        let timestampFields = timestampText.split(separator: " ").first.map(String.init) ?? timestampText
        let timeComponents = timestampFields.split(separator: ":").map { Double($0.replacingOccurrences(of: ",", with: ".")) }
        guard !timeComponents.isEmpty, timeComponents.allSatisfy({ $0 != nil }) else { return nil }
        return timeComponents.compactMap { $0 }.reduce(0) { runningSeconds, component in runningSeconds * 60 + component }
    }

    /// Caption lines inside one video part, re-timed relative to that part,
    /// formatted for the prompt and capped so captions never crowd out the video.
    static func promptLines(
        from captionLines: [TutorialCaptionLine],
        partStartSeconds: Double,
        partEndSeconds: Double,
        maximumCharacterCount: Int = 6000
    ) -> [String] {
        var formattedLines: [String] = []
        var usedCharacterCount = 0
        for captionLine in captionLines where captionLine.startSeconds >= partStartSeconds && captionLine.startSeconds < partEndSeconds {
            let formattedLine = String(format: "[%.1f] %@", captionLine.startSeconds - partStartSeconds, captionLine.text)
            usedCharacterCount += formattedLine.count + 1
            if usedCharacterCount > maximumCharacterCount { break }
            formattedLines.append(formattedLine)
        }
        return formattedLines
    }
}

// MARK: - Prompts

nonisolated enum TutorialTourPrompts {

    /// The extraction prompt that scored best on real YouTube tutorials in
    /// the October 2026 evaluation (medium effort, with captions).
    static func extractionPrompt(
        tutorialTitle: String,
        sourceDescription: String,
        partNumber: Int,
        partCount: Int,
        partStartSeconds: Double,
        partDurationSeconds: Double,
        frameWidthInPixels: Int,
        frameHeightInPixels: Int,
        captionPromptLines: [String]
    ) -> String {
        var partContext = ""
        if partCount > 1 {
            partContext = String(
                format: " This clip is part %d of %d of the full tutorial (it starts %.0f s into the original); give times relative to THIS clip.",
                partNumber, partCount, partStartSeconds
            )
        }

        var prompt = """
        You are watching a screen-recorded software tutorial titled "\(tutorialTitle)". The video is \(String(format: "%.1f", partDurationSeconds)) s long, \(frameWidthInPixels)x\(frameHeightInPixels) pixels.\(partContext)

        Turn it into a TOUR that a guide app could walk a user through on their own computer: one step per user action the tutorial demonstrates (clicks, menu choices, double/right clicks, typing, keyboard shortcuts, drags). Ignore talking-head, intro, outro and subscribe segments and aimless cursor movement. If the video is zoomed or panned for emphasis, still box the element on the frame as shown.

        For each step give:
        - "t": seconds into this video at the moment of the action (the click, or the start of typing / the shortcut), to 0.1 s
        - "action": click | double_click | right_click | type | key | scroll | drag | wait
        - "target_label": the visible text or accessible name of the element acted on ("" if icon-only)
        - "target_description": what the element looks like and where it sits in the window, specific enough to find it on a different screen size
        - "target_box_2d": [y1, x1, y2, x2], integers normalized 0-1000 (y first, origin top-left) on the video frame at t, tight around the element acted on (the button, menu item or icon itself, not the whole panel). For key/type steps with no on-screen target, box the field or object that receives the input, or [] if there is none.
        - "text" (typed text), "keys" (e.g. "ctrl+r", "tab"), "expect" (what the screen shows after the step)

        Check each box against the full-resolution frame at t before answering.

        """

        if !captionPromptLines.isEmpty {
            prompt += """
            The video's audio is not available to you, so here is the narrator's speech as auto-generated captions, timestamped in seconds from the start of this video. Use it to understand WHAT is being clicked and WHY (shortcut keys and menu names the narrator says), but take times and boxes from the frames.
            <captions>
            \(captionPromptLines.joined(separator: "\n"))
            </captions>

            """
        }

        prompt += """
        Reply with ONLY one JSON object, no prose, in exactly this shape:
        {"source": "\(sourceDescription.replacingOccurrences(of: "\"", with: "'"))", "app": "<app or site>", "goal": "<one sentence>", "steps": [{"n": 1, "t": 0.0, "action": "click", "target_label": "...", "target_description": "...", "target_box_2d": [y1, x1, y2, x2], "text": "", "keys": "", "expect": "..."}]}
        """
        return prompt
    }

    /// Asks for pixel coordinates on a screenshot resized to 1000×1000. In
    /// testing, Elorian's fast mode sometimes answered on a 0–1000 grid when
    /// asked for pixels; making the two spaces identical took its hit rate
    /// on small controls from 65% to 91%.
    static func pointingPrompt(
        squareImageSideInPixels: Int,
        targetLabel: String,
        targetDescription: String,
        hasReferenceCrop: Bool
    ) -> String {
        var targetSummary = targetDescription
        if !targetLabel.isEmpty {
            targetSummary = "the element labelled “\(targetLabel)”" + (targetDescription.isEmpty ? "" : " (\(targetDescription))")
        }
        let side = squareImageSideInPixels
        if hasReferenceCrop {
            return "The FIRST image is a \(side)x\(side) pixel screenshot of the user's screen (resized to a square). The SECOND image is a small crop of the target element taken from a tutorial recording of the same app; on the user's screen the size, theme, and layout may differ. Find \(targetSummary) (the element shown in the second image) in the FIRST image. If it is not visible, reply {\"x\": null, \"y\": null}. Otherwise reply with only JSON: {\"x\": <int>, \"y\": <int>} = the pixel coordinates of its center in the first \(side)x\(side) image (origin top-left)."
        }
        return "This screenshot is \(side)x\(side) pixels (resized to a square). Find \(targetSummary). If it is not visible, reply {\"x\": null, \"y\": null}. Otherwise reply with only JSON: {\"x\": <int>, \"y\": <int>} = the pixel coordinates of the center of that element in this \(side)x\(side) image (origin top-left, x to the right, y down)."
    }
}

// MARK: - Pointing answers

nonisolated enum ElorianPointAnswerParser {

    /// Returns the point from the last `{...}` object that has numeric x and y.
    /// Returns nil when the model says the target is not visible.
    static func point(from answerText: String) -> CGPoint? {
        let objectTexts = TutorialTourAnswerParser.completeTopLevelObjectTexts(in: Substring(answerText + "]"))
        for objectText in objectTexts.reversed() {
            guard let objectData = objectText.data(using: .utf8),
                  let answerObject = try? JSONSerialization.jsonObject(with: objectData) as? [String: Any],
                  let xNumber = answerObject["x"] as? NSNumber,
                  let yNumber = answerObject["y"] as? NSNumber else {
                continue
            }
            return CGPoint(x: xNumber.doubleValue, y: yNumber.doubleValue)
        }
        return nil
    }
}

// MARK: - Pricing

nonisolated enum ElorianPricing {
    /// Published API prices per million tokens (October 2026). Reasoning
    /// tokens are billed as output.
    static let inputDollarsPerMillionTokens = 0.60
    static let cachedInputDollarsPerMillionTokens = 0.06
    static let outputDollarsPerMillionTokens = 3.00

    static func estimatedCostInDollars(promptTokens: Int, cachedPromptTokens: Int, completionTokens: Int) -> Double {
        let uncachedPromptTokens = max(0, promptTokens - cachedPromptTokens)
        return (Double(uncachedPromptTokens) * inputDollarsPerMillionTokens
            + Double(cachedPromptTokens) * cachedInputDollarsPerMillionTokens
            + Double(completionTokens) * outputDollarsPerMillionTokens) / 1_000_000
    }
}
