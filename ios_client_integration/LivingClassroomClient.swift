/**
 * Living Classroom - iOS WebSocket Client
 * ======================================
 *
 * Real-time WebSocket client for scene-by-scene streaming from the Living Classroom backend.
 * Replaces the current HTTP polling with bidirectional WebSocket communication.
 *
 * Architecture: iOS Client ←→ WebSocket ←→ Scene Lifecycle Engine ←→ Multi-Agent System
 */

import Foundation
import Combine
import SwiftUI

// MARK: - SDUI Models (matching Python backend exactly)

struct ScenePayload: Codable {
    let eventType: String
    let sessionId: String
    let scene: Scene
    let componentCount: Int

    enum CodingKeys: String, CodingKey {
        case eventType = "event_type"
        case sessionId = "session_id"
        case scene
        case componentCount = "component_count"
    }
}

struct Scene: Codable, Identifiable {
    let id: String
    let sceneId: String
    let sceneType: SceneType
    let components: [Component]
    let priority: Int
    let metadata: SceneMetadata?

    enum CodingKeys: String, CodingKey {
        case id = "scene_id"
        case sceneId = "scene_id"
        case sceneType = "scene_type"
        case components
        case priority
        case metadata
    }
}

enum SceneType: String, Codable, CaseIterable {
    case instruction = "instruction"
    case challenge = "challenge"
    case celebration = "celebration"
    case correction = "correction"
    case reflection = "reflection"
}

struct SceneMetadata: Codable {
    let estimatedDuration: Int?
    let difficultyLevel: String?
    let conceptTags: [String]?

    enum CodingKeys: String, CodingKey {
        case estimatedDuration = "estimated_duration_ms"
        case difficultyLevel = "difficulty_level"
        case conceptTags = "concept_tags"
    }
}

// MARK: - Component System (Server-Driven UI)

protocol Component: Codable, Identifiable {
    var id: String { get }
    var type: ComponentType { get }
    var priority: Int { get }
    var delayMs: Int? { get }
}

enum ComponentType: String, Codable {
    case teacherMessage = "TeacherMessage"
    case studentPrompt = "StudentPrompt"
    case quizCard = "QuizCard"
    case ctaButton = "CTAButton"
    case celebration = "Celebration"
    case codeEditor = "CodeEditor"
}

struct TeacherMessage: Component {
    let id: String
    let type: ComponentType = .teacherMessage
    let text: String
    let emotion: String?
    let audioMood: String?
    let priority: Int
    let delayMs: Int?
    let conceptTags: [String]?

    enum CodingKeys: String, CodingKey {
        case id = "component_id"
        case text
        case emotion
        case audioMood = "audio_mood"
        case priority
        case delayMs = "delay_ms"
        case conceptTags = "concept_tags"
    }
}

struct QuizCard: Component {
    let id: String
    let type: ComponentType = .quizCard
    let question: String
    let options: [QuizOption]
    let priority: Int
    let delayMs: Int?
    let conceptId: String?

    enum CodingKeys: String, CodingKey {
        case id = "component_id"
        case question
        case options
        case priority
        case delayMs = "delay_ms"
        case conceptId = "concept_id"
    }
}

struct QuizOption: Codable, Identifiable {
    let id: String
    let label: String
    let isCorrect: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case isCorrect = "is_correct"
    }
}

struct CTAButton: Component {
    let id: String
    let type: ComponentType = .ctaButton
    let label: String
    let actionIntent: ActionIntent
    let priority: Int
    let delayMs: Int?
    let style: String?

    enum CodingKeys: String, CodingKey {
        case id = "component_id"
        case label
        case actionIntent = "action_intent"
        case priority
        case delayMs = "delay_ms"
        case style
    }
}

enum ActionIntent: String, Codable {
    case `continue` = "continue"
    case retry = "retry"
    case hint = "hint"
    case skip = "skip"
    case celebrate = "celebrate"
    case nextTopic = "next_topic"
}

struct Celebration: Component {
    let id: String
    let type: ComponentType = .celebration
    let message: String
    let celebrationType: String
    let particleEffect: Bool?
    let priority: Int
    let delayMs: Int?

    enum CodingKeys: String, CodingKey {
        case id = "component_id"
        case message
        case celebrationType = "celebration_type"
        case particleEffect = "particle_effect"
        case priority
        case delayMs = "delay_ms"
    }
}

// MARK: - WebSocket Client Implementation

@MainActor
class LivingClassroomClient: ObservableObject {
    @Published var isConnected = false
    @Published var currentScene: Scene?
    @Published var components: [AnyComponent] = []
    @Published var connectionState: ConnectionState = .disconnected
    @Published var lastError: String?

    private var webSocketTask: URLSessionWebSocketTask?
    private var sessionId: String
    private let baseURL: String
    private let userToken: String
    private var heartbeatTimer: Timer?

    enum ConnectionState {
        case disconnected
        case connecting
        case connected
        case reconnecting
        case error(String)
    }

    init(baseURL: String = "wss://api.lyo.ai", userToken: String, sessionId: String? = nil) {
        self.baseURL = baseURL
        self.userToken = userToken
        self.sessionId = sessionId ?? UUID().uuidString
    }

    // MARK: - Connection Management

    func connect() async throws {
        connectionState = .connecting

        guard let url = URL(string: "\(baseURL)/api/v1/classroom/ws/connect") else {
            throw LivingClassroomError.invalidURL
        }

        var request = URLRequest(url: url)
        request.setValue("Bearer \(userToken)", forHTTPHeaderField: "Authorization")
        request.setValue(sessionId, forHTTPHeaderField: "X-Session-ID")

        let session = URLSession(configuration: .default)
        webSocketTask = session.webSocketTask(with: request)

        webSocketTask?.resume()

        // Start listening for messages
        await startListening()

        // Start heartbeat
        startHeartbeat()

        connectionState = .connected
        isConnected = true

        print("🎭 Living Classroom WebSocket connected - Session: \(sessionId)")
    }

    func disconnect() {
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        heartbeatTimer?.invalidate()
        connectionState = .disconnected
        isConnected = false
        print("👋 Living Classroom WebSocket disconnected")
    }

    // MARK: - Message Handling

    private func startListening() async {
        guard let webSocketTask = webSocketTask else { return }

        do {
            while isConnected {
                let message = try await webSocketTask.receive()
                await handleMessage(message)
            }
        } catch {
            print("❌ WebSocket listening error: \(error)")
            await handleConnectionError(error)
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) async {
        switch message {
        case .string(let text):
            await processTextMessage(text)
        case .data(let data):
            await processDataMessage(data)
        @unknown default:
            print("⚠️ Unknown WebSocket message type")
        }
    }

    private func processTextMessage(_ text: String) async {
        do {
            let data = Data(text.utf8)

            // Try to parse as ScenePayload
            if let scenePayload = try? JSONDecoder().decode(ScenePayload.self, from: data) {
                await handleScenePayload(scenePayload)
                return
            }

            // Try generic JSON
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                await handleGenericMessage(json)
            }

        } catch {
            print("❌ Failed to process message: \(error)")
        }
    }

    private func processDataMessage(_ data: Data) async {
        // Handle binary data if needed
        print("📦 Received binary message: \(data.count) bytes")
    }

    private func handleScenePayload(_ payload: ScenePayload) async {
        print("🎬 New scene received: \(payload.scene.sceneType) with \(payload.componentCount) components")

        currentScene = payload.scene

        // Convert components to renderable format
        var newComponents: [AnyComponent] = []

        for component in payload.scene.components {
            if let anyComponent = createAnyComponent(from: component) {
                newComponents.append(anyComponent)
            }
        }

        components = newComponents

        // Trigger progressive rendering with delays
        await progressivelyRenderComponents()
    }

    private func handleGenericMessage(_ json: [String: Any]) async {
        if let eventType = json["event_type"] as? String {
            switch eventType {
            case "connection_established":
                print("✅ Living Classroom connection established")
            case "scene_start":
                print("🎭 Scene starting...")
            case "scene_complete":
                print("✅ Scene complete")
            case "error":
                if let errorMessage = json["message"] as? String {
                    lastError = errorMessage
                    print("❌ Backend error: \(errorMessage)")
                }
            default:
                print("📨 Unknown event: \(eventType)")
            }
        }
    }

    private func handleConnectionError(_ error: Error) async {
        connectionState = .error(error.localizedDescription)
        isConnected = false

        // Attempt reconnection after delay
        try? await Task.sleep(nanoseconds: 3_000_000_000) // 3 seconds

        if case .error = connectionState {
            connectionState = .reconnecting
            try? await connect()
        }
    }

    // MARK: - Progressive Rendering

    private func progressivelyRenderComponents() async {
        let sortedComponents = components.sorted { $0.priority < $1.priority }

        for component in sortedComponents {
            // Apply delay if specified
            if let delayMs = component.delayMs, delayMs > 0 {
                let delaySeconds = Double(delayMs) / 1000.0
                try? await Task.sleep(nanoseconds: UInt64(delaySeconds * 1_000_000_000))
            }

            // Trigger component animation/rendering
            await animateComponentIn(component)
        }
    }

    private func animateComponentIn(_ component: AnyComponent) async {
        withAnimation(.easeInOut(duration: 0.5)) {
            // Component becomes visible with animation
            if let index = components.firstIndex(where: { $0.id == component.id }) {
                components[index].isVisible = true
            }
        }
    }

    // MARK: - User Actions

    func sendUserAction(intent: ActionIntent, data: [String: Any] = [:]) async throws {
        let payload = [
            "event_type": "user_action",
            "session_id": sessionId,
            "action_intent": intent.rawValue,
            "action_data": data,
            "timestamp": ISO8601DateFormatter().string(from: Date())
        ]

        let jsonData = try JSONSerialization.data(withJSONObject: payload)
        let message = URLSessionWebSocketTask.Message.data(jsonData)

        try await webSocketTask?.send(message)
        print("📤 User action sent: \(intent.rawValue)")
    }

    func submitQuizAnswer(questionId: String, selectedOptionId: String, isCorrect: Bool) async throws {
        try await sendUserAction(
            intent: .continue,
            data: [
                "action_type": "quiz_submit",
                "question_id": questionId,
                "selected_option": selectedOptionId,
                "is_correct": isCorrect
            ]
        )
    }

    func requestHint() async throws {
        try await sendUserAction(intent: .hint)
    }

    func continueLesson() async throws {
        try await sendUserAction(intent: .continue)
    }

    // MARK: - Heartbeat

    private func startHeartbeat() {
        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { @MainActor in
                try? await self?.sendHeartbeat()
            }
        }
    }

    private func sendHeartbeat() async throws {
        let ping = URLSessionWebSocketTask.Message.string("ping")
        try await webSocketTask?.send(ping)
    }
}

// MARK: - Component Type Erasure

struct AnyComponent: Identifiable {
    let id: String
    let type: ComponentType
    let priority: Int
    let delayMs: Int?
    var isVisible: Bool = false

    let component: Any // The actual component

    init<T: Component>(_ component: T) {
        self.id = component.id
        self.type = component.type
        self.priority = component.priority
        self.delayMs = component.delayMs
        self.component = component
    }
}

private func createAnyComponent(from json: [String: Any]) -> AnyComponent? {
    guard let typeString = json["type"] as? String,
          let componentType = ComponentType(rawValue: typeString) else {
        return nil
    }

    do {
        let data = try JSONSerialization.data(withJSONObject: json)

        switch componentType {
        case .teacherMessage:
            let component = try JSONDecoder().decode(TeacherMessage.self, from: data)
            return AnyComponent(component)
        case .quizCard:
            let component = try JSONDecoder().decode(QuizCard.self, from: data)
            return AnyComponent(component)
        case .ctaButton:
            let component = try JSONDecoder().decode(CTAButton.self, from: data)
            return AnyComponent(component)
        case .celebration:
            let component = try JSONDecoder().decode(Celebration.self, from: data)
            return AnyComponent(component)
        default:
            return nil
        }
    } catch {
        print("❌ Failed to decode component: \(error)")
        return nil
    }
}

// MARK: - Error Handling

enum LivingClassroomError: LocalizedError {
    case invalidURL
    case connectionFailed
    case invalidMessage
    case authenticationFailed

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid WebSocket URL"
        case .connectionFailed:
            return "Failed to connect to Living Classroom"
        case .invalidMessage:
            return "Invalid message format"
        case .authenticationFailed:
            return "Authentication failed"
        }
    }
}

// MARK: - SwiftUI Views

struct LivingClassroomView: View {
    @StateObject private var client = LivingClassroomClient(
        userToken: "your_token_here",
        sessionId: nil
    )

    var body: some View {
        VStack(spacing: 16) {
            // Connection Status
            HStack {
                Circle()
                    .fill(client.isConnected ? Color.green : Color.red)
                    .frame(width: 12, height: 12)

                Text(client.isConnected ? "Connected" : "Disconnected")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Spacer()

                Text("Living Classroom")
                    .font(.headline)
            }
            .padding(.horizontal)

            // Scene Components
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(client.components) { anyComponent in
                        ComponentView(component: anyComponent)
                            .opacity(anyComponent.isVisible ? 1.0 : 0.0)
                            .animation(.easeInOut, value: anyComponent.isVisible)
                    }
                }
                .padding()
            }
        }
        .onAppear {
            Task {
                try? await client.connect()
            }
        }
        .onDisappear {
            client.disconnect()
        }
    }
}

struct ComponentView: View {
    let component: AnyComponent

    var body: some View {
        Group {
            switch component.type {
            case .teacherMessage:
                if let teacherMessage = component.component as? TeacherMessage {
                    TeacherMessageView(message: teacherMessage)
                }
            case .quizCard:
                if let quiz = component.component as? QuizCard {
                    QuizCardView(quiz: quiz)
                }
            case .ctaButton:
                if let button = component.component as? CTAButton {
                    CTAButtonView(button: button)
                }
            case .celebration:
                if let celebration = component.component as? Celebration {
                    CelebrationView(celebration: celebration)
                }
            default:
                EmptyView()
            }
        }
        .transition(.opacity.combined(with: .slide))
    }
}

struct TeacherMessageView: View {
    let message: TeacherMessage

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 8) {
                Text(message.text)
                    .font(.body)
                    .multilineTextAlignment(.leading)

                if let emotion = message.emotion {
                    Text("Emotion: \(emotion)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()
        }
        .padding()
        .background(Color.blue.opacity(0.1))
        .cornerRadius(12)
    }
}

struct QuizCardView: View {
    let quiz: QuizCard
    @State private var selectedOption: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(quiz.question)
                .font(.headline)

            ForEach(quiz.options) { option in
                Button {
                    selectedOption = option.id
                    // Submit quiz answer via WebSocket
                } label: {
                    HStack {
                        Image(systemName: selectedOption == option.id ? "circle.fill" : "circle")
                            .foregroundColor(selectedOption == option.id ? .blue : .gray)

                        Text(option.label)
                            .foregroundColor(.primary)

                        Spacer()
                    }
                    .padding()
                    .background(Color.gray.opacity(0.1))
                    .cornerRadius(8)
                }
            }
        }
        .padding()
        .background(Color.green.opacity(0.1))
        .cornerRadius(12)
    }
}

struct CTAButtonView: View {
    let button: CTAButton

    var body: some View {
        Button {
            // Handle CTA action via WebSocket
        } label: {
            Text(button.label)
                .font(.headline)
                .foregroundColor(.white)
                .padding()
                .frame(maxWidth: .infinity)
                .background(Color.blue)
                .cornerRadius(12)
        }
    }
}

struct CelebrationView: View {
    let celebration: Celebration

    var body: some View {
        VStack {
            Text("🎉")
                .font(.largeTitle)
                .scaleEffect(2.0)
                .animation(.easeInOut.repeatCount(3), value: true)

            Text(celebration.message)
                .font(.headline)
                .multilineTextAlignment(.center)
        }
        .padding()
        .background(Color.yellow.opacity(0.2))
        .cornerRadius(12)
    }
}