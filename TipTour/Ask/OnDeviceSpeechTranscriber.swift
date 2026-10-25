//
//  OnDeviceSpeechTranscriber.swift
//  TipTour
//
//  Push-to-talk speech-to-text for the ask harness using SFSpeechRecognizer
//  with requiresOnDeviceRecognition = true. Audio never leaves the Mac for
//  transcription: when the active locale cannot recognize on-device, start
//  refuses instead of silently falling back to a network service.
//
//  Lifecycle: start suspends on the Speech and microphone permission
//  prompts, and a release/cancel (stop) or a newer press can land while it
//  is suspended. AskSpeechStartCoordinator revalidates the start intent
//  after every await and once more immediately before install, so a
//  superseded start never installs a live engine after its session ended.
//  Recognition callbacks are epoch-keyed (AskTranscriptSink) so a stale
//  task's result can never contaminate the next session's transcript.
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
    private var tapInstalled = false

    /// Epoch-keyed transcript state; see AskTranscriptSink.
    private let transcriptSink = AskTranscriptSink()

    /// Inputs prepared by start(locale:) for the coordinator's install step.
    private var pendingRecognizer: SFSpeechRecognizer?
    private var pendingLocale: Locale?

    private lazy var lifecycle = AskSpeechStartCoordinator(
        requestSpeechPermission: {
            let status = await OnDeviceSpeechTranscriber.requestSpeechAuthorization()
            guard status == .authorized else {
                throw OnDeviceSpeechTranscriberError.speechRecognitionNotAuthorized(status)
            }
        },
        requestMicrophonePermission: {
            let granted = await OnDeviceSpeechTranscriber.requestMicrophoneAuthorization()
            guard granted else {
                throw OnDeviceSpeechTranscriberError.microphoneNotAuthorized
            }
        },
        installRecording: { [weak self] in
            guard let self else { throw CancellationError() }
            try self.installRecording()
        }
    )

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
    /// network-backed request. On success returns the recording epoch,
    /// which the caller can pass to stopIfCurrent(_:) if its session ended
    /// while the start was still in flight.
    @discardableResult
    func start(locale: Locale = .autoupdatingCurrent) async throws -> Int {
        if let readinessError = Self.onDeviceReadinessError(for: locale),
           readinessError.isFatalBeforePrompt {
            throw readinessError
        }

        guard let recognizer = SFSpeechRecognizer(locale: locale),
              recognizer.isAvailable,
              recognizer.supportsOnDeviceRecognition else {
            throw OnDeviceSpeechTranscriberError.onDeviceRecognitionUnsupported(localeIdentifier: locale.identifier)
        }

        pendingRecognizer = recognizer
        pendingLocale = locale
        defer {
            pendingRecognizer = nil
            pendingLocale = nil
        }

        // The coordinator validates the start intent after each permission
        // await and once more immediately before installRecording().
        try await lifecycle.start()
        return transcriptSink.epoch
    }

    /// Stops recording, invalidates any start still waiting on a permission
    /// prompt (a late start must never install a live engine after this),
    /// and waits briefly for the final transcript. Idempotent: safe to call
    /// when nothing is recording and safe to call twice.
    /// Returns whatever was recognized, possibly empty.
    @discardableResult
    func stop() async -> String {
        lifecycle.invalidatePendingStart()

        // Move state out first so an overlapping stop() is a no-op and a
        // new start can never see a half-torn-down engine.
        let engine = audioEngine
        let request = recognitionRequest
        let task = recognitionTask
        let hadTap = tapInstalled
        audioEngine = nil
        recognitionRequest = nil
        recognitionTask = nil
        tapInstalled = false

        if hadTap {
            engine?.inputNode.removeTap(onBus: 0)
        }
        engine?.stop()
        request?.endAudio()

        // Only a session that actually recorded can still deliver a final
        // result; a superseded or never-installed start must not wait.
        if hadTap {
            for _ in 0..<25 where !transcriptSink.didReceiveFinal {
                try? await Task.sleep(nanoseconds: 100_000_000)
            }
        }

        task?.cancel()
        return transcriptSink.finish()
    }

    /// Stops the recording only if `epoch` is still the active one. Used
    /// when a start succeeded after its session already ended: the orphan
    /// recording is torn down, but a newer session's recording (different
    /// epoch) is never touched.
    @discardableResult
    func stopIfCurrent(_ epoch: Int) async -> Bool {
        guard epoch == transcriptSink.epoch, audioEngine != nil else { return false }
        _ = await stop()
        return true
    }

    /// Runs synchronously inside the coordinator's final validated window:
    /// no stop()/cancel/new start can interleave between its last intent
    /// check and this install. Engine state is published before the engine
    /// starts so the throw path tears down through one idempotent path.
    private func installRecording() throws {
        guard let recognizer = pendingRecognizer, let locale = pendingLocale else {
            throw CancellationError()
        }

        // Defensive: no earlier recording may still be live when a new one
        // installs (the coordinator's supersession already guarantees it).
        teardownRecording()

        self.locale = locale
        let epoch = transcriptSink.beginNewRecording()

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

        let recognitionTask = recognizer.recognitionTask(with: recognitionRequest) { [weak self] result, error in
            guard let self else { return }
            if let result {
                let text = result.bestTranscription.formattedString
                let isFinal = result.isFinal
                Task { @MainActor in
                    // Drop results from a superseded recording: they belong
                    // to the old session, not the current transcript.
                    self.transcriptSink.accept(text, isFinal: isFinal, fromEpoch: epoch)
                }
            }
            if let error {
                NSLog("[Ask] speech recognition ended with error: \(error.localizedDescription)")
                Task { @MainActor in
                    self.transcriptSink.markFinal(fromEpoch: epoch)
                }
            }
        }

        self.audioEngine = audioEngine
        self.recognitionRequest = recognitionRequest
        self.recognitionTask = recognitionTask

        inputNode.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { buffer, _ in
            recognitionRequest.append(buffer)
        }
        tapInstalled = true

        audioEngine.prepare()
        do {
            try audioEngine.start()
        } catch {
            teardownRecording()
            throw error
        }
    }

    /// Idempotent teardown: safe with a partially installed engine and
    /// safe when already torn down. Does not touch lifecycle intent; it is
    /// called from inside installRecording()'s validated window too.
    private func teardownRecording() {
        if tapInstalled {
            tapInstalled = false
            audioEngine?.inputNode.removeTap(onBus: 0)
        }
        audioEngine?.stop()
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        audioEngine = nil
        recognitionRequest = nil
        recognitionTask = nil
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
