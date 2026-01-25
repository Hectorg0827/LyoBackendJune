// CourseGenerationService.swift
// Lyo
//
// Course Generation Service with proper job_id handling
// Copy this file to: Lyo/Services/CourseGenerationService.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import Foundation
import Combine

// MARK: - Course Generation Service Extension for LyoAppAPIClient

extension LyoAppAPIClient {

    // MARK: - Course Generation

    /// Generate a new course from a topic request
    func generateCourse(
        topic: String,
        difficulty: String = "intermediate",
        estimatedHours: Double = 2.0
    ) -> AnyPublisher<CourseGenerationJobResponse, APIError> {
        var request = createRequest(for: "/api/v2/courses/generate", method: .POST)

        let courseRequest = CourseGenerationRequest(
            request: topic,
            difficulty: difficulty,
            estimatedHours: estimatedHours
        )

        do {
            request.httpBody = try JSONEncoder().encode(courseRequest)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }

        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: CourseGenerationJobResponse.self, decoder: JSONDecoder())
            .mapError { error in
                print("❌ Course generation decode error: \(error)")
                return APIError.networkError
            }
            .eraseToAnyPublisher()
    }

    /// Poll for course generation status
    func getCourseGenerationStatus(jobId: String) -> AnyPublisher<CourseGenerationStatusResponse, APIError> {
        let request = createRequest(for: "/api/v2/courses/status/\(jobId)", method: .GET)

        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: CourseGenerationStatusResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }

    /// Get completed course result
    func getCourseGenerationResult(jobId: String) -> AnyPublisher<CourseGenerationResultResponse, APIError> {
        let request = createRequest(for: "/api/v2/courses/\(jobId)/result", method: .GET)

        return session.dataTaskPublisher(for: request)
            .map(\.data)
            .decode(type: CourseGenerationResultResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
}

// MARK: - Course Generation Models

/// Request to generate a new course
struct CourseGenerationRequest: Codable {
    let request: String
    let difficulty: String
    let estimatedHours: Double

    enum CodingKeys: String, CodingKey {
        case request
        case difficulty
        case estimatedHours = "estimated_hours"
    }
}

/// Response when submitting a course generation job
struct CourseGenerationJobResponse: Codable {
    let jobId: String
    let status: String
    let qualityTier: String
    let estimatedCostUsd: Double
    let message: String
    let pollUrl: String

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status
        case qualityTier = "quality_tier"
        case estimatedCostUsd = "estimated_cost_usd"
        case message
        case pollUrl = "poll_url"
    }
}

/// Response when polling for job status
struct CourseGenerationStatusResponse: Codable {
    let jobId: String
    let status: CourseGenerationStatus
    let progress: Int?
    let currentStep: String?
    let estimatedTimeRemaining: Int?
    let message: String?
    let result: CourseResult?

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status
        case progress
        case currentStep = "current_step"
        case estimatedTimeRemaining = "estimated_time_remaining"
        case message
        case result
    }
}

/// Status of course generation job
enum CourseGenerationStatus: String, Codable {
    case pending = "pending"
    case inProgress = "in_progress"
    case completed = "completed"
    case failed = "failed"
    case cancelled = "cancelled"
}

/// Final course generation result
struct CourseGenerationResultResponse: Codable {
    let jobId: String
    let status: String
    let result: CourseResult
    let metadata: CourseGenerationMetadata?

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status
        case result
        case metadata
    }
}

/// Course content structure
struct CourseResult: Codable {
    let courseId: String
    let title: String
    let description: String
    let difficulty: String
    let estimatedHours: Double
    let modules: [CourseModule]
    let prerequisites: [String]?
    let learningObjectives: [String]
    let tags: [String]

    enum CodingKeys: String, CodingKey {
        case courseId = "course_id"
        case title
        case description
        case difficulty
        case estimatedHours = "estimated_hours"
        case modules
        case prerequisites
        case learningObjectives = "learning_objectives"
        case tags
    }
}

/// Course module structure
struct CourseModule: Codable {
    let moduleId: String
    let title: String
    let description: String
    let estimatedMinutes: Int
    let lessons: [CourseLesson]
    let quiz: CourseQuiz?

    enum CodingKeys: String, CodingKey {
        case moduleId = "module_id"
        case title
        case description
        case estimatedMinutes = "estimated_minutes"
        case lessons
        case quiz
    }
}

/// Individual lesson structure
struct CourseLesson: Codable {
    let lessonId: String
    let title: String
    let content: String
    let type: LessonType
    let estimatedMinutes: Int
    let resources: [LessonResource]?

    enum CodingKeys: String, CodingKey {
        case lessonId = "lesson_id"
        case title
        case content
        case type
        case estimatedMinutes = "estimated_minutes"
        case resources
    }
}

/// Type of lesson content
enum LessonType: String, Codable {
    case text = "text"
    case video = "video"
    case interactive = "interactive"
    case exercise = "exercise"
    case reading = "reading"
}

/// Additional lesson resources
struct LessonResource: Codable {
    let type: String
    let url: String
    let title: String
    let description: String?
}

/// Quiz structure for modules
struct CourseQuiz: Codable {
    let quizId: String
    let title: String
    let questions: [QuizQuestion]
    let passingScore: Int?

    enum CodingKeys: String, CodingKey {
        case quizId = "quiz_id"
        case title
        case questions
        case passingScore = "passing_score"
    }
}

/// Individual quiz question
struct QuizQuestion: Codable {
    let questionId: String
    let question: String
    let type: QuizQuestionType
    let options: [String]?
    let correctAnswer: QuizAnswer
    let explanation: String?

    enum CodingKeys: String, CodingKey {
        case questionId = "question_id"
        case question
        case type
        case options
        case correctAnswer = "correct_answer"
        case explanation
    }
}

/// Type of quiz question
enum QuizQuestionType: String, Codable {
    case multipleChoice = "multiple_choice"
    case trueFalse = "true_false"
    case shortAnswer = "short_answer"
}

/// Quiz answer structure
struct QuizAnswer: Codable {
    let value: String
    let index: Int?
}

/// Metadata about course generation process
struct CourseGenerationMetadata: Codable {
    let generatedAt: String
    let processingTime: Double
    let tokensUsed: Int?
    let qualityScore: Double?
    let version: String

    enum CodingKeys: String, CodingKey {
        case generatedAt = "generated_at"
        case processingTime = "processing_time"
        case tokensUsed = "tokens_used"
        case qualityScore = "quality_score"
        case version
    }
}

// MARK: - Course Generation View Model

@MainActor
class CourseGenerationViewModel: ObservableObject {
    @Published var currentJob: CourseGenerationJobResponse?
    @Published var jobStatus: CourseGenerationStatusResponse?
    @Published var courseResult: CourseResult?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var progress: Double = 0.0

    private let apiClient = LyoAppAPIClient.shared
    private var statusTimer: Timer?
    private var cancellables = Set<AnyCancellable>()

    // MARK: - Public Methods

    func generateCourse(topic: String, difficulty: String = "intermediate") {
        isLoading = true
        errorMessage = nil
        currentJob = nil
        jobStatus = nil
        courseResult = nil
        progress = 0.0

        print("🚀 Starting course generation for: \(topic)")

        apiClient.generateCourse(
            topic: topic,
            difficulty: difficulty
        )
        .receive(on: DispatchQueue.main)
        .sink(
            receiveCompletion: { [weak self] completion in
                if case .failure(let error) = completion {
                    print("❌ Course generation failed: \(error)")
                    self?.errorMessage = "Failed to start course generation: \(error.localizedDescription)"
                    self?.isLoading = false
                }
            },
            receiveValue: { [weak self] response in
                print("✅ Course generation job started: \(response.jobId)")
                self?.currentJob = response
                self?.startPollingForStatus(jobId: response.jobId)
            }
        )
        .store(in: &cancellables)
    }

    func cancelGeneration() {
        isLoading = false
        statusTimer?.invalidate()
        statusTimer = nil
        currentJob = nil
        jobStatus = nil
        courseResult = nil
        progress = 0.0
    }

    // MARK: - Private Methods

    private func startPollingForStatus(jobId: String) {
        statusTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.pollJobStatus(jobId: jobId)
        }
    }

    private func pollJobStatus(jobId: String) {
        apiClient.getCourseGenerationStatus(jobId: jobId)
            .receive(on: DispatchQueue.main)
            .sink(
                receiveCompletion: { [weak self] completion in
                    if case .failure(let error) = completion {
                        print("❌ Status poll failed: \(error)")
                        // Continue polling unless too many failures
                    }
                },
                receiveValue: { [weak self] status in
                    self?.handleStatusUpdate(status)
                }
            )
            .store(in: &cancellables)
    }

    private func handleStatusUpdate(_ status: CourseGenerationStatusResponse) {
        jobStatus = status

        if let progressValue = status.progress {
            progress = Double(progressValue) / 100.0
        }

        print("📊 Job \(status.jobId) status: \(status.status) (\(status.progress ?? 0)%)")

        switch status.status {
        case .completed:
            statusTimer?.invalidate()
            statusTimer = nil
            fetchCompletedCourse(jobId: status.jobId)

        case .failed, .cancelled:
            statusTimer?.invalidate()
            statusTimer = nil
            isLoading = false
            errorMessage = status.message ?? "Course generation failed"

        case .inProgress, .pending:
            // Continue polling
            break
        }
    }

    private func fetchCompletedCourse(jobId: String) {
        apiClient.getCourseGenerationResult(jobId: jobId)
            .receive(on: DispatchQueue.main)
            .sink(
                receiveCompletion: { [weak self] completion in
                    self?.isLoading = false
                    if case .failure(let error) = completion {
                        self?.errorMessage = "Failed to fetch course result: \(error.localizedDescription)"
                    }
                },
                receiveValue: { [weak self] result in
                    print("✅ Course generation completed: \(result.result.title)")
                    self?.courseResult = result.result
                    self?.isLoading = false
                    self?.progress = 1.0
                }
            )
            .store(in: &cancellables)
    }
}

// MARK: - API Error Extension

extension APIError {
    static let encodingError = APIError.networkError(NSError(
        domain: "CourseGeneration",
        code: -1,
        userInfo: [NSLocalizedDescriptionKey: "Failed to encode request"]
    ))

    static func networkError(_ error: Error) -> APIError {
        return .networkError(error)
    }

    var localizedDescription: String {
        switch self {
        case .networkError(let error):
            return error.localizedDescription
        default:
            return "An unknown error occurred"
        }
    }
}

// MARK: - APIError Definition (if not already defined)

enum APIError: Error {
    case networkError(Error)
    case decodingError
    case encodingError

    var localizedDescription: String {
        switch self {
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .decodingError:
            return "Failed to decode server response"
        case .encodingError:
            return "Failed to encode request"
        }
    }
}