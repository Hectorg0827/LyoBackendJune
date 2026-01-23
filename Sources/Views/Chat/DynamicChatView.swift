import SwiftUI
import Combine

// MARK: - Dynamic Chat View with Full A2UI Integration
struct DynamicChatView: View {
    @StateObject private var chatService = DynamicChatService()
    @State private var message = ""
    @State private var isLoading = false
    @FocusState private var isInputFocused: Bool
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            // Messages with A2UI components
            messagesView

            // Input area
            inputArea
        }
        .navigationTitle("AI Chat")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button("Close") {
                    dismiss()
                }
            }

            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button("New Chat") {
                        chatService.startNewChat()
                    }

                    Button("Clear History") {
                        chatService.clearHistory()
                    }

                    Divider()

                    Button("Export Chat") {
                        chatService.exportChat()
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
        .onAppear {
            chatService.initializeChat()
        }
    }

    // MARK: - Messages View

    private var messagesView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 16) {
                    ForEach(chatService.messages) { message in
                        DynamicMessageView(
                            message: message,
                            onAction: handleMessageAction
                        )
                        .id(message.id)
                    }

                    if isLoading {
                        LoadingMessageView()
                            .id("loading")
                    }
                }
                .padding()
            }
            .onChange(of: chatService.messages.count) { _ in
                withAnimation(.easeOut(duration: 0.3)) {
                    proxy.scrollTo(chatService.messages.last?.id ?? "loading", anchor: .bottom)
                }
            }
            .onChange(of: isLoading) { loading in
                if loading {
                    withAnimation(.easeOut(duration: 0.3)) {
                        proxy.scrollTo("loading", anchor: .bottom)
                    }
                }
            }
        }
    }

    // MARK: - Input Area

    private var inputArea: some View {
        VStack(spacing: 0) {
            Divider()

            HStack(alignment: .bottom, spacing: 12) {
                // Message input
                TextField("Ask anything...", text: $message, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(1...5)
                    .focused($isInputFocused)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color(.systemGray6))
                    .cornerRadius(20)
                    .onSubmit {
                        sendMessage()
                    }

                // Send button
                Button(action: sendMessage) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title)
                        .foregroundColor(message.isEmpty ? .gray : .blue)
                }
                .disabled(message.isEmpty || isLoading)
            }
            .padding()
        }
        .background(Color(.systemBackground))
    }

    // MARK: - Actions

    private func sendMessage() {
        guard !message.isEmpty else { return }

        let userMessage = message
        message = ""
        isInputFocused = false
        isLoading = true

        Task {
            await chatService.sendMessage(userMessage)
            await MainActor.run {
                isLoading = false
            }
        }
    }

    private func handleMessageAction(_ action: A2UIAction) {
        Task {
            await chatService.handleMessageAction(action)
        }
    }
}

// MARK: - Dynamic Message View
struct DynamicMessageView: View {
    let message: ChatMessage
    let onAction: ((A2UIAction) -> Void)?

    var body: some View {
        HStack {
            if message.isUser {
                Spacer(minLength: 60)
            }

            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 8) {
                // Text content
                if !message.content.isEmpty {
                    Text(message.content)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(backgroundColor)
                        .foregroundColor(textColor)
                        .cornerRadius(20)
                }

                // A2UI component
                if let component = message.uiComponent {
                    A2UIRenderer(component: component, onAction: onAction)
                        .background(Color(.systemBackground))
                        .cornerRadius(12)
                        .shadow(radius: 1)
                }

                // Timestamp
                Text(message.timestamp, style: .time)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            if !message.isUser {
                Spacer(minLength: 60)
            }
        }
    }

    private var backgroundColor: Color {
        message.isUser ? .blue : Color(.systemGray5)
    }

    private var textColor: Color {
        message.isUser ? .white : .primary
    }
}

// MARK: - Loading Message View
struct LoadingMessageView: View {
    @State private var animating = false

    var body: some View {
        HStack {
            HStack(spacing: 4) {
                ForEach(0..<3) { index in
                    Circle()
                        .fill(Color.gray)
                        .frame(width: 8, height: 8)
                        .scaleEffect(animating ? 1.0 : 0.5)
                        .animation(
                            .easeInOut(duration: 0.6)
                                .repeatForever()
                                .delay(Double(index) * 0.2),
                            value: animating
                        )
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color(.systemGray5))
            .cornerRadius(20)

            Spacer()
        }
        .onAppear {
            animating = true
        }
    }
}

// MARK: - Dynamic Chat Service
@MainActor
class DynamicChatService: ObservableObject {
    @Published var messages: [ChatMessage] = []

    private let baseURL = "https://lyo-backend-production-830162750094.us-central1.run.app"
    private var sessionId: String?

    struct ChatMessage: Identifiable {
        let id = UUID().uuidString
        let content: String
        let isUser: Bool
        let timestamp: Date
        let uiComponent: A2UIComponent?

        init(content: String, isUser: Bool, uiComponent: A2UIComponent? = nil) {
            self.content = content
            self.isUser = isUser
            self.timestamp = Date()
            self.uiComponent = uiComponent
        }
    }

    func initializeChat() {
        if messages.isEmpty {
            let welcomeMessage = ChatMessage(
                content: "Hello! I'm Lyo, your AI learning assistant. How can I help you today?",
                isUser: false
            )
            messages.append(welcomeMessage)
        }
    }

    func sendMessage(_ text: String) async {
        // Add user message
        let userMessage = ChatMessage(content: text, isUser: true)
        messages.append(userMessage)

        // Call chat API with A2UI support
        do {
            let response = try await callChatAPI(message: text)

            // Create AI response with A2UI component
            let aiMessage = ChatMessage(
                content: response.response,
                isUser: false,
                uiComponent: response.uiComponent
            )
            messages.append(aiMessage)

            sessionId = response.conversationId

        } catch {
            let errorMessage = ChatMessage(
                content: "Sorry, I encountered an error. Please try again.",
                isUser: false
            )
            messages.append(errorMessage)
        }
    }

    func handleMessageAction(_ action: A2UIAction) async {
        // Handle action and potentially update messages
        print("Handling message action: \(action.actionId)")

        // For actions that result in new messages, add them to the conversation
        switch action.actionId {
        case "suggestion_tap":
            if let suggestion = action.params?["suggestion"] as? String {
                await sendMessage(suggestion)
            }
        case "course_tap", "lesson_tap", "quiz_answer":
            // These might trigger new chat messages or navigation
            let responseMessage = ChatMessage(
                content: "Great! Let me help you with that.",
                isUser: false
            )
            messages.append(responseMessage)
        default:
            break
        }
    }

    func startNewChat() {
        messages = []
        sessionId = nil
        initializeChat()
    }

    func clearHistory() {
        messages = []
        sessionId = nil
    }

    func exportChat() {
        // Export chat functionality
        print("Exporting chat...")
    }

    // MARK: - API Call

    private func callChatAPI(message: String) async throws -> ChatAPIResponse {
        let url = URL(string: "\(baseURL)/api/v1/chat")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer test-token", forHTTPHeaderField: "Authorization")

        let requestBody: [String: Any] = [
            "message": message,
            "conversation_history": [],
            "include_chips": 0,
            "include_ctas": 0
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)

        print("🌐 Calling chat API: \(url)")
        print("📝 Request: \(String(data: request.httpBody!, encoding: .utf8) ?? "nil")")

        let (data, response) = try await URLSession.shared.data(for: request)

        print("📡 Response status: \((response as? HTTPURLResponse)?.statusCode ?? -1)")
        print("📄 Response data: \(String(data: data, encoding: .utf8) ?? "nil")")

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            print("❌ HTTP Error: \((response as? HTTPURLResponse)?.statusCode ?? -1)")
            throw URLError(.badServerResponse)
        }

        do {
            let chatResponse = try JSONDecoder().decode(ChatAPIResponse.self, from: data)
            print("✅ Decoded response. UI Component: \(chatResponse.uiComponent?.type ?? "none")")
            return chatResponse
        } catch {
            print("❌ JSON Decode Error: \(error)")
            throw error
        }
    }

    struct ChatAPIResponse: Codable {
        let response: String
        let conversationId: String?
        let uiComponentRaw: [UiComponentWrapper]?

        // Computed property to extract A2UI component
        var uiComponent: A2UIComponent? {
            guard let rawComponents = uiComponentRaw,
                  let firstWrapper = rawComponents.first,
                  firstWrapper.type == "a2ui",
                  let componentJsonString = firstWrapper.component else {
                return nil
            }

            // Parse the nested JSON string
            guard let jsonData = componentJsonString.data(using: .utf8) else {
                print("❌ Failed to convert component JSON string to data")
                return nil
            }

            do {
                let component = try JSONDecoder().decode(A2UIComponent.self, from: jsonData)
                print("✅ Successfully parsed A2UI component: \(component.type)")
                return component
            } catch {
                print("❌ Failed to decode A2UI component: \(error)")
                return nil
            }
        }

        enum CodingKeys: String, CodingKey {
            case response
            case conversationId = "conversation_id"
            case uiComponentRaw = "ui_component"
        }
    }

    struct UiComponentWrapper: Codable {
        let type: String
        let component: String?
    }
}

#Preview {
    NavigationView {
        DynamicChatView()
    }
}