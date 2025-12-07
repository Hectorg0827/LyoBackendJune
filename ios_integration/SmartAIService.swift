// SmartAIService.swift
// Lyo
//
// Smart AI Service - Automatically detects intent and routes to appropriate task type
// Copy this file to your iOS project: Lyo/Services/SmartAIService.swift
//
// This replaces basic AI calls with intelligent routing:
// - "Teach me X" → COURSE_GENERATION (full course)
// - "What is X?" → EDUCATIONAL_EXPLANATION (quick answer)
// - "Quiz me on X" → QUIZ_GENERATION (practice questions)
//
// USAGE:
//   SmartAIService.shared.chat(message: "Teach me Python") { result in ... }

import Foundation

// MARK: - Smart AI Service

@MainActor
class SmartAIService: ObservableObject {
    static let shared = SmartAIService()
    
    @Published var isLoading = false
    @Published var lastResponse: AIResponse?
    @Published var error: Error?
    
    private let baseURL = "https://lyo-backend-production-830162750094.us-central1.run.app"
    
    // MARK: - Intent Detection Patterns
    
    private let coursePatterns: [String] = [
        "create a course",
        "teach me",
        "learn about",
        "full course on",
        "course on",
        "comprehensive guide",
        "in-depth lesson",
        "tutorial on",
        "master",
        "study guide for"
    ]
    
    private let quizPatterns: [String] = [
        "quiz me",
        "test me",
        "practice questions",
        "test my knowledge",
        "assessment on",
        "practice test",
        "check my understanding"
    ]
    
    private let notePatterns: [String] = [
        "summarize",
        "notes on",
        "key points",
        "tldr",
        "summary of",
        "outline"
    ]
    
    // MARK: - Task Type Detection
    
    func detectTaskType(from message: String) -> TaskType {
        let lowercased = message.lowercased()
        
        // Check for course patterns first (most specific)
        for pattern in coursePatterns {
            if lowercased.contains(pattern) {
                return .courseGeneration
            }
        }
        
        // Check for quiz patterns
        for pattern in quizPatterns {
            if lowercased.contains(pattern) {
                return .quizGeneration
            }
        }
        
        // Check for note/summary patterns
        for pattern in notePatterns {
            if lowercased.contains(pattern) {
                return .noteSummarization
            }
        }
        
        // Default to educational explanation
        return .educationalExplanation
    }
    
    // MARK: - Main Chat Method
    
    func chat(
        message: String,
        forceTaskType: TaskType? = nil,
        temperature: Double = 0.7,
        completion: @escaping (Result<AIResponse, Error>) -> Void
    ) {
        isLoading = true
        error = nil
        
        // Auto-detect or use forced task type
        let taskType = forceTaskType ?? detectTaskType(from: message)
        
        print("🧠 SmartAI: Detected task type: \(taskType.rawValue) for: \"\(message)\"")
        
        // Build request
        guard let url = URL(string: "\(baseURL)/api/v1/ai/generate") else {
            completion(.failure(AIError.invalidURL))
            isLoading = false
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("iOS", forHTTPHeaderField: "X-Platform")
        request.setValue("1.0", forHTTPHeaderField: "X-App-Version")
        
        // Add auth token if available
        if let token = UserDefaults.standard.string(forKey: "firebase_id_token") {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let body: [String: Any] = [
            "prompt": message,
            "task_type": taskType.rawValue,
            "temperature": temperature,
            "max_tokens": taskType == .courseGeneration ? 3000 : 1500
        ]
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        } catch {
            completion(.failure(error))
            isLoading = false
            return
        }
        
        // Make request
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                self?.isLoading = false
                
                if let error = error {
                    self?.error = error
                    completion(.failure(error))
                    return
                }
                
                guard let data = data else {
                    let noDataError = AIError.noData
                    self?.error = noDataError
                    completion(.failure(noDataError))
                    return
                }
                
                // Debug: print response
                if let responseString = String(data: data, encoding: .utf8) {
                    print("📥 SmartAI Response: \(responseString.prefix(500))...")
                }
                
                do {
                    let decoder = JSONDecoder()
                    let aiResponse = try decoder.decode(AIResponse.self, from: data)
                    
                    if aiResponse.success && !aiResponse.response.isEmpty {
                        self?.lastResponse = aiResponse
                        completion(.success(aiResponse))
                    } else if let errorMsg = aiResponse.error {
                        let apiError = AIError.apiError(errorMsg)
                        self?.error = apiError
                        completion(.failure(apiError))
                    } else if aiResponse.response.isEmpty {
                        let emptyError = AIError.emptyResponse
                        self?.error = emptyError
                        completion(.failure(emptyError))
                    } else {
                        self?.lastResponse = aiResponse
                        completion(.success(aiResponse))
                    }
                } catch {
                    print("❌ SmartAI Decode Error: \(error)")
                    self?.error = error
                    completion(.failure(error))
                }
            }
        }.resume()
    }
    
    // MARK: - Async/Await Version
    
    func chat(message: String, forceTaskType: TaskType? = nil) async throws -> AIResponse {
        return try await withCheckedThrowingContinuation { continuation in
            chat(message: message, forceTaskType: forceTaskType) { result in
                switch result {
                case .success(let response):
                    continuation.resume(returning: response)
                case .failure(let error):
                    continuation.resume(throwing: error)
                }
            }
        }
    }
    
    // MARK: - Convenience Methods
    
    /// Quick explanation
    func explain(_ topic: String) async throws -> AIResponse {
        try await chat(message: topic, forceTaskType: .educationalExplanation)
    }
    
    /// Generate a full course
    func createCourse(on topic: String) async throws -> AIResponse {
        try await chat(message: "Create a comprehensive course on \(topic)", forceTaskType: .courseGeneration)
    }
    
    /// Generate quiz questions
    func quiz(on topic: String) async throws -> AIResponse {
        try await chat(message: "Quiz me on \(topic)", forceTaskType: .quizGeneration)
    }
    
    /// Summarize content
    func summarize(_ content: String) async throws -> AIResponse {
        try await chat(message: content, forceTaskType: .noteSummarization)
    }
}

// MARK: - Task Types

enum TaskType: String {
    case educationalExplanation = "EDUCATIONAL_EXPLANATION"
    case courseGeneration = "COURSE_GENERATION"
    case quizGeneration = "QUIZ_GENERATION"
    case noteSummarization = "NOTE_SUMMARIZATION"
    case practiceQuestions = "PRACTICE_QUESTIONS"
    case general = "GENERAL"
}

// MARK: - Response Models

struct AIResponse: Codable {
    let response: String
    let taskType: String
    let tokensUsed: Int?
    let modelUsed: String
    let latencyMs: Int
    let success: Bool
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case response
        case taskType = "task_type"
        case tokensUsed = "tokens_used"
        case modelUsed = "model_used"
        case latencyMs = "latency_ms"
        case success
        case error
    }
}

// MARK: - Errors

enum AIError: LocalizedError {
    case invalidURL
    case noData
    case emptyResponse
    case apiError(String)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid API URL"
        case .noData:
            return "No data received from server"
        case .emptyResponse:
            return "Received empty response from AI"
        case .apiError(let message):
            return message
        }
    }
}

// MARK: - SwiftUI Integration Example

/*
 Usage in SwiftUI View:
 
 struct ChatView: View {
     @StateObject private var aiService = SmartAIService.shared
     @State private var message = ""
     @State private var response = ""
     
     var body: some View {
         VStack {
             TextField("Ask Lyo...", text: $message)
                 .textFieldStyle(.roundedBorder)
             
             Button("Send") {
                 Task {
                     do {
                         // Auto-detects: "teach me" → course, "what is" → explanation
                         let result = try await aiService.chat(message: message)
                         response = result.response
                     } catch {
                         response = "Error: \(error.localizedDescription)"
                     }
                 }
             }
             .disabled(aiService.isLoading)
             
             if aiService.isLoading {
                 ProgressView()
             }
             
             ScrollView {
                 Text(response)
                     .padding()
             }
         }
         .padding()
     }
 }
 */
