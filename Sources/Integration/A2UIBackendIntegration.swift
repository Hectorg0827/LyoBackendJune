import SwiftUI
import Combine
import Foundation

// MARK: - A2UI Backend Integration Example

struct A2UIBackendIntegrationView: View {
    @StateObject private var backendService = A2UIBackendService()
    @State private var currentScreen = "dashboard"
    @State private var isLoading = false
    @State private var error: String?

    var body: some View {
        NavigationView {
            VStack {
                if isLoading {
                    ProgressView("Loading UI...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let error = error {
                    ErrorView(error: error) {
                        loadScreen(currentScreen)
                    }
                } else if let component = backendService.currentComponent {
                    ScrollView {
                        A2UIRenderer(
                            component: component,
                            onAction: handleAction
                        )
                        .padding()
                    }
                } else {
                    Text("No content available")
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle("Dynamic UI")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu("Screens") {
                        ForEach(backendService.availableScreens, id: \.self) { screen in
                            Button(screen.capitalized) {
                                loadScreen(screen)
                            }
                        }
                    }
                }
            }
        }
        .onAppear {
            loadScreen(currentScreen)
        }
    }

    private func loadScreen(_ screenId: String) {
        isLoading = true
        error = nil
        currentScreen = screenId

        Task {
            do {
                try await backendService.loadScreen(screenId)
                isLoading = false
            } catch {
                self.error = error.localizedDescription
                isLoading = false
            }
        }
    }

    private func handleAction(_ action: A2UIAction) {
        Task {
            await backendService.handleAction(action)
        }
    }
}

// MARK: - API Models
struct A2UIScreenResponse: Codable {
    let component: A2UIComponent
    let screenId: String
    let sessionId: String
    let metadata: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case component, screenId = "screen_id", sessionId = "session_id", metadata
    }
}

struct A2UIActionResponse: Codable {
    let component: A2UIComponent?
    let navigation: [String: AnyCodable]?
    let message: String?
    let success: Bool
}

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if container.decodeNil() {
            value = NSNull()
        } else {
            throw DecodingError.typeMismatch(AnyCodable.self, DecodingError.Context(
                codingPath: decoder.codingPath,
                debugDescription: "AnyCodable value cannot be decoded"
            ))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()

        switch value {
        case let string as String:
            try container.encode(string)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let bool as Bool:
            try container.encode(bool)
        case is NSNull:
            try container.encodeNil()
        default:
            throw EncodingError.invalidValue(value, EncodingError.Context(
                codingPath: encoder.codingPath,
                debugDescription: "AnyCodable value cannot be encoded"
            ))
        }
    }
}

enum A2UIError: Error {
    case invalidResponse
    case httpError(Int)
    case decodingError(Error)
    case networkError(Error)

    var localizedDescription: String {
        switch self {
        case .invalidResponse:
            return "Invalid server response"
        case .httpError(let code):
            return "HTTP error: \(code)"
        case .decodingError(let error):
            return "Failed to parse response: \(error.localizedDescription)"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}

// MARK: - A2UI Backend Service
@MainActor
class A2UIBackendService: ObservableObject {
    @Published var currentComponent: A2UIComponent?
    @Published var availableScreens = ["dashboard", "course", "quiz", "chat", "settings"]

    private let baseURL = "http://127.0.0.1:8001"  // Local development
    private let fallbackURL = "https://lyo-backend-production-830162750094.us-central1.run.app"  // Production fallback
    private var cancellables = Set<AnyCancellable>()

    // MARK: - Load Screen from Backend

    func loadScreen(_ screenId: String) async throws {
        // Try local development server first, then fallback to production, then mock
        await tryLoadScreen(screenId, retryCount: 0)
    }

    private func tryLoadScreen(_ screenId: String, retryCount: Int) async {
        let urls = [baseURL, fallbackURL]

        guard retryCount < urls.count else {
            // All URLs failed, use mock data
            print("⚠️ All API endpoints failed, using mock data")
            do {
                try await simulateAPICall(screenId)
            } catch {
                print("❌ Even mock data failed: \(error)")
                currentComponent = createErrorComponent("Failed to load screen")
            }
            return
        }

        let currentURL = urls[retryCount]
        let url = URL(string: "\(currentURL)/a2ui/screen/\(screenId)")!

        print("🔄 Trying to load screen '\(screenId)' from: \(currentURL)")

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10.0  // 10 second timeout

        let requestBody = [
            "screen_id": screenId,
            "user_id": "ios_user_123",
            "context": [
                "platform": "ios",
                "version": "1.0",
                "capabilities": ["video", "audio", "camera", "location"]
            ]
        ] as [String: Any]

        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                print("⚠️ Invalid response from \(currentURL), trying next...")
                await tryLoadScreen(screenId, retryCount: retryCount + 1)
                return
            }

            guard httpResponse.statusCode == 200 else {
                print("⚠️ HTTP \(httpResponse.statusCode) from \(currentURL), trying next...")
                await tryLoadScreen(screenId, retryCount: retryCount + 1)
                return
            }

            let apiResponse = try JSONDecoder().decode(A2UIScreenResponse.self, from: data)
            currentComponent = apiResponse.component
            print("✅ Successfully loaded screen '\(screenId)' from: \(currentURL)")

        } catch {
            print("⚠️ Error loading from \(currentURL): \(error)")
            await tryLoadScreen(screenId, retryCount: retryCount + 1)
        }
    }

    // MARK: - Helper Functions

    private func createErrorComponent(_ message: String) -> A2UIComponent {
        return A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(20),
                "padding": .double(16),
                "align": .string("center")
            ],
            children: [
                A2UIComponent(
                    type: "image",
                    props: [
                        "systemName": .string("exclamationmark.triangle"),
                        "font": .string("largeTitle"),
                        "color": .string("#FF6B6B")
                    ]
                ),
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("Oops! Something went wrong"),
                        "font": .string("headline"),
                        "textAlign": .string("center")
                    ]
                ),
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string(message),
                        "font": .string("body"),
                        "textAlign": .string("center"),
                        "color": .string("#666666")
                    ]
                ),
                A2UIComponent(
                    type: "button",
                    props: [
                        "title": .string("Try Again"),
                        "action": .string("retry_load"),
                        "style": .string("primary")
                    ]
                )
            ]
        )
    }

    // MARK: - Handle Action from UI Component

    func handleAction(_ action: A2UIAction) async {
        print("🔄 Handling action: \(action.actionId)")

        // Handle some actions locally first
        switch action.actionId {
        case "retry_load":
            await tryLoadScreen("dashboard", retryCount: 0)
            return
        default:
            break
        }

        // Try to send action to backend
        await tryHandleAction(action, retryCount: 0)
    }

    private func tryHandleAction(_ action: A2UIAction, retryCount: Int) async {
        let urls = [baseURL, fallbackURL]

        guard retryCount < urls.count else {
            // All URLs failed, use local fallback
            print("⚠️ Action API endpoints failed, using local fallback")
            await simulateActionResponse(action)
            return
        }

        let currentURL = urls[retryCount]
        let url = URL(string: "\(currentURL)/a2ui/action")!

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 5.0  // Shorter timeout for actions

        let actionPayload = [
            "action_id": action.actionId,
            "component_id": action.componentId,
            "action_type": action.actionType,
            "params": action.params ?? [:]
        ] as [String: Any]

        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: actionPayload)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                await tryHandleAction(action, retryCount: retryCount + 1)
                return
            }

            guard httpResponse.statusCode == 200 else {
                await tryHandleAction(action, retryCount: retryCount + 1)
                return
            }

            let actionResponse = try JSONDecoder().decode(A2UIActionResponse.self, from: data)

            // Handle action response
            if let updatedComponent = actionResponse.component {
                currentComponent = updatedComponent
            }

            if let navigation = actionResponse.navigation {
                // Handle navigation - could trigger screen changes
                if let screenId = navigation["screen"]?.value as? String {
                    await tryLoadScreen(screenId, retryCount: 0)
                }
            }

            print("✅ Action handled successfully: \(actionResponse.message ?? "No message")")

        } catch {
            await tryHandleAction(action, retryCount: retryCount + 1)
        }
    }

    // MARK: - Mock API Simulation

    private func simulateAPICall(_ screenId: String) async throws {
        // Simulate network delay
        try await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds

        let mockComponent: A2UIComponent

        switch screenId {
        case "dashboard":
            mockComponent = createDashboardFromAPI()
        case "course":
            mockComponent = createCourseFromAPI()
        case "quiz":
            mockComponent = createQuizFromAPI()
        case "chat":
            mockComponent = createChatFromAPI()
        case "settings":
            mockComponent = createSettingsFromAPI()
        default:
            mockComponent = createDashboardFromAPI()
        }

        currentComponent = mockComponent
    }

    private func simulateActionResponse(_ action: A2UIAction) async {
        // Simulate processing time
        try? await Task.sleep(nanoseconds: 200_000_000) // 0.2 seconds

        // Handle specific actions that update the UI
        switch action.actionId {
        case "start_course":
            currentComponent = createCourseFromAPI()
        case "take_quiz":
            currentComponent = createQuizFromAPI()
        case "quiz_answer":
            if let updatedQuiz = updateQuizWithAnswer(action) {
                currentComponent = updatedQuiz
            }
        case "chat_message":
            if let updatedChat = addChatMessage(action) {
                currentComponent = updatedChat
            }
        default:
            print("Action handled: \(action.actionId)")
        }
    }

    // MARK: - API Response Creators (Mock Backend Responses)

    private func createDashboardFromAPI() -> A2UIComponent {
        // This simulates receiving JSON from your backend and parsing it
        let json = """
        {
            "type": "vstack",
            "props": {
                "spacing": 20,
                "padding": 16
            },
            "children": [
                {
                    "type": "text",
                    "props": {
                        "text": "Welcome to Lyo Learning! 🎓",
                        "font": "title",
                        "textAlign": "center",
                        "color": "#007AFF"
                    }
                },
                {
                    "type": "hstack",
                    "props": {
                        "spacing": 12
                    },
                    "children": [
                        {
                            "type": "coursecard",
                            "props": {
                                "title": "iOS Development",
                                "description": "Build your first iOS app with SwiftUI",
                                "progress": 68.5,
                                "difficulty": "Intermediate",
                                "duration": "4 hours",
                                "action": "start_ios_course"
                            }
                        },
                        {
                            "type": "coursecard",
                            "props": {
                                "title": "Machine Learning",
                                "description": "Introduction to AI and ML concepts",
                                "progress": 25.0,
                                "difficulty": "Beginner",
                                "duration": "6 hours",
                                "action": "start_ml_course"
                            }
                        }
                    ]
                },
                {
                    "type": "button",
                    "props": {
                        "title": "Take Quick Quiz",
                        "action": "take_quiz",
                        "style": "primary",
                        "fullWidth": true
                    }
                }
            ]
        }
        """

        return parseA2UIComponent(from: json) ?? A2UIComponent(type: "text", props: ["text": .string("Error loading dashboard")])
    }

    private func createCourseFromAPI() -> A2UIComponent {
        let json = """
        {
            "type": "vstack",
            "props": {
                "spacing": 16,
                "padding": 16
            },
            "children": [
                {
                    "type": "text",
                    "props": {
                        "text": "iOS Development Course",
                        "font": "title"
                    }
                },
                {
                    "type": "text",
                    "props": {
                        "text": "Lesson 3: SwiftUI State Management",
                        "font": "headline",
                        "color": "#007AFF"
                    }
                },
                {
                    "type": "progressbar",
                    "props": {
                        "progress": 68.5,
                        "color": "#007AFF"
                    }
                },
                {
                    "type": "video",
                    "props": {
                        "url": "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4",
                        "height": 200,
                        "controls": true,
                        "action": "video_interaction"
                    }
                },
                {
                    "type": "lessoncard",
                    "props": {
                        "title": "Next: Navigation and Routing",
                        "description": "Learn how to navigate between views",
                        "completed": false,
                        "duration": "15 min",
                        "type": "video",
                        "action": "next_lesson"
                    }
                }
            ]
        }
        """

        return parseA2UIComponent(from: json) ?? A2UIComponent(type: "text", props: ["text": .string("Error loading course")])
    }

    private func createQuizFromAPI() -> A2UIComponent {
        let json = """
        {
            "type": "vstack",
            "props": {
                "spacing": 24,
                "padding": 16
            },
            "children": [
                {
                    "type": "text",
                    "props": {
                        "text": "SwiftUI Knowledge Check",
                        "font": "title2",
                        "textAlign": "center"
                    }
                },
                {
                    "type": "text",
                    "props": {
                        "text": "Question 1 of 3",
                        "font": "subheadline",
                        "color": "#666666",
                        "textAlign": "center"
                    }
                },
                {
                    "type": "progressbar",
                    "props": {
                        "progress": 33,
                        "color": "#34C759"
                    }
                },
                {
                    "type": "quiz",
                    "props": {
                        "question": "What property wrapper is used for simple local state in SwiftUI?",
                        "options": ["@State", "@Binding", "@StateObject", "@ObservedObject"],
                        "correctAnswer": 0,
                        "selectedAnswer": null,
                        "action": "quiz_answer"
                    }
                }
            ]
        }
        """

        return parseA2UIComponent(from: json) ?? A2UIComponent(type: "text", props: ["text": .string("Error loading quiz")])
    }

    private func createChatFromAPI() -> A2UIComponent {
        let json = """
        {
            "type": "vstack",
            "props": {
                "spacing": 16,
                "padding": 16
            },
            "children": [
                {
                    "type": "text",
                    "props": {
                        "text": "AI Tutor Chat",
                        "font": "title2",
                        "textAlign": "center"
                    }
                },
                {
                    "type": "vstack",
                    "props": {
                        "spacing": 12,
                        "align": "leading"
                    },
                    "children": [
                        {
                            "type": "text",
                            "props": {
                                "text": "Hello! I'm your AI tutor. How can I help you today?",
                                "font": "body",
                                "padding": 12,
                                "backgroundColor": "#F0F0F0",
                                "cornerRadius": 16
                            }
                        }
                    ]
                },
                {
                    "type": "hstack",
                    "props": {
                        "spacing": 12
                    },
                    "children": [
                        {
                            "type": "textfield",
                            "props": {
                                "placeholder": "Ask me anything...",
                                "backgroundColor": "#F8F9FA",
                                "cornerRadius": 20,
                                "padding": 12
                            }
                        },
                        {
                            "type": "button",
                            "props": {
                                "title": "Send",
                                "action": "chat_message",
                                "style": "primary"
                            }
                        }
                    ]
                }
            ]
        }
        """

        return parseA2UIComponent(from: json) ?? A2UIComponent(type: "text", props: ["text": .string("Error loading chat")])
    }

    private func createSettingsFromAPI() -> A2UIComponent {
        let json = """
        {
            "type": "vstack",
            "props": {
                "spacing": 20,
                "padding": 16
            },
            "children": [
                {
                    "type": "text",
                    "props": {
                        "text": "Learning Settings",
                        "font": "title",
                        "textAlign": "center"
                    }
                },
                {
                    "type": "vstack",
                    "props": {
                        "spacing": 8,
                        "backgroundColor": "#F8F9FA",
                        "cornerRadius": 12,
                        "padding": 16
                    },
                    "children": [
                        {
                            "type": "hstack",
                            "children": [
                                {
                                    "type": "text",
                                    "props": {
                                        "text": "Dark Mode",
                                        "font": "body"
                                    }
                                },
                                {
                                    "type": "spacer"
                                },
                                {
                                    "type": "toggle",
                                    "props": {
                                        "value": false,
                                        "action": "toggle_dark_mode"
                                    }
                                }
                            ]
                        },
                        {
                            "type": "hstack",
                            "children": [
                                {
                                    "type": "text",
                                    "props": {
                                        "text": "Notifications",
                                        "font": "body"
                                    }
                                },
                                {
                                    "type": "spacer"
                                },
                                {
                                    "type": "toggle",
                                    "props": {
                                        "value": true,
                                        "action": "toggle_notifications"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        """

        return parseA2UIComponent(from: json) ?? A2UIComponent(type: "text", props: ["text": .string("Error loading settings")])
    }

    // MARK: - Action Response Handlers

    private func updateQuizWithAnswer(_ action: A2UIAction) -> A2UIComponent? {
        guard let selectedAnswer = action.params?["selectedAnswer"] as? Int else { return nil }

        let json = """
        {
            "type": "vstack",
            "props": {
                "spacing": 24,
                "padding": 16
            },
            "children": [
                {
                    "type": "text",
                    "props": {
                        "text": "SwiftUI Knowledge Check",
                        "font": "title2",
                        "textAlign": "center"
                    }
                },
                {
                    "type": "quiz",
                    "props": {
                        "question": "What property wrapper is used for simple local state in SwiftUI?",
                        "options": ["@State", "@Binding", "@StateObject", "@ObservedObject"],
                        "correctAnswer": 0,
                        "selectedAnswer": \(selectedAnswer),
                        "action": "quiz_answer"
                    }
                },
                {
                    "type": "button",
                    "props": {
                        "title": "Next Question",
                        "action": "next_question",
                        "style": "primary",
                        "fullWidth": true
                    }
                }
            ]
        }
        """

        return parseA2UIComponent(from: json)
    }

    private func addChatMessage(_ action: A2UIAction) -> A2UIComponent? {
        // In real implementation, this would add the new message to the chat
        // For demo, return updated chat UI with response
        let json = """
        {
            "type": "vstack",
            "props": {
                "spacing": 16,
                "padding": 16
            },
            "children": [
                {
                    "type": "text",
                    "props": {
                        "text": "AI Tutor Chat",
                        "font": "title2",
                        "textAlign": "center"
                    }
                },
                {
                    "type": "vstack",
                    "props": {
                        "spacing": 12,
                        "align": "leading"
                    },
                    "children": [
                        {
                            "type": "text",
                            "props": {
                                "text": "That's a great question! @State is indeed used for simple local state management in SwiftUI.",
                                "font": "body",
                                "padding": 12,
                                "backgroundColor": "#F0F0F0",
                                "cornerRadius": 16
                            }
                        }
                    ]
                },
                {
                    "type": "hstack",
                    "props": {
                        "spacing": 12
                    },
                    "children": [
                        {
                            "type": "textfield",
                            "props": {
                                "placeholder": "Ask me anything...",
                                "backgroundColor": "#F8F9FA",
                                "cornerRadius": 20,
                                "padding": 12
                            }
                        },
                        {
                            "type": "button",
                            "props": {
                                "title": "Send",
                                "action": "chat_message",
                                "style": "primary"
                            }
                        }
                    ]
                }
            ]
        }
        """

        return parseA2UIComponent(from: json)
    }

    // MARK: - JSON Parsing Helper

    private func parseA2UIComponent(from json: String) -> A2UIComponent? {
        guard let data = json.data(using: .utf8) else { return nil }

        do {
            return try JSONDecoder().decode(A2UIComponent.self, from: data)
        } catch {
            print("Error parsing A2UI component: \(error)")
            return nil
        }
    }
}

// MARK: - Error View
struct ErrorView: View {
    let error: String
    let onRetry: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundColor(.orange)

            Text("Failed to load content")
                .font(.headline)

            Text(error)
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Button("Retry", action: onRetry)
                .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}

#Preview {
    A2UIBackendIntegrationView()
}