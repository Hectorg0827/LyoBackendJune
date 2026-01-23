import SwiftUI

// MARK: - Enhanced Message Bubble with A2UI Support
struct EnhancedMessageBubble: View {
    let message: MultimodalMessage
    var onAction: ((A2UIAction) -> Void)?

    var body: some View {
        HStack {
            if message.isUser { Spacer(minLength: 60) }

            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 8) {
                // Main content bubble
                VStack(alignment: .leading, spacing: 12) {
                    // Text content (if any)
                    if !message.textContent.isEmpty {
                        Text(message.textContent)
                            .foregroundColor(textColor)
                    }

                    // A2UI Components
                    if let uiComponent = message.uiComponent {
                        A2UIRenderer(component: uiComponent, onAction: onAction)
                    }

                    // Media content
                    if let mediaUrl = message.mediaUrl {
                        AsyncImage(url: URL(string: mediaUrl)) { image in
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .cornerRadius(8)
                        } placeholder: {
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color(.systemGray5))
                                .frame(height: 100)
                                .overlay(
                                    Image(systemName: "photo")
                                        .foregroundColor(.secondary)
                                )
                        }
                        .frame(maxHeight: 200)
                    }

                    // Interactive suggestions
                    if !message.suggestions.isEmpty && !message.isUser {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Suggested actions:")
                                .font(.caption)
                                .foregroundColor(.secondary)

                            LazyVGrid(columns: [
                                GridItem(.adaptive(minimum: 120))
                            ], spacing: 8) {
                                ForEach(message.suggestions, id: \.self) { suggestion in
                                    Button(suggestion) {
                                        let action = A2UIAction(
                                            actionId: "suggestion_tap",
                                            componentId: message.id,
                                            actionType: "suggestion",
                                            params: ["suggestion": suggestion]
                                        )
                                        onAction?(action)
                                    }
                                    .font(.caption)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(Color.blue.opacity(0.1))
                                    .foregroundColor(.blue)
                                    .cornerRadius(12)
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(backgroundColor)
                .cornerRadius(20)

                // Timestamp
                Text(message.timestamp, style: .time)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            if !message.isUser { Spacer(minLength: 60) }
        }
    }

    private var backgroundColor: Color {
        if message.isError {
            return Color.red.opacity(0.2)
        }
        return message.isUser ? Color.blue : Color(.systemGray5)
    }

    private var textColor: Color {
        if message.isError {
            return .red
        }
        return message.isUser ? .white : .primary
    }
}

// MARK: - Multimodal Message Model
struct MultimodalMessage: Identifiable {
    let id: String
    let textContent: String
    let isUser: Bool
    let timestamp: Date
    var isError: Bool = false
    var intent: DetectedIntent? = nil
    var uiComponent: A2UIComponent? = nil
    var mediaUrl: String? = nil
    var suggestions: [String] = []
    var metadata: [String: Any] = [:]

    init(id: String = UUID().uuidString,
         textContent: String = "",
         isUser: Bool,
         timestamp: Date = Date(),
         isError: Bool = false,
         intent: DetectedIntent? = nil,
         uiComponent: A2UIComponent? = nil,
         mediaUrl: String? = nil,
         suggestions: [String] = [],
         metadata: [String: Any] = [:]) {
        self.id = id
        self.textContent = textContent
        self.isUser = isUser
        self.timestamp = timestamp
        self.isError = isError
        self.intent = intent
        self.uiComponent = uiComponent
        self.mediaUrl = mediaUrl
        self.suggestions = suggestions
        self.metadata = metadata
    }

    // Legacy compatibility with ChatMessage
    init(from chatMessage: ChatMessage) {
        self.id = chatMessage.id
        self.textContent = chatMessage.content
        self.isUser = chatMessage.isUser
        self.timestamp = chatMessage.timestamp
        self.isError = chatMessage.isError
        self.intent = chatMessage.intent
    }
}

// MARK: - Intent Detection Types
struct DetectedIntent {
    let type: String
    let confidence: Double
    let parameters: [String: Any]
}

#Preview {
    VStack {
        // Text message preview
        EnhancedMessageBubble(
            message: MultimodalMessage(
                textContent: "Hello! This is a regular text message.",
                isUser: true
            )
        )

        // A2UI component message preview
        EnhancedMessageBubble(
            message: MultimodalMessage(
                textContent: "Here's an interactive course card:",
                isUser: false,
                uiComponent: A2UIComponent(
                    type: "coursecard",
                    props: [
                        "title": .string("Swift Programming"),
                        "description": .string("Learn iOS development"),
                        "progress": .double(65.0),
                        "difficulty": .string("Intermediate"),
                        "duration": .string("2 hours")
                    ]
                ),
                suggestions: ["Tell me more", "Start learning", "Show similar courses"]
            )
        )
    }
    .padding()
}