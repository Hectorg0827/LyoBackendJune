import SwiftUI
import AVFoundation
import Combine

// MARK: - Enhanced AI Chat View with A2UI Support
struct EnhancedAIChatView: View {
    @StateObject private var viewModel = EnhancedAIChatViewModel()
    @State private var message = ""
    @State private var showVoiceSelector = false
    @FocusState private var isInputFocused: Bool
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            // Messages List with A2UI Support
            messagesView

            // Global suggestions (when available)
            if !viewModel.globalSuggestions.isEmpty && !viewModel.isLoading {
                globalSuggestionsView
            }

            // Input Area
            inputArea
        }
        .navigationTitle("AI Classroom")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button(action: { dismiss() }) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
            }

            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button(action: { viewModel.startNewSession() }) {
                        Label("New Session", systemImage: "plus.circle")
                    }

                    Button(action: { showVoiceSelector = true }) {
                        Label("Voice Settings", systemImage: "waveform")
                    }

                    Toggle(isOn: $viewModel.enableTTS) {
                        Label("Audio Mode", systemImage: viewModel.enableTTS ? "speaker.wave.3.fill" : "speaker.slash.fill")
                    }

                    Divider()

                    Button(role: .destructive, action: { viewModel.clearHistory() }) {
                        Label("Clear History", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .font(.title3)
                }
            }
        }
        .sheet(isPresented: $showVoiceSelector) {
            VoiceSelectorView(
                voices: viewModel.availableVoices,
                selectedVoice: $viewModel.selectedVoice
            )
        }
        .task {
            await viewModel.loadVoices()
        }
        .onAppear {
            if viewModel.messages.isEmpty {
                viewModel.addWelcomeMessage()
            }
        }
    }

    // MARK: - Messages View with A2UI

    private var messagesView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 16) {
                    ForEach(viewModel.messages) { message in
                        EnhancedMessageBubble(
                            message: message,
                            onAction: handleA2UIAction
                        )
                        .id(message.id)
                    }

                    if viewModel.isLoading {
                        TypingIndicatorView()
                            .id("typing")
                    }
                }
                .padding()
            }
            .onChange(of: viewModel.messages.count) { _ in
                withAnimation {
                    proxy.scrollTo(viewModel.messages.last?.id ?? "typing", anchor: .bottom)
                }
            }
        }
    }

    // MARK: - Global Suggestions View

    private var globalSuggestionsView: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.globalSuggestions, id: \.self) { suggestion in
                    Button(action: {
                        message = suggestion
                        sendMessage()
                    }) {
                        Text(suggestion)
                            .font(.subheadline)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(Color.blue.opacity(0.1))
                            .foregroundColor(.blue)
                            .cornerRadius(16)
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
        .background(Color(.systemBackground))
    }

    // MARK: - Input Area

    private var inputArea: some View {
        VStack(spacing: 0) {
            Divider()

            HStack(alignment: .bottom, spacing: 12) {
                // Voice toggle
                Button(action: { viewModel.enableTTS.toggle() }) {
                    Image(systemName: viewModel.enableTTS ? "speaker.wave.3.fill" : "speaker.slash.fill")
                        .foregroundColor(viewModel.enableTTS ? .blue : .gray)
                        .font(.title3)
                }

                // Text input
                TextField("Ask anything about any topic...", text: $message, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(1...5)
                    .focused($isInputFocused)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color(.systemGray6))
                    .cornerRadius(20)

                // Send button
                Button(action: sendMessage) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title)
                        .foregroundColor(message.isEmpty ? .gray : .blue)
                }
                .disabled(message.isEmpty || viewModel.isLoading)
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

        Task {
            await viewModel.sendMessage(userMessage)
        }
    }

    private func handleA2UIAction(_ action: A2UIAction) {
        Task {
            await viewModel.handleA2UIAction(action)
        }
    }
}

// MARK: - Enhanced View Model with A2UI Support
@MainActor
class EnhancedAIChatViewModel: ObservableObject {
    @Published var messages: [MultimodalMessage] = []
    @Published var globalSuggestions: [String] = []
    @Published var isLoading = false
    @Published var enableTTS = true
    @Published var selectedVoice: TTSVoice?
    @Published var availableVoices: [TTSVoice] = []

    private let apiClient = LyoAppAPIClient.shared
    private var audioPlayer: AVPlayer?
    private var sessionId: String?
    private var cancellables = Set<AnyCancellable>()

    // MARK: - Welcome Message with A2UI

    func addWelcomeMessage() {
        // Create welcome message with A2UI course grid
        let welcomeComponent = A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(16),
                "padding": .double(16)
            ],
            children: [
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("👋 Welcome to AI Classroom!"),
                        "font": .string("title2"),
                        "textAlign": .string("center"),
                        "color": .string("#007AFF")
                    ]
                ),
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("Choose what you'd like to explore today:"),
                        "font": .string("subheadline"),
                        "textAlign": .string("center")
                    ]
                ),
                A2UIComponent(
                    type: "grid",
                    props: [
                        "columns": .int(2),
                        "spacing": .double(12)
                    ],
                    children: [
                        createFeatureCard(
                            icon: "book.fill",
                            title: "Quick Learn",
                            description: "Explanations on any topic",
                            action: "quick_learn"
                        ),
                        createFeatureCard(
                            icon: "graduationcap.fill",
                            title: "Full Course",
                            description: "Complete courses with quizzes",
                            action: "full_course"
                        ),
                        createFeatureCard(
                            icon: "questionmark.circle.fill",
                            title: "Practice Quiz",
                            description: "Test your knowledge",
                            action: "practice_quiz"
                        ),
                        createFeatureCard(
                            icon: "laptopcomputer",
                            title: "Code Help",
                            description: "Programming assistance",
                            action: "code_help"
                        )
                    ]
                )
            ]
        )

        let welcome = MultimodalMessage(
            textContent: "",
            isUser: false,
            uiComponent: welcomeComponent,
            suggestions: ["Tell me about machine learning", "Create a Python course", "Help me with Swift"]
        )
        messages.append(welcome)
    }

    private func createFeatureCard(icon: String, title: String, description: String, action: String) -> A2UIComponent {
        return A2UIComponent(
            type: "button",
            props: [
                "action": .string(action),
                "style": .string("outline"),
                "fullWidth": .bool(true),
                "padding": .double(16),
                "cornerRadius": .double(12)
            ],
            children: [
                A2UIComponent(
                    type: "vstack",
                    props: [
                        "spacing": .double(8),
                        "align": .string("center")
                    ],
                    children: [
                        A2UIComponent(
                            type: "image",
                            props: [
                                "systemName": .string(icon),
                                "font": .string("title"),
                                "color": .string("#007AFF")
                            ]
                        ),
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string(title),
                                "font": .string("headline"),
                                "textAlign": .string("center")
                            ]
                        ),
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string(description),
                                "font": .string("caption"),
                                "textAlign": .string("center"),
                                "color": .string("#666666")
                            ]
                        )
                    ]
                )
            ]
        )
    }

    // MARK: - Public Methods

    func sendMessage(_ text: String) async {
        // Add user message
        let userMessage = MultimodalMessage(
            textContent: text,
            isUser: true
        )
        messages.append(userMessage)
        isLoading = true
        globalSuggestions = []

        // Send to API with A2UI support
        apiClient.sendEnhancedClassroomMessage(
            message: text,
            sessionId: sessionId,
            enableTTS: enableTTS,
            voiceId: selectedVoice?.id ?? "nova",
            includeUI: true
        )
        .receive(on: DispatchQueue.main)
        .sink(
            receiveCompletion: { [weak self] completion in
                self?.isLoading = false
                if case .failure = completion {
                    let errorMessage = MultimodalMessage(
                        textContent: "Sorry, something went wrong. Please try again.",
                        isUser: false,
                        isError: true
                    )
                    self?.messages.append(errorMessage)
                }
            },
            receiveValue: { [weak self] response in
                guard let self = self else { return }

                // Parse A2UI component if available
                var uiComponent: A2UIComponent?
                if let uiData = response.uiComponent {
                    uiComponent = try? JSONDecoder().decode(A2UIComponent.self, from: uiData)
                }

                // Add AI response with A2UI support
                let aiMessage = MultimodalMessage(
                    textContent: response.response,
                    isUser: false,
                    intent: response.intent,
                    uiComponent: uiComponent,
                    mediaUrl: response.mediaUrl,
                    suggestions: response.suggestions ?? []
                )
                self.messages.append(aiMessage)

                // Update session and global suggestions
                self.sessionId = response.sessionId
                if let newSuggestions = response.globalSuggestions {
                    self.globalSuggestions = newSuggestions
                }

                // Play audio if available
                if self.enableTTS, let audioUrlString = response.audioUrl,
                   let audioUrl = URL(string: audioUrlString) {
                    self.playAudio(from: audioUrl)
                }

                self.isLoading = false
            }
        )
        .store(in: &cancellables)
    }

    func handleA2UIAction(_ action: A2UIAction) async {
        let actionMessage = "Action: \(action.actionId)"

        // Handle specific actions
        switch action.actionId {
        case "quick_learn":
            await sendMessage("I want to learn about a specific topic quickly")
        case "full_course":
            await sendMessage("I want to create a complete course")
        case "practice_quiz":
            await sendMessage("I want to take a practice quiz")
        case "code_help":
            await sendMessage("I need help with programming")
        case "suggestion_tap":
            if let suggestion = action.params?["suggestion"] as? String {
                await sendMessage(suggestion)
            }
        case "course_tap":
            await sendMessage("Tell me more about this course")
        case "lesson_tap":
            await sendMessage("Start this lesson")
        case "answer_selected":
            if let selectedAnswer = action.params?["selectedAnswer"] as? Int {
                await sendMessage("I selected answer \(selectedAnswer)")
            }
        default:
            await sendMessage(actionMessage)
        }
    }

    func loadVoices() async {
        apiClient.getTTSVoices()
            .receive(on: DispatchQueue.main)
            .sink(
                receiveCompletion: { completion in
                    if case .failure(let error) = completion {
                        print("Failed to load voices: \(error)")
                    }
                },
                receiveValue: { [weak self] response in
                    self?.availableVoices = response.voices
                    if self?.selectedVoice == nil {
                        self?.selectedVoice = response.voices.first { $0.id == "nova" }
                    }
                }
            )
            .store(in: &cancellables)
    }

    func startNewSession() {
        messages = []
        globalSuggestions = []
        sessionId = nil
        addWelcomeMessage()
    }

    func clearHistory() {
        messages = []
        globalSuggestions = []
        sessionId = nil
    }

    // MARK: - Private Methods

    private func playAudio(from url: URL) {
        let playerItem = AVPlayerItem(url: url)
        audioPlayer = AVPlayer(playerItem: playerItem)
        audioPlayer?.play()
    }
}

// MARK: - Enhanced API Response Models
struct EnhancedClassroomResponse {
    let response: String
    let sessionId: String
    let intent: DetectedIntent?
    let suggestions: [String]?
    let globalSuggestions: [String]?
    let audioUrl: String?
    let uiComponent: Data?
    let mediaUrl: String?
}

// MARK: - API Client Extension for A2UI
extension LyoAppAPIClient {
    func sendEnhancedClassroomMessage(
        message: String,
        sessionId: String?,
        enableTTS: Bool = false,
        voiceId: String = "nova",
        includeUI: Bool = true
    ) -> AnyPublisher<EnhancedClassroomResponse, Error> {
        // This would connect to your enhanced backend endpoint
        // For now, return a mock response with A2UI component
        return Just(createMockEnhancedResponse(for: message))
            .setFailureType(to: Error.self)
            .eraseToAnyPublisher()
    }

    private func createMockEnhancedResponse(for message: String) -> EnhancedClassroomResponse {
        if message.lowercased().contains("course") {
            // Return course card component
            let courseComponent = A2UIComponent(
                type: "coursecard",
                props: [
                    "title": .string("Machine Learning Fundamentals"),
                    "description": .string("Learn the basics of ML algorithms and applications"),
                    "progress": .double(0),
                    "difficulty": .string("Beginner"),
                    "duration": .string("4 hours"),
                    "action": .string("course_tap")
                ]
            )

            let componentData = try? JSONEncoder().encode(courseComponent)

            return EnhancedClassroomResponse(
                response: "I've created a machine learning course for you:",
                sessionId: UUID().uuidString,
                intent: DetectedIntent(type: "course_request", confidence: 0.95, parameters: [:]),
                suggestions: ["Start learning", "Show course details", "Find similar courses"],
                globalSuggestions: ["Create another course", "Take a quiz", "Get help"],
                audioUrl: nil,
                uiComponent: componentData,
                mediaUrl: nil
            )
        } else if message.lowercased().contains("quiz") {
            // Return quiz component
            let quizComponent = A2UIComponent(
                type: "quiz",
                props: [
                    "question": .string("What is the primary goal of machine learning?"),
                    "options": .array([
                        .string("To replace human intelligence"),
                        .string("To learn patterns from data and make predictions"),
                        .string("To create artificial consciousness"),
                        .string("To store large amounts of data")
                    ]),
                    "correctAnswer": .int(1),
                    "action": .string("answer_selected")
                ]
            )

            let componentData = try? JSONEncoder().encode(quizComponent)

            return EnhancedClassroomResponse(
                response: "Here's a quiz question to test your knowledge:",
                sessionId: UUID().uuidString,
                intent: DetectedIntent(type: "quiz_request", confidence: 0.9, parameters: [:]),
                suggestions: ["Need a hint", "Explain the answer", "Next question"],
                globalSuggestions: ["Create a course", "Get coding help", "Learn something new"],
                audioUrl: nil,
                uiComponent: componentData,
                mediaUrl: nil
            )
        }

        return EnhancedClassroomResponse(
            response: "I understand you're asking about: \(message). How can I help you learn more about this topic?",
            sessionId: UUID().uuidString,
            intent: nil,
            suggestions: ["Explain in detail", "Create a course", "Give me examples"],
            globalSuggestions: ["Take a quiz", "Learn something new", "Get coding help"],
            audioUrl: nil,
            uiComponent: nil,
            mediaUrl: nil
        )
    }
}

#Preview {
    EnhancedAIChatView()
}