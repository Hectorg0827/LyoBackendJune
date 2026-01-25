import Foundation
import SwiftUI
import AVFoundation
import Speech

/// Voice Integration for A2UI Protocol
/// Enables TTS, voice input, and accessibility for all A2UI components

// ═══════════════════════════════════════════════════════════════════
// MARK: - Voice-Enhanced A2UI Props
// ═══════════════════════════════════════════════════════════════════

extension A2UIComponent {

    /// Extract speakable text for TTS
    var speakableContent: String? {
        // Priority: custom speakable > accessibility label > main text
        return prop("speakable_text").asString ??
               prop("accessibility_label").asString ??
               prop("text").asString ??
               prop("title").asString ??
               prop("question").asString
    }

    /// Should this component auto-speak when displayed?
    var shouldAutoSpeak: Bool {
        return prop("auto_speak").asBool ?? false
    }

    /// Voice input enabled for this component?
    var acceptsVoiceInput: Bool {
        return prop("accepts_voice_input").asBool ?? false
    }

    /// Voice hint for input components
    var voiceInputHint: String? {
        return prop("voice_hint").asString
    }

    /// TTS voice style
    var preferredVoice: TTSVoice {
        guard let voiceString = prop("tts_voice").asString else { return .nova }
        return TTSVoice(rawValue: voiceString) ?? .nova
    }

    /// TTS speed (0.5 to 2.0)
    var speechRate: Float {
        return Float(prop("tts_speed").asDouble ?? 1.0)
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - Voice-Enhanced Renderer
// ═══════════════════════════════════════════════════════════════════

struct A2UIVoiceRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    @StateObject private var voiceCoordinator = A2UIVoiceCoordinator()
    @State private var hasSpoken = false

    var body: some View {
        A2UIRenderer(component: component, onAction: onAction)
            .onAppear {
                handleAutoSpeak()
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(component.prop("accessibility_label").asString ?? "")
            .accessibilityHint(component.prop("accessibility_hint").asString ?? "")
            .accessibilityAddTraits(component.acceptsVoiceInput ? .allowsDirectInteraction : [])
            .overlay(
                voiceInputOverlay,
                alignment: .topTrailing
            )
    }

    private func handleAutoSpeak() {
        guard component.shouldAutoSpeak,
              !hasSpoken,
              let content = component.speakableContent else {
            return
        }

        hasSpoken = true

        Task {
            await voiceCoordinator.speak(
                text: content,
                voice: component.preferredVoice,
                rate: component.speechRate
            )
        }
    }

    @ViewBuilder
    private var voiceInputOverlay: some View {
        if component.acceptsVoiceInput {
            Button(action: startVoiceInput) {
                Image(systemName: voiceCoordinator.isListening ? "mic.fill" : "mic")
                    .foregroundColor(voiceCoordinator.isListening ? .red : .blue)
                    .padding(8)
                    .background(Color(.systemBackground))
                    .clipShape(Circle())
                    .shadow(radius: 2)
            }
            .accessibilityLabel("Voice input")
            .accessibilityHint(component.voiceInputHint ?? "Tap to speak your answer")
        }
    }

    private func startVoiceInput() {
        guard !voiceCoordinator.isListening else {
            voiceCoordinator.stopListening()
            return
        }

        voiceCoordinator.startListening { transcript in
            let action = A2UIAction(
                actionId: "voice_input",
                componentId: component.id,
                actionType: "voice_input",
                params: [
                    "transcript": transcript,
                    "confidence": voiceCoordinator.lastConfidence
                ]
            )
            onAction?(action)
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - Voice Coordinator
// ═══════════════════════════════════════════════════════════════════

@MainActor
final class A2UIVoiceCoordinator: ObservableObject {
    @Published var isListening = false
    @Published var isSpeaking = false
    @Published var lastTranscript: String = ""
    @Published var lastConfidence: Float = 0.0

    private let synthesizer = AVSpeechSynthesizer()
    private let speechRecognizer = SFSpeechRecognizer()
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()

    private var onTranscriptReceived: ((String) -> Void)?

    init() {
        setupAudio()
    }

    private func setupAudio() {
        // Configure audio session for both TTS and recognition
        do {
            try AVAudioSession.sharedInstance().setCategory(
                .playAndRecord,
                mode: .default,
                options: [.defaultToSpeaker, .allowBluetooth]
            )
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {
            print("Failed to setup audio session: \(error)")
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // MARK: - Text-to-Speech
    // ═══════════════════════════════════════════════════════════════

    func speak(text: String, voice: TTSVoice = .nova, rate: Float = 1.0) async {
        guard !text.isEmpty else { return }

        isSpeaking = true
        defer { isSpeaking = false }

        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = voice.avVoice
        utterance.rate = max(0.1, min(1.0, rate)) // Clamp rate
        utterance.pitchMultiplier = 1.0
        utterance.volume = 1.0

        synthesizer.speak(utterance)

        // Wait for speech to complete
        await withUnsafeContinuation { continuation in
            let delegate = SpeechDelegate {
                continuation.resume()
            }
            synthesizer.delegate = delegate
        }
    }

    func stopSpeaking() {
        synthesizer.stopSpeaking(at: .immediate)
        isSpeaking = false
    }

    // ═══════════════════════════════════════════════════════════════
    // MARK: - Speech Recognition
    // ═══════════════════════════════════════════════════════════════

    func startListening(onResult: @escaping (String) -> Void) {
        guard let speechRecognizer = speechRecognizer,
              speechRecognizer.isAvailable else {
            print("Speech recognition not available")
            return
        }

        onTranscriptReceived = onResult

        // Request authorization
        SFSpeechRecognizer.requestAuthorization { authStatus in
            DispatchQueue.main.async {
                if authStatus == .authorized {
                    self.startRecording()
                }
            }
        }
    }

    private func startRecording() {
        // Cancel any previous task
        recognitionTask?.cancel()
        recognitionTask = nil

        let inputNode = audioEngine.inputNode
        let recordingFormat = inputNode.outputFormat(forBus: 0)

        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { buffer, _ in
            self.recognitionTask?.append(buffer)
        }

        audioEngine.prepare()

        do {
            try audioEngine.start()
        } catch {
            print("Audio engine couldn't start: \(error)")
            return
        }

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true

        recognitionTask = speechRecognizer?.recognitionTask(with: request) { result, error in
            var isFinal = false

            if let result = result {
                DispatchQueue.main.async {
                    self.lastTranscript = result.bestTranscription.formattedString
                    self.lastConfidence = result.bestTranscription.averageConfidence
                }
                isFinal = result.isFinal
            }

            if error != nil || isFinal {
                DispatchQueue.main.async {
                    self.stopListening()
                    if !self.lastTranscript.isEmpty {
                        self.onTranscriptReceived?(self.lastTranscript)
                    }
                }
            }
        }

        isListening = true
    }

    func stopListening() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionTask?.cancel()
        recognitionTask = nil
        isListening = false
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - TTS Voice Options
// ═══════════════════════════════════════════════════════════════════

enum TTSVoice: String, CaseIterable {
    case nova = "nova"
    case alloy = "alloy"
    case echo = "echo"
    case fable = "fable"
    case onyx = "onyx"
    case shimmer = "shimmer"

    var avVoice: AVSpeechSynthesisVoice? {
        // Map to available system voices
        switch self {
        case .nova:
            return AVSpeechSynthesisVoice(language: "en-US")
        case .alloy:
            return AVSpeechSynthesisVoice(identifier: "com.apple.ttsbundle.Samantha-compact")
        case .echo:
            return AVSpeechSynthesisVoice(identifier: "com.apple.ttsbundle.Daniel-compact")
        case .fable:
            return AVSpeechSynthesisVoice(identifier: "com.apple.ttsbundle.Karen-compact")
        case .onyx:
            return AVSpeechSynthesisVoice(identifier: "com.apple.ttsbundle.Moira-compact")
        case .shimmer:
            return AVSpeechSynthesisVoice(identifier: "com.apple.ttsbundle.Tessa-compact")
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - Speech Delegate Helper
// ═══════════════════════════════════════════════════════════════════

private class SpeechDelegate: NSObject, AVSpeechSynthesizerDelegate {
    let onComplete: () -> Void

    init(onComplete: @escaping () -> Void) {
        self.onComplete = onComplete
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        onComplete()
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - Usage Examples
// ═══════════════════════════════════════════════════════════════════

/*

Backend can now send voice-enhanced A2UI:

{
    "type": "quiz_mcq",
    "props": {
        "question": "What is the capital of France?",
        "options": ["London", "Berlin", "Paris", "Madrid"],
        "correct_index": 2,

        // Voice properties
        "auto_speak": true,
        "speakable_text": "Question: What is the capital of France? Your options are: A, London. B, Berlin. C, Paris. D, Madrid.",
        "accepts_voice_input": true,
        "voice_hint": "Say the letter or full answer",
        "tts_voice": "nova",
        "tts_speed": 1.0,

        // Accessibility
        "accessibility_label": "Multiple choice question about European capitals",
        "accessibility_hint": "Tap an option or use voice input to answer"
    }
}

*/