// InteractiveCinemaService.swift
// Lyo
//
// Interactive Cinema + Adaptive Tutor Integration
// Copy this file to: Lyo/Services/InteractiveCinemaService.swift
//
// This service integrates with the new graph-based learning experience
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import Foundation
import Combine
import AVFoundation

// MARK: - Models

/// Node types in the learning graph
enum NodeType: String, Codable {
    case hook = "hook"
    case narrative = "narrative"
    case explanation = "explanation"
    case interaction = "interaction"
    case remediation = "remediation"
    case summary = "summary"
    case review = "review"
    case transition = "transition"
}

/// Interaction types for knowledge checks
enum InteractionType: String, Codable {
    case multipleChoice = "multiple_choice"
    case trueFalse = "true_false"
    case slider = "slider"
    case dragMatch = "drag_match"
    case shortAnswer = "short_answer"
    case prediction = "prediction"
}

/// A learning node in the interactive cinema experience
struct LearningNode: Codable, Identifiable {
    let id: String
    let nodeType: NodeType
    let title: String
    let scriptText: String?
    let visualCue: String?
    let durationSeconds: Int
    let audioUrl: String?
    let imageUrl: String?
    let interactionType: InteractionType?
    let interactionData: InteractionData?
    let isCheckpoint: Bool
    let moduleIndex: Int?
    let lessonIndex: Int?
    
    enum CodingKeys: String, CodingKey {
        case id
        case nodeType = "node_type"
        case title
        case scriptText = "script_text"
        case visualCue = "visual_cue"
        case durationSeconds = "duration_seconds"
        case audioUrl = "audio_url"
        case imageUrl = "image_url"
        case interactionType = "interaction_type"
        case interactionData = "interaction_data"
        case isCheckpoint = "is_checkpoint"
        case moduleIndex = "module_index"
        case lessonIndex = "lesson_index"
    }
}

/// Interaction data for knowledge checks
struct InteractionData: Codable {
    let question: String?
    let options: [InteractionOption]?
    let correctAnswer: String?
    let explanation: String?
    let hints: [String]?
    let timeLimit: Int?
    
    enum CodingKeys: String, CodingKey {
        case question
        case options
        case correctAnswer = "correct_answer"
        case explanation
        case hints
        case timeLimit = "time_limit"
    }
}

/// An option in a multiple choice interaction
struct InteractionOption: Codable, Identifiable {
    let id: String
    let label: String
    let isCorrect: Bool
    let feedback: String?
    let misconceptionTag: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case label
        case isCorrect = "is_correct"
        case feedback
        case misconceptionTag = "misconception_tag"
    }
}

/// Current playback state
struct PlaybackState: Codable {
    let courseId: String
    let currentNodeId: String
    let currentNode: LearningNode
    let nextNodes: [LearningNode]
    let completedNodes: [String]
    let progressPercent: Double
    let totalTimeSeconds: Int
    let canGoBack: Bool
    let isAtInteraction: Bool
    
    enum CodingKeys: String, CodingKey {
        case courseId = "course_id"
        case currentNodeId = "current_node_id"
        case currentNode = "current_node"
        case nextNodes = "next_nodes"
        case completedNodes = "completed_nodes"
        case progressPercent = "progress_percent"
        case totalTimeSeconds = "total_time_seconds"
        case canGoBack = "can_go_back"
        case isAtInteraction = "is_at_interaction"
    }
}

/// Response from starting a course
struct CourseStartResponse: Codable {
    let courseId: String
    let sessionId: String
    let currentNode: LearningNode
    let lookahead: [LearningNode]
    let totalNodes: Int
    let estimatedMinutes: Int
    
    enum CodingKeys: String, CodingKey {
        case courseId = "course_id"
        case sessionId = "session_id"
        case currentNode = "current_node"
        case lookahead
        case totalNodes = "total_nodes"
        case estimatedMinutes = "estimated_minutes"
    }
}

/// Response from advancing to next node
struct AdvanceResponse: Codable {
    let node: LearningNode
    let lookahead: [LearningNode]
    let progressPercent: Double
    let showAd: Bool
    let adConfig: AdConfig?
    let celebration: CelebrationConfig?
    
    enum CodingKeys: String, CodingKey {
        case node
        case lookahead
        case progressPercent = "progress_percent"
        case showAd = "show_ad"
        case adConfig = "ad_config"
        case celebration
    }
}

/// Ad configuration for client-side display
struct AdConfig: Codable {
    let adUnitId: String
    let adFormat: String
    let placementType: String
    
    enum CodingKeys: String, CodingKey {
        case adUnitId = "ad_unit_id"
        case adFormat = "ad_format"
        case placementType = "placement_type"
    }
}

/// Celebration configuration
struct CelebrationConfig: Codable {
    let type: String
    let animation: String
    let sound: String
    let message: String
    let durationMs: Int
    
    enum CodingKeys: String, CodingKey {
        case type
        case animation
        case sound
        case message
        case durationMs = "duration_ms"
    }
}

/// Response from submitting an interaction
struct InteractionSubmitResponse: Codable {
    let isCorrect: Bool
    let feedback: String
    let explanation: String?
    let masteryDelta: Double
    let newMastery: Double
    let celebration: CelebrationConfig?
    let nextNode: LearningNode?
    let remediationNode: LearningNode?
    
    enum CodingKeys: String, CodingKey {
        case isCorrect = "is_correct"
        case feedback
        case explanation
        case masteryDelta = "mastery_delta"
        case newMastery = "new_mastery"
        case celebration
        case nextNode = "next_node"
        case remediationNode = "remediation_node"
    }
}

/// Mastery state for a concept
struct MasteryState: Codable {
    let conceptId: String
    let conceptName: String
    let masteryScore: Double
    let confidence: Double
    let trend: String
    let lastPracticed: Date?
    
    enum CodingKeys: String, CodingKey {
        case conceptId = "concept_id"
        case conceptName = "concept_name"
        case masteryScore = "mastery_score"
        case confidence
        case trend
        case lastPracticed = "last_practiced"
    }
}

/// Review item for spaced repetition
struct ReviewItem: Codable, Identifiable {
    let id: String
    let conceptId: String
    let conceptName: String
    let courseId: String
    let courseName: String
    let nodeId: String
    let node: LearningNode
    let lastReview: Date?
    let nextReview: Date
    let easinessFactor: Double
    let intervalDays: Int
    let priority: Int
    
    enum CodingKeys: String, CodingKey {
        case id
        case conceptId = "concept_id"
        case conceptName = "concept_name"
        case courseId = "course_id"
        case courseName = "course_name"
        case nodeId = "node_id"
        case node
        case lastReview = "last_review"
        case nextReview = "next_review"
        case easinessFactor = "easiness_factor"
        case intervalDays = "interval_days"
        case priority
    }
}

/// Response from getting today's reviews
struct ReviewQueueResponse: Codable {
    let items: [ReviewItem]
    let totalDue: Int
    let streakDays: Int
    let estimatedMinutes: Int
    
    enum CodingKeys: String, CodingKey {
        case items
        case totalDue = "total_due"
        case streakDays = "streak_days"
        case estimatedMinutes = "estimated_minutes"
    }
}

/// Response from submitting a review
struct ReviewSubmitResponse: Codable {
    let isCorrect: Bool
    let feedback: String
    let nextReview: Date
    let intervalDays: Int
    let easinessFactor: Double
    let masteryDelta: Double
    let newMastery: Double
    let streakDays: Int
    let celebration: CelebrationConfig?
    
    enum CodingKeys: String, CodingKey {
        case isCorrect = "is_correct"
        case feedback
        case nextReview = "next_review"
        case intervalDays = "interval_days"
        case easinessFactor = "easiness_factor"
        case masteryDelta = "mastery_delta"
        case newMastery = "new_mastery"
        case streakDays = "streak_days"
        case celebration
    }
}

// MARK: - Interactive Cinema Service

/// Main service for Interactive Cinema + Adaptive Tutor experience
@MainActor
class InteractiveCinemaService: ObservableObject {
    static let shared = InteractiveCinemaService()
    
    // MARK: - Published State
    
    @Published var currentNode: LearningNode?
    @Published var playbackState: PlaybackState?
    @Published var isPlaying: Bool = false
    @Published var isLoading: Bool = false
    @Published var error: Error?
    @Published var progressPercent: Double = 0
    @Published var currentMastery: [String: MasteryState] = [:]
    @Published var reviewQueue: [ReviewItem] = []
    @Published var streakDays: Int = 0
    
    // MARK: - Private
    
    private let baseURL = "https://lyo-backend-production-830162750094.us-central1.run.app"
    private let apiPath = "/api/v1/playback"
    private var sessionId: String?
    private var audioPlayer: AVPlayer?
    private var prefetchedAssets: [String: (audioURL: URL?, imageURL: URL?)] = [:]
    private var cancellables = Set<AnyCancellable>()
    
    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
    
    private init() {}
    
    // MARK: - Course Playback
    
    /// Start playing a course
    func startCourse(courseId: String) async throws -> CourseStartResponse {
        isLoading = true
        defer { isLoading = false }
        
        let url = URL(string: "\(baseURL)\(apiPath)/courses/\(courseId)/start")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue("Bearer \(getAuthToken())", forHTTPHeaderField: "Authorization")
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw InteractiveCinemaError.serverError
        }
        
        let result = try decoder.decode(CourseStartResponse.self, from: data)
        
        self.sessionId = result.sessionId
        self.currentNode = result.currentNode
        self.isPlaying = true
        
        // Pre-fetch lookahead assets
        Task {
            await prefetchAssets(for: result.lookahead)
        }
        
        return result
    }
    
    /// Get current playback state
    func getCurrentState(courseId: String) async throws -> PlaybackState {
        let url = URL(string: "\(baseURL)\(apiPath)/courses/\(courseId)/current")!
        var request = URLRequest(url: url)
        request.addValue("Bearer \(getAuthToken())", forHTTPHeaderField: "Authorization")
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let state = try decoder.decode(PlaybackState.self, from: data)
        
        self.playbackState = state
        self.currentNode = state.currentNode
        self.progressPercent = state.progressPercent
        
        return state
    }
    
    /// Advance to the next node
    func advance(courseId: String) async throws -> AdvanceResponse {
        guard let currentNodeId = currentNode?.id else {
            throw InteractiveCinemaError.noCurrentNode
        }
        
        isLoading = true
        defer { isLoading = false }
        
        let url = URL(string: "\(baseURL)\(apiPath)/courses/\(courseId)/advance")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue("Bearer \(getAuthToken())", forHTTPHeaderField: "Authorization")
        
        let body = ["current_node_id": currentNodeId, "direction": "next"]
        request.httpBody = try JSONEncoder().encode(body)
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let result = try decoder.decode(AdvanceResponse.self, from: data)
        
        self.currentNode = result.node
        self.progressPercent = result.progressPercent
        
        // Handle celebration
        if let celebration = result.celebration {
            await showCelebration(celebration)
        }
        
        // Handle ad
        if result.showAd, let adConfig = result.adConfig {
            await showAd(adConfig)
        }
        
        // Pre-fetch lookahead
        Task {
            await prefetchAssets(for: result.lookahead)
        }
        
        return result
    }
    
    /// Submit an interaction response
    func submitInteraction(
        courseId: String,
        nodeId: String,
        answerId: String,
        timeTaken: Double
    ) async throws -> InteractionSubmitResponse {
        let url = URL(string: "\(baseURL)\(apiPath)/courses/\(courseId)/interaction/submit")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue("Bearer \(getAuthToken())", forHTTPHeaderField: "Authorization")
        
        let body: [String: Any] = [
            "node_id": nodeId,
            "answer_id": answerId,
            "time_taken_seconds": timeTaken
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let result = try decoder.decode(InteractionSubmitResponse.self, from: data)
        
        // Handle celebration
        if let celebration = result.celebration {
            await showCelebration(celebration)
        }
        
        // Navigate to next node or remediation
        if let remediation = result.remediationNode {
            self.currentNode = remediation
        } else if let next = result.nextNode {
            self.currentNode = next
        }
        
        return result
    }
    
    // MARK: - Spaced Repetition
    
    /// Get today's review queue
    func getTodaysReviews() async throws -> ReviewQueueResponse {
        let url = URL(string: "\(baseURL)\(apiPath)/review/today")!
        var request = URLRequest(url: url)
        request.addValue("Bearer \(getAuthToken())", forHTTPHeaderField: "Authorization")
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let result = try decoder.decode(ReviewQueueResponse.self, from: data)
        
        self.reviewQueue = result.items
        self.streakDays = result.streakDays
        
        return result
    }
    
    /// Submit a review response
    func submitReview(
        scheduleId: String,
        answerId: String,
        timeTaken: Double
    ) async throws -> ReviewSubmitResponse {
        let url = URL(string: "\(baseURL)\(apiPath)/review/submit")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue("Bearer \(getAuthToken())", forHTTPHeaderField: "Authorization")
        
        let body: [String: Any] = [
            "schedule_id": scheduleId,
            "answer_id": answerId,
            "time_taken_seconds": timeTaken
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let result = try decoder.decode(ReviewSubmitResponse.self, from: data)
        
        self.streakDays = result.streakDays
        
        // Remove completed item from queue
        reviewQueue.removeAll { $0.id == scheduleId }
        
        // Handle celebration
        if let celebration = result.celebration {
            await showCelebration(celebration)
        }
        
        return result
    }
    
    // MARK: - Audio Playback
    
    /// Play the audio for the current node
    func playCurrentNodeAudio() {
        guard let audioUrlString = currentNode?.audioUrl,
              let audioUrl = URL(string: audioUrlString) else {
            return
        }
        
        audioPlayer = AVPlayer(url: audioUrl)
        audioPlayer?.play()
    }
    
    /// Pause audio playback
    func pauseAudio() {
        audioPlayer?.pause()
    }
    
    /// Stop audio playback
    func stopAudio() {
        audioPlayer?.pause()
        audioPlayer = nil
    }
    
    // MARK: - Asset Prefetching
    
    /// Prefetch assets for upcoming nodes
    private func prefetchAssets(for nodes: [LearningNode]) async {
        for node in nodes {
            var audioURL: URL?
            var imageURL: URL?
            
            if let audioString = node.audioUrl {
                audioURL = URL(string: audioString)
                // Prefetch audio data
                if let url = audioURL {
                    _ = try? await URLSession.shared.data(from: url)
                }
            }
            
            if let imageString = node.imageUrl {
                imageURL = URL(string: imageString)
                // Prefetch image data
                if let url = imageURL {
                    _ = try? await URLSession.shared.data(from: url)
                }
            }
            
            prefetchedAssets[node.id] = (audioURL, imageURL)
        }
    }
    
    // MARK: - Celebrations
    
    /// Show a celebration animation
    private func showCelebration(_ celebration: CelebrationConfig) async {
        // Notify the UI to show celebration
        NotificationCenter.default.post(
            name: .showCelebration,
            object: nil,
            userInfo: [
                "type": celebration.type,
                "animation": celebration.animation,
                "sound": celebration.sound,
                "message": celebration.message,
                "duration": celebration.durationMs
            ]
        )
        
        // Play celebration sound
        // Implementation depends on your sound system
    }
    
    // MARK: - Ads
    
    /// Show an ad using AdMob
    private func showAd(_ adConfig: AdConfig) async {
        // Notify the UI to show ad
        NotificationCenter.default.post(
            name: .showAd,
            object: nil,
            userInfo: [
                "adUnitId": adConfig.adUnitId,
                "adFormat": adConfig.adFormat,
                "placementType": adConfig.placementType
            ]
        )
        
        // Wait for ad to complete before continuing
        // Implementation depends on your AdMob integration
    }
    
    /// Report ad impression to backend
    func reportAdImpression(adUnitId: String, placementType: String) async {
        guard let sessionId = sessionId else { return }
        
        let url = URL(string: "\(baseURL)\(apiPath)/ads/impression")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue("Bearer \(getAuthToken())", forHTTPHeaderField: "Authorization")
        
        let body: [String: String] = [
            "session_id": sessionId,
            "ad_unit_id": adUnitId,
            "placement_type": placementType
        ]
        request.httpBody = try? JSONEncoder().encode(body)
        
        _ = try? await URLSession.shared.data(for: request)
    }
    
    // MARK: - Helpers
    
    private func getAuthToken() -> String {
        // Get from your auth system
        return UserDefaults.standard.string(forKey: "authToken") ?? ""
    }
    
    /// Stop playback and clean up
    func stopPlayback() {
        stopAudio()
        currentNode = nil
        playbackState = nil
        isPlaying = false
        sessionId = nil
        prefetchedAssets.removeAll()
    }
}

// MARK: - Errors

enum InteractiveCinemaError: Error, LocalizedError {
    case serverError
    case noCurrentNode
    case networkError
    case decodingError
    
    var errorDescription: String? {
        switch self {
        case .serverError:
            return "Server returned an error"
        case .noCurrentNode:
            return "No current node to advance from"
        case .networkError:
            return "Network connection failed"
        case .decodingError:
            return "Failed to decode response"
        }
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let showCelebration = Notification.Name("showCelebration")
    static let showAd = Notification.Name("showAd")
}
