// ProgressiveCourseService.swift
// Lyo
//
// Outline-first progressive course loading.
// Copy this file to: Lyo/Services/ProgressiveCourseService.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app
//
// Flow:
//   1. POST /api/v2/courses/outline   → instant scaffold (< 3s), fires background job
//   2. GET  /{jobId}/modules/{id}/stream → SSE: lesson_ready events as content generates
//   3. GET  /{jobId}/modules/{id}/generate → on-demand fallback if SSE fails
//   4. GET  /{jobId}/result           → full course when polling shows completed

import Foundation
import Combine

// MARK: - Progressive Course Stage

enum ProgressiveCourseStage: Equatable {
    case idle
    case scaffolding                          // POST /outline in flight
    case scaffoldReady(CourseScaffold)        // outline returned, background gen running
    case moduleLoading(moduleId: String)      // SSE open for a specific module
    case complete(ProgressiveCourse)          // all modules populated
    case failed(String)

    static func == (lhs: ProgressiveCourseStage, rhs: ProgressiveCourseStage) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle): return true
        case (.scaffolding, .scaffolding): return true
        case (.scaffoldReady(let a), .scaffoldReady(let b)): return a.courseId == b.courseId
        case (.moduleLoading(let a), .moduleLoading(let b)): return a == b
        case (.complete(let a), .complete(let b)): return a.courseId == b.courseId
        case (.failed(let a), .failed(let b)): return a == b
        default: return false
        }
    }
}

// MARK: - Scaffold Models (returned immediately from /outline)

struct CourseScaffold: Codable, Equatable {
    let courseId: String
    let title: String
    let description: String
    let difficulty: String
    let estimatedDuration: Int
    let modules: [ScaffoldModule]

    enum CodingKeys: String, CodingKey {
        case courseId = "course_id"
        case title, description, difficulty
        case estimatedDuration = "estimated_duration"
        case modules
    }
}

struct ScaffoldModule: Codable, Equatable, Identifiable {
    let id: String
    let title: String
    let description: String
}

// MARK: - Progressive Course (scaffold + loaded modules)

struct ProgressiveCourse: Equatable {
    let courseId: String
    let title: String
    let description: String
    let difficulty: String
    let estimatedDuration: Int
    var modules: [ProgressiveModule]

    init(scaffold: CourseScaffold) {
        self.courseId = scaffold.courseId
        self.title = scaffold.title
        self.description = scaffold.description
        self.difficulty = scaffold.difficulty
        self.estimatedDuration = scaffold.estimatedDuration
        self.modules = scaffold.modules.map { ProgressiveModule(scaffold: $0) }
    }
}

struct ProgressiveModule: Equatable, Identifiable {
    let id: String
    let title: String
    let description: String
    var state: ModuleLoadState

    enum ModuleLoadState: Equatable {
        case skeleton           // outline-only, content not fetched
        case streaming          // SSE open
        case ready([BackendLesson])  // lessons available
        case failed(String)

        static func == (lhs: ModuleLoadState, rhs: ModuleLoadState) -> Bool {
            switch (lhs, rhs) {
            case (.skeleton, .skeleton): return true
            case (.streaming, .streaming): return true
            case (.ready(let a), .ready(let b)): return a.count == b.count
            case (.failed(let a), .failed(let b)): return a == b
            default: return false
            }
        }
    }

    init(scaffold: ScaffoldModule) {
        self.id = scaffold.id
        self.title = scaffold.title
        self.description = scaffold.description
        self.state = .skeleton
    }
}

// MARK: - Backend Lesson Model (v2 internal format)

struct BackendLesson: Codable, Equatable, Identifiable {
    let id: String
    let title: String
    let content: String?
    let durationMinutes: Int
    let order: Int

    enum CodingKeys: String, CodingKey {
        case id, title, content, order
        case durationMinutes = "duration_minutes"
    }
}

// MARK: - Outline Request/Response

private struct OutlineRequest: Encodable {
    let request: String
    let qualityTier: String
    let userContext: [String: String]?

    enum CodingKeys: String, CodingKey {
        case request
        case qualityTier = "quality_tier"
        case userContext = "user_context"
    }
}

private struct OutlineResponse: Decodable {
    let courseId: String
    let title: String
    let description: String
    let difficulty: String
    let estimatedDuration: Int
    let outlineHash: String
    let modules: [ScaffoldModule]
    let status: String

    enum CodingKeys: String, CodingKey {
        case courseId = "course_id"
        case title, description, difficulty, status, modules
        case estimatedDuration = "estimated_duration"
        case outlineHash = "outline_hash"
    }
}

// MARK: - SSE Module Stream Events

private enum ModuleSSEEvent {
    case moduleStart(moduleId: String, title: String)
    case lessonReady(lesson: BackendLesson)
    case moduleComplete(lessons: [BackendLesson], fromCache: Bool)
    case warning(String)
    case error(String)
    case done
    case unknown
}

// MARK: - Progressive Course View Model

@MainActor
class ProgressiveCourseViewModel: ObservableObject {
    @Published var stage: ProgressiveCourseStage = .idle
    @Published var course: ProgressiveCourse?
    @Published var errorMessage: String?

    private let baseURL: String
    private let session: URLSession
    private var cancellables = Set<AnyCancellable>()
    private var sseTask: URLSessionDataTask?
    private var jobId: String?

    init(
        baseURL: String = "https://lyo-backend-production-830162750094.us-central1.run.app",
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.session = session
    }

    // MARK: - Public API

    /// Stage 1: POST /outline — returns scaffold instantly, fires background gen
    func startCourse(topic: String, difficulty: String = "intermediate") {
        stage = .scaffolding
        errorMessage = nil
        course = nil

        let url = URL(string: "\(baseURL)/api/v2/courses/outline")!
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = OutlineRequest(
            request: topic,
            qualityTier: "standard",
            userContext: ["difficulty": difficulty]
        )
        req.httpBody = try? JSONEncoder().encode(body)

        URLSession.shared.dataTaskPublisher(for: req)
            .map(\.data)
            .decode(type: OutlineResponse.self, decoder: JSONDecoder())
            .receive(on: DispatchQueue.main)
            .sink(
                receiveCompletion: { [weak self] completion in
                    if case .failure(let err) = completion {
                        self?.stage = .failed("Failed to start course: \(err.localizedDescription)")
                        self?.errorMessage = err.localizedDescription
                    }
                },
                receiveValue: { [weak self] response in
                    guard let self else { return }
                    self.jobId = response.courseId

                    let scaffold = CourseScaffold(
                        courseId: response.courseId,
                        title: response.title,
                        description: response.description,
                        difficulty: response.difficulty,
                        estimatedDuration: response.estimatedDuration,
                        modules: response.modules
                    )
                    let progressiveCourse = ProgressiveCourse(scaffold: scaffold)
                    self.course = progressiveCourse
                    self.stage = .scaffoldReady(scaffold)
                }
            )
            .store(in: &cancellables)
    }

    /// Stage 2: Open SSE stream for a module — lessons arrive progressively
    func streamModule(moduleId: String) {
        guard let jobId else { return }
        stage = .moduleLoading(moduleId: moduleId)
        updateModuleState(moduleId: moduleId, state: .streaming)

        let url = URL(string: "\(baseURL)/api/v2/courses/\(jobId)/modules/\(moduleId)/stream")!
        var req = URLRequest(url: url)
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")

        var buffer = ""
        var collectedLessons: [BackendLesson] = []

        let task = URLSession.shared.dataTask(with: req) { [weak self] data, response, error in
            if let error {
                DispatchQueue.main.async {
                    self?.updateModuleState(moduleId: moduleId, state: .failed(error.localizedDescription))
                    self?.stage = .scaffoldReady(self?.scaffoldFromCourse() ?? CourseScaffold(courseId: "", title: "", description: "", difficulty: "", estimatedDuration: 0, modules: []))
                }
                return
            }

            guard let data, let chunk = String(data: data, encoding: .utf8) else { return }
            buffer += chunk

            while let range = buffer.range(of: "\n\n") {
                let rawEvent = String(buffer[buffer.startIndex..<range.lowerBound])
                buffer = String(buffer[range.upperBound...])

                guard let event = Self.parseSSEEvent(rawEvent) else { continue }

                DispatchQueue.main.async {
                    switch event {
                    case .lessonReady(let lesson):
                        collectedLessons.append(lesson)
                        // Update module with lessons received so far
                        self?.updateModuleState(moduleId: moduleId, state: .ready(collectedLessons))

                    case .moduleComplete(let lessons, _):
                        self?.updateModuleState(moduleId: moduleId, state: .ready(lessons))
                        self?.recheckCompletion()

                    case .error(let msg):
                        self?.updateModuleState(moduleId: moduleId, state: .failed(msg))

                    case .warning(let msg):
                        print("⚠️ Module \(moduleId) warning: \(msg)")

                    case .done:
                        self?.recheckCompletion()

                    default:
                        break
                    }
                }
            }
        }
        sseTask = task
        task.resume()
    }

    /// Stage 2 (fallback): POST /{jobId}/modules/{id}/generate — sync if SSE not available
    func generateModuleFallback(moduleId: String) {
        guard let jobId else { return }
        updateModuleState(moduleId: moduleId, state: .streaming)

        let url = URL(string: "\(baseURL)/api/v2/courses/\(jobId)/modules/\(moduleId)/generate")!
        var req = URLRequest(url: url)
        req.httpMethod = "POST"

        URLSession.shared.dataTaskPublisher(for: req)
            .map(\.data)
            .decode(type: ModuleResponseWrapper.self, decoder: JSONDecoder())
            .receive(on: DispatchQueue.main)
            .sink(
                receiveCompletion: { [weak self] completion in
                    if case .failure(let err) = completion {
                        self?.updateModuleState(moduleId: moduleId, state: .failed(err.localizedDescription))
                    }
                },
                receiveValue: { [weak self] wrapper in
                    self?.updateModuleState(moduleId: moduleId, state: .ready(wrapper.module.lessons))
                    self?.recheckCompletion()
                }
            )
            .store(in: &cancellables)
    }

    // MARK: - Private Helpers

    private func updateModuleState(moduleId: String, state: ProgressiveModule.ModuleLoadState) {
        guard var c = course else { return }
        guard let idx = c.modules.firstIndex(where: { $0.id == moduleId }) else { return }
        c.modules[idx].state = state
        course = c
    }

    private func recheckCompletion() {
        guard let c = course else { return }
        let allReady = c.modules.allSatisfy {
            if case .ready = $0.state { return true }
            return false
        }
        if allReady {
            stage = .complete(c)
        } else if case .moduleLoading = stage {
            // Back to scaffold-ready once the streamed module is done
            if let scaffold = scaffoldFromCourse() {
                stage = .scaffoldReady(scaffold)
            }
        }
    }

    private func scaffoldFromCourse() -> CourseScaffold? {
        guard let c = course else { return nil }
        return CourseScaffold(
            courseId: c.courseId,
            title: c.title,
            description: c.description,
            difficulty: c.difficulty,
            estimatedDuration: c.estimatedDuration,
            modules: c.modules.map { ScaffoldModule(id: $0.id, title: $0.title, description: $0.description) }
        )
    }

    // MARK: - SSE Event Parser

    private static func parseSSEEvent(_ raw: String) -> ModuleSSEEvent? {
        var eventType = ""
        var dataString = ""

        for line in raw.components(separatedBy: "\n") {
            if line.hasPrefix("event: ") {
                eventType = String(line.dropFirst(7))
            } else if line.hasPrefix("data: ") {
                dataString = String(line.dropFirst(6))
            }
        }

        guard !eventType.isEmpty, !dataString.isEmpty,
              let jsonData = dataString.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
        else { return nil }

        switch eventType {
        case "module_start":
            let id = json["module_id"] as? String ?? ""
            let title = json["title"] as? String ?? ""
            return .moduleStart(moduleId: id, title: title)

        case "lesson_ready":
            guard let lessonDict = json["lesson"] as? [String: Any],
                  let lessonData = try? JSONSerialization.data(withJSONObject: lessonDict),
                  let lesson = try? JSONDecoder().decode(BackendLesson.self, from: lessonData)
            else { return nil }
            return .lessonReady(lesson: lesson)

        case "module_complete":
            guard let moduleDict = json["module"] as? [String: Any],
                  let lessonsArray = moduleDict["lessons"] as? [[String: Any]],
                  let lessonsData = try? JSONSerialization.data(withJSONObject: lessonsArray),
                  let lessons = try? JSONDecoder().decode([BackendLesson].self, from: lessonsData)
            else { return nil }
            return .moduleComplete(lessons: lessons, fromCache: json["from_cache"] as? Bool ?? false)

        case "warning":
            return .warning(json["message"] as? String ?? "")

        case "error":
            return .error(json["message"] as? String ?? "Unknown error")

        case "done":
            return .done

        default:
            return .unknown
        }
    }
}

// MARK: - Module Response Wrapper (for fallback endpoint)

private struct ModuleResponseWrapper: Decodable {
    let courseId: String
    let module: ModuleWithLessons
    let status: String

    enum CodingKeys: String, CodingKey {
        case courseId = "course_id"
        case module, status
    }
}

private struct ModuleWithLessons: Decodable {
    let id: String
    let title: String
    let description: String
    let lessons: [BackendLesson]
}
