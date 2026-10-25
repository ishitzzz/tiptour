//
//  OnDeviceSpeechTranscriber.swift
//  TipTour
//
//  Push-to-talk speech-to-text for the ask harness using SFSpeechRecognizer
//  with requiresOnDeviceRecognition = true. Audio never leaves the Mac for
//  transcription: when the active locale cannot recognize on-device, start
//  refuses instead of silently falling back to a network service.
//

import AVFoundation
import Speech

enum OnDeviceSpeechTranscriberError: LocalizedError {
    case recognizerUnavailable(localeIdentifier: String)
    case onDeviceRecognitionUnsupported(localeIdentifier: String)
    case speechRecognitionNotAuthorized(SFSpeechRecognizerAuthorizationStatus)
    case microphoneNotAuthorized

    var errorDescription: String? {
        switch self {
        case .recognizerUnavailable(let localeIdentifier):
            return "Speech recognition is unavailable for locale \(localeIdentifier) right now."
        case .onDeviceRecognitionUnsupported(let localeIdentifier):
            return "On-device speech recognition is not supported for locale \(localeIdentifier) on this Mac. TipTour will not send your audio over the network, so the spoken question cannot be transcribed here."
        case .speechRecognitionNotAuthorized(let status):
            return "Speech recognition permission is \(Self.describe(status)). Grant it in System Settings > Privacy & Security > Speech Recognition."
        case .microphoneNotAuthorized:
            return "Microphone permission is not granted. Enable it in System Settings > Privacy & Security > Microphone."
        }
    }

    private static func describe(_ status: SFSpeechRecognizerAuthorizationStatus) -> String {
        switch status {
        case .denied: return "denied"
        case .restricted: return "restricted"
        case .notDetermined: return "not determined"
        case .authorized: return "authorized"
        @unknown default: return "unknown"
        }
    }
}

@MainActor
final class OnDeviceSpeechTranscriber {
    private(set) var locale: Locale = .autoupdatingCurrent

    private var audioEngine: AVAudioEngine?
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var latestTranscript = ""
    private var didReceiveFinalResult = false

    /// Pre-flight check so the harness can fail before recording starts.
    static func onDeviceReadinessError(
        for locale: Locale = .autoupdatingCurrent
    ) -> OnDeviceSpeechTranscriberError? {
        let localeIdentifier = locale.identifier
        guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
            return .recognizerUnavailable(localeIdentifier: localeIdentifier)
        }
        guard recognizer.supportsOnDeviceRecognition else {
            return .onDeviceRecognitionUnsupported(localeIdentifier: localeIdentifier)
        }
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized, .notDetermined:
            return nil
        case let status:
            return .speechRecognitionNotAuthorized(status)
        }
    }

    /// Starts recording and transcribing. Throws when on-device
    /// recognition or permissions are unavailable; never degrades to a
    /// network-backed request.
    func start(locale: Locale = .autoupdatingCurrent) async throws {
        if let readinessError = Self.onDeviceReadinessError(for: locale),
           readinessError.isFatalBeforePrompt {
            throw readinessError
        }

        let speechStatus = await Self.requestSpeechAuthorization()
        guard speechStatus == .authorized else {
            throw OnDeviceSpeechTranscriberError.speechRecognitionNotAuthorized(speechStatus)
        }

        let microphoneGranted = await Self.requestMicrophoneAuthorization()
        guard microphoneGranted else {
            throw OnDeviceSpeechTranscriberError.microphoneNotAuthorized
        }

        guard let recognizer = SFSpeechRecognizer(locale: locale),
              recognizer.isAvailable,
              recognizer.supportsOnDeviceRecognition else {
            throw OnDeviceSpeechTranscriberError.onDeviceRecognitionUnsupported(localeIdentifier: locale.identifier)
        }

        self.locale = locale
        latestTranscript = ""
        didReceiveFinalResult = false

        // A fresh engine per run: reinstalling a tap on a reused engine
        // explodes after a device or sample-rate change.
        let audioEngine = AVAudioEngine()
        let recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        recognitionRequest.shouldReportPartialResults = true
        recognitionRequest.requiresOnDeviceRecognition = true

        let inputNode = audioEngine.inputNode
        let inputFormat = inputNode.inputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0 else {
            throw OnDeviceSpeechTranscriberError.microphoneNotAuthorized
        }

        recognitionTask = recognizer.recognitionTask(with: recognitionRequest) { [weak self] result, error in
            guard let self else { return }
            if let result {
                Task { @MainActor in
                    self.latestTranscript = result.bestTranscription.formattedString
                    if result.isFinal {
                        self.didReceiveFinalResult = true
                    }
                }
            }
            if let error {
                NSLog("[Ask] speech recognition ended with error: \(error.localizedDescription)")
                Task { @MainActor in
                    self.didReceiveFinalResult = true
                }
            }
        }

        inputNode.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { buffer, _ in
            recognitionRequest.append(buffer)
        }

        audioEngine.prepare()
        try audioEngine.start()

        self.audioEngine = audioEngine
        self.recognitionRequest = recognitionRequest
    }

    /// Stops recording and waits briefly for the final transcript.
    /// Returns whatever was recognized, possibly empty.
    func stop() async -> String {
        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine?.stop()
        recognitionRequest?.endAudio()

        // Give the recognizer a short window to deliver its final result
        // after endAudio; partial results are already in latestTranscript.
        for _ in 0..<25 where !didReceiveFinalResult {
            try? await Task.sleep(nanoseconds: 100_000_000)
        }

        recognitionTask?.cancel()
        recognitionTask = nil
        recognitionRequest = nil
        audioEngine = nil

        return latestTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func requestSpeechAuthorization() async -> SFSpeechRecognizerAuthorizationStatus {
        await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status)
            }
        }
    }

    private static func requestMicrophoneAuthorization() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return true
        case .notDetermined:
            return await withCheckedContinuation { continuation in
                AVCaptureDevice.requestAccess(for: .audio) { granted in
                    continuation.resume(returning: granted)
                }
            }
        case .denied, .restricted:
            return false
        @unknown default:
            return false
        }
    }
}

private extension OnDeviceSpeechTranscriberError {
    /// Denied/restricted speech permission cannot be fixed by prompting, so
    /// it is fatal up front; `notDetermined` may proceed to the prompt.
    var isFatalBeforePrompt: Bool {
        switch self {
        case .speechRecognitionNotAuthorized(let status):
            return status == .denied || status == .restricted
        case .recognizerUnavailable, .onDeviceRecognitionUnsupported, .microphoneNotAuthorized:
            return true
        }
    }
}
