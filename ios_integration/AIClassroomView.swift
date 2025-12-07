// AIClassroomView.swift
// Lyo
//
// Main AI Classroom SwiftUI View - Award-Winning Learning Experience
// Copy this file to: Lyo/Views/AIClassroom/AIClassroomView.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import SwiftUI
import AVFoundation
import Combine

// MARK: - AI Classroom View

struct AIClassroomView: View {
    @StateObject private var viewModel = AIClassroomViewModel()
    @State private var message = ""
    @State private var showVoiceSelector = false
    @FocusState private var isInputFocused: Bool
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        VStack(spacing: 0) {
            // Messages List
            messagesView
            
            // Suggestions (when available)
            if !viewModel.suggestions.isEmpty && !viewModel.isLoading {
                suggestionsView
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
            // Add welcome message if empty
            if viewModel.messages.isEmpty {
                viewModel.addWelcomeMessage()
            }
        }
    }
    
    // MARK: - Messages View
    
    private var messagesView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 16) {
                    ForEach(viewModel.messages) { message in
                        MessageBubbleView(message: message)
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
    
    // MARK: - Suggestions View
    
    private var suggestionsView: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.suggestions, id: \.self) { suggestion in
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
}

// MARK: - View Model

@MainActor
class AIClassroomViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var suggestions: [String] = []
    @Published var isLoading = false
    @Published var enableTTS = true
    @Published var selectedVoice: TTSVoice?
    @Published var availableVoices: [TTSVoice] = []
    
    private let apiClient = LyoAppAPIClient.shared
    private var audioPlayer: AVPlayer?
    private var sessionId: String?
    private var cancellables = Set<AnyCancellable>()
    
    // MARK: - Welcome Message
    
    func addWelcomeMessage() {
        let welcome = ChatMessage(
            id: UUID().uuidString,
            content: "👋 Welcome to AI Classroom!\n\nI can help you with:\n• 📚 Quick explanations on any topic\n• 🎓 Full course generation\n• 📝 Quizzes and practice exercises\n• 💻 Code help and debugging\n• 📅 Study plan creation\n\nJust type what you want to learn!",
            isUser: false,
            timestamp: Date()
        )
        messages.append(welcome)
    }
    
    // MARK: - Public Methods
    
    func sendMessage(_ text: String) async {
        // Add user message
        let userMessage = ChatMessage(
            id: UUID().uuidString,
            content: text,
            isUser: true,
            timestamp: Date()
        )
        messages.append(userMessage)
        isLoading = true
        suggestions = []
        
        // Use the LyoAppAPIClient extension
        apiClient.sendClassroomMessage(
            message: text,
            sessionId: sessionId,
            enableTTS: enableTTS,
            voiceId: selectedVoice?.id ?? "nova"
        )
        .receive(on: DispatchQueue.main)
        .sink(
            receiveCompletion: { [weak self] completion in
                self?.isLoading = false
                if case .failure = completion {
                    let errorMessage = ChatMessage(
                        id: UUID().uuidString,
                        content: "Sorry, something went wrong. Please try again.",
                        isUser: false,
                        timestamp: Date(),
                        isError: true
                    )
                    self?.messages.append(errorMessage)
                }
            },
            receiveValue: { [weak self] response in
                guard let self = self else { return }
                
                // Add AI response
                let aiMessage = ChatMessage(
                    id: UUID().uuidString,
                    content: response.response,
                    isUser: false,
                    timestamp: Date(),
                    intent: response.intent
                )
                self.messages.append(aiMessage)
                
                // Update session and suggestions
                self.sessionId = response.sessionId
                if let newSuggestions = response.suggestions {
                    self.suggestions = newSuggestions
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
        suggestions = []
        sessionId = nil
        addWelcomeMessage()
    }
    
    func clearHistory() {
        messages = []
        suggestions = []
        sessionId = nil
    }
    
    // MARK: - Private Methods
    
    private func playAudio(from url: URL) {
        let playerItem = AVPlayerItem(url: url)
        audioPlayer = AVPlayer(playerItem: playerItem)
        audioPlayer?.play()
    }
}

// MARK: - Supporting Views

struct ChatMessage: Identifiable {
    let id: String
    let content: String
    let isUser: Bool
    let timestamp: Date
    var isError: Bool = false
    var intent: DetectedIntent? = nil
}

struct MessageBubbleView: View {
    let message: ChatMessage
    
    var body: some View {
        HStack {
            if message.isUser { Spacer(minLength: 60) }
            
            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 4) {
                Text(message.content)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(backgroundColor)
                    .foregroundColor(textColor)
                    .cornerRadius(20)
                
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

struct TypingIndicatorView: View {
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
        .onAppear { animating = true }
    }
}

struct VoiceSelectorView: View {
    let voices: [TTSVoice]
    @Binding var selectedVoice: TTSVoice?
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        NavigationStack {
            List(voices) { voice in
                Button(action: {
                    selectedVoice = voice
                    dismiss()
                }) {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(voice.name)
                                .font(.headline)
                            Text(voice.description)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        
                        Spacer()
                        
                        if selectedVoice?.id == voice.id {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.blue)
                        }
                    }
                }
                .foregroundColor(.primary)
            }
            .navigationTitle("Select Voice")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

// MARK: - Preview

#Preview {
    AIClassroomView()
}
