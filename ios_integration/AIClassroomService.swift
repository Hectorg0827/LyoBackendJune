// AIClassroomService.swift
// Lyo
//
// AI Classroom Integration - Extends LyoAppAPIClient
// Copy this file to: Lyo/Services/AIClassroomService.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import Foundation
import Combine

// MARK: - AI Classroom Extension for LyoAppAPIClient

extension LyoAppAPIClient {
    
    // MARK: - AI Classroom Chat
    
    /// Send a message to AI Classroom and get intelligent response
    func sendClassroomMessage(
        message: String,
        sessionId: String? = nil,
        enableTTS: Bool = false,
        voiceId: String = "nova"
    ) -> AnyPublisher<ClassroomChatResponse, APIError> {
        var request = createRequest(for: "/classroom/chat", method: .POST)
        
        let chatRequest = ClassroomChatRequest(
            message: message,
            sessionId: sessionId,
            context: nil,
            enableTTS: enableTTS,
            voiceId: enableTTS ? voiceId : nil
        )
        
        do {
            request.httpBody = try JSONEncoder().encode(chatRequest)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: ClassroomChatResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    /// Analyze user intent from message
    func analyzeIntent(message: String) -> AnyPublisher<IntentAnalysisResponse, APIError> {
        var request = createRequest(for: "/classroom/analyze-intent", method: .POST)
        
        let intentRequest = IntentAnalysisRequest(message: message, context: nil)
        
        do {
            request.httpBody = try JSONEncoder().encode(intentRequest)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: IntentAnalysisResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    /// Get chat suggestions based on context
    func getClassroomSuggestions(sessionId: String) -> AnyPublisher<SuggestionsResponse, APIError> {
        var request = createRequest(for: "/classroom/suggestions", method: .POST)
        
        let suggestionsRequest = ["session_id": sessionId]
        
        do {
            request.httpBody = try JSONEncoder().encode(suggestionsRequest)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: SuggestionsResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    /// Get AI Classroom capabilities
    func getClassroomCapabilities() -> AnyPublisher<CapabilitiesResponse, APIError> {
        let request = createRequest(for: "/classroom/capabilities", method: .GET)
        
        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: CapabilitiesResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    // MARK: - Text-to-Speech
    
    /// Get available TTS voices
    func getTTSVoices() -> AnyPublisher<TTSVoicesResponse, APIError> {
        let request = createRequest(for: "/tts/voices", method: .GET)
        
        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: TTSVoicesResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    /// Synthesize speech from text
    func synthesizeSpeech(
        text: String,
        voiceId: String = "nova",
        speed: Double = 1.0
    ) -> AnyPublisher<TTSSynthesizeResponse, APIError> {
        var request = createRequest(for: "/tts/synthesize", method: .POST)
        
        let ttsRequest = TTSRequest(text: text, voiceId: voiceId, speed: speed, format: "mp3")
        
        do {
            request.httpBody = try JSONEncoder().encode(ttsRequest)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: TTSSynthesizeResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    // MARK: - Image Generation
    
    /// Generate educational image using DALL-E 3
    func generateImage(
        prompt: String,
        style: ImageStyle = .educational,
        size: String = "1024x1024"
    ) -> AnyPublisher<ImageGenResponse, APIError> {
        var request = createRequest(for: "/images/generate", method: .POST)
        
        let imageRequest = ImageGenRequest(prompt: prompt, style: style, size: size, quality: "standard")
        
        do {
            request.httpBody = try JSONEncoder().encode(imageRequest)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: ImageGenResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    /// Generate educational-optimized image
    func generateEducationalImage(
        topic: String,
        contentType: String = "diagram"
    ) -> AnyPublisher<ImageGenResponse, APIError> {
        var request = createRequest(for: "/images/educational", method: .POST)
        
        let educationalRequest = ["topic": topic, "content_type": contentType]
        
        do {
            request.httpBody = try JSONEncoder().encode(educationalRequest)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: ImageGenResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
}

// MARK: - AI Classroom Models

struct ClassroomChatRequest: Codable {
    let message: String
    let sessionId: String?
    let context: ClassroomContext?
    let enableTTS: Bool?
    let voiceId: String?
    
    enum CodingKeys: String, CodingKey {
        case message
        case sessionId = "session_id"
        case context
        case enableTTS = "enable_tts"
        case voiceId = "voice_id"
    }
}

struct ClassroomContext: Codable {
    let topic: String?
    let difficulty: String?
    let learningStyle: String?
    let previousConcepts: [String]?
    
    enum CodingKeys: String, CodingKey {
        case topic
        case difficulty
        case learningStyle = "learning_style"
        case previousConcepts = "previous_concepts"
    }
}

struct ClassroomChatResponse: Codable {
    let sessionId: String
    let response: String
    let intent: DetectedIntent
    let suggestions: [String]?
    let audioUrl: String?
    let generatedContent: GeneratedContent?
    
    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case response
        case intent
        case suggestions
        case audioUrl = "audio_url"
        case generatedContent = "generated_content"
    }
}

struct DetectedIntent: Codable {
    let type: IntentType
    let confidence: Double
    let parameters: [String: String]?
}

enum IntentType: String, Codable {
    case quickExplanation = "quick_explanation"
    case fullCourse = "full_course"
    case quiz = "quiz"
    case exercise = "exercise"
    case codeHelp = "code_help"
    case studyPlan = "study_plan"
    case conversation = "conversation"
    case unknown = "unknown"
}

struct GeneratedContent: Codable {
    let type: String
    let title: String?
    let content: String?
    let courseId: String?
    let quizId: String?
    
    enum CodingKeys: String, CodingKey {
        case type
        case title
        case content
        case courseId = "course_id"
        case quizId = "quiz_id"
    }
}

struct IntentAnalysisRequest: Codable {
    let message: String
    let context: ClassroomContext?
}

struct IntentAnalysisResponse: Codable {
    let intent: DetectedIntent
    let suggestedActions: [SuggestedAction]
    
    enum CodingKeys: String, CodingKey {
        case intent
        case suggestedActions = "suggested_actions"
    }
}

struct SuggestedAction: Codable {
    let action: String
    let label: String
    let description: String?
}

struct SuggestionsResponse: Codable {
    let suggestions: [String]
    let sessionId: String?
    
    enum CodingKeys: String, CodingKey {
        case suggestions
        case sessionId = "session_id"
    }
}

struct CapabilitiesResponse: Codable {
    let intents: [String]
    let voices: [String]
    let imageStyles: [String]
    let features: [String]
    
    enum CodingKeys: String, CodingKey {
        case intents
        case voices
        case imageStyles = "image_styles"
        case features
    }
}

// MARK: - TTS Models

struct TTSRequest: Codable {
    let text: String
    let voiceId: String?
    let speed: Double?
    let format: String?
    
    enum CodingKeys: String, CodingKey {
        case text
        case voiceId = "voice_id"
        case speed
        case format
    }
}

struct TTSVoice: Codable, Identifiable {
    let id: String
    let name: String
    let description: String
    let previewUrl: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case description
        case previewUrl = "preview_url"
    }
}

struct TTSVoicesResponse: Codable {
    let voices: [TTSVoice]
}

struct TTSSynthesizeResponse: Codable {
    let audioUrl: String
    let duration: Double?
    
    enum CodingKeys: String, CodingKey {
        case audioUrl = "audio_url"
        case duration
    }
}

// MARK: - Image Generation Models

struct ImageGenRequest: Codable {
    let prompt: String
    let style: ImageStyle?
    let size: String?
    let quality: String?
    
    enum CodingKeys: String, CodingKey {
        case prompt
        case style
        case size
        case quality
    }
}

enum ImageStyle: String, Codable {
    case educational = "educational"
    case diagram = "diagram"
    case illustration = "illustration"
    case infographic = "infographic"
    case realistic = "realistic"
}

struct ImageGenResponse: Codable {
    let imageUrl: String
    let revisedPrompt: String?
    
    enum CodingKeys: String, CodingKey {
        case imageUrl = "image_url"
        case revisedPrompt = "revised_prompt"
    }
}
