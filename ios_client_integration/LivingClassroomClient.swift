/**
 * Living Classroom - iOS WebSocket Client  (v2 — Interactive)
 * ============================================================
 *
 * Protocol (v2):
 *   SERVER → CLIENT  LyoStreamChunk  { card, card_index, total_cards, is_last_card }
 *   CLIENT → SERVER  { "action_intent": "continue" | "skip" | "hint" | "quiz_submit", ... }
 *   SERVER → CLIENT  { "is_complete": true }
 *
 * The server sends ONE card at a time and waits for the client to send
 * any action_intent message before advancing.  This file replaces the
 * previous passive-streaming version.
 */

import Foundation
import Combine
import SwiftUI
import AVFoundation

// MARK: - Card Models (mirror Python schemas exactly)

struct LyoStreamChunk: Codable {
    let metadata: LyoLessonMetadata?
    let card: LyoCard?
    let isComplete: Bool
    let cardIndex: Int?
    let totalCards: Int?
    let isLastCard: Bool?

    enum CodingKeys: String, CodingKey {
        case metadata
        case card
        case isComplete   = "is_complete"
        case cardIndex    = "card_index"
        case totalCards   = "total_cards"
        case isLastCard   = "is_last_card"
    }
}

struct LyoLessonMetadata: Codable {
    let topic: String
    let palette: LyoLessonPalette
}

struct LyoLessonPalette: Codable {
    let color1Hex: String
    let color2Hex: String
    let color3Hex: String

    enum CodingKeys: String, CodingKey {
        case color1Hex = "color1_hex"
        case color2Hex = "color2_hex"
        case color3Hex = "color3_hex"
    }
}

// MARK: - Polymorphic Card

struct LyoCard: Codable {
    let type: String

    // ConceptCard
    let keyTerm: String?
    let bodyText: String?

    // AnalogyCard
    let conceptSide: String?
    let analogySide: String?

    // DiagramCard
    let nodes: [DiagramNode]?
    let connections: [DiagramConnection]?

    // QuizCard
    let question: String?
    let options: [String]?
    let correctOptionIndex: Int?
    let explanation: String?

    // ReflectCard
    let prompt: String?

    // SummaryCard
    let title: String?
    let keyPoints: [String]?

    // TransitionCard — uses `title` above

    // Shared
    let voiceText: String?
    let audioUrl: String?

    enum CodingKeys: String, CodingKey {
        case type
        case keyTerm            = "key_term"
        case bodyText           = "body_text"
        case conceptSide        = "concept_side"
        case analogySide        = "analogy_side"
        case nodes, connections
        case question, options
        case correctOptionIndex = "correct_option_index"
        case explanation, prompt, title
        case keyPoints          = "key_points"
        case voiceText          = "voice_text"
        case audioUrl           = "audio_url"
    }
}

struct DiagramNode: Codable, Identifiable {
    let id: String
    let symbolName: String
    let label: String
    let colorHex: String?

    enum CodingKeys: String, CodingKey {
        case id
        case symbolName = "symbol_name"
        case label
        case colorHex  = "color_hex"
    }
}

struct DiagramConnection: Codable {
    let sourceId: String
    let targetId: String
    let label: String?

    enum CodingKeys: String, CodingKey {
        case sourceId = "source_id"
        case targetId = "target_id"
        case label
    }
}

// MARK: - Action Intent

enum ActionIntent: String, Codable {
    case `continue`  = "continue"
    case skip        = "skip"
    case hint        = "hint"
    case quizSubmit  = "quiz_submit"
    case nextTopic   = "next_topic"
}

// MARK: - Classroom ViewModel

@MainActor
class LivingClassroomViewModel: ObservableObject {
    // Published state
    @Published var metadata: LyoLessonMetadata?
    @Published var currentCard: LyoCard?
    @Published var cardIndex: Int = 0
    @Published var totalCards: Int = 0
    @Published var isComplete: Bool = false
    @Published var isConnected: Bool = false
    @Published var isWaitingForServer: Bool = false
    @Published var errorMessage: String?

    private var webSocketTask: URLSessionWebSocketTask?
    private var audioPlayer: AVPlayer?
    private var sessionId: String = UUID().uuidString
    private let baseURL: String

    // Heartbeat
    private var heartbeatTask: Task<Void, Never>?

    init(baseURL: String = "wss://lyo-production.up.railway.app") {
        self.baseURL = baseURL
    }

    // MARK: - Connect & Start Lesson

    func startLesson(topic: String) async {
        guard let url = URL(string: "\(baseURL)/api/v1/classroom/ws/lesson/\(topic.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? topic)") else {
            errorMessage = "Invalid classroom URL"
            return
        }

        // Reset state
        metadata     = nil
        currentCard  = nil
        cardIndex    = 0
        totalCards   = 0
        isComplete   = false
        isConnected  = false
        errorMessage = nil

        let request = URLRequest(url: url)
        let session = URLSession(configuration: .default)
        webSocketTask = session.webSocketTask(with: request)
        webSocketTask?.resume()

        isConnected = true
        startHeartbeat()
        await receiveMessages()
    }

    func disconnect() {
        heartbeatTask?.cancel()
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        isConnected = false
    }

    // MARK: - Receive Loop

    private func receiveMessages() async {
        guard let task = webSocketTask else { return }
        do {
            while isConnected {
                let message = try await task.receive()
                switch message {
                case .string(let text):
                    processMessage(text)
                case .data(let data):
                    if let text = String(data: data, encoding: .utf8) {
                        processMessage(text)
                    }
                @unknown default:
                    break
                }
            }
        } catch {
            if isConnected {
                errorMessage = "Connection lost: \(error.localizedDescription)"
                isConnected = false
            }
        }
    }

    private func processMessage(_ text: String) {
        guard let data = text.data(using: .utf8) else { return }
        do {
            let chunk = try JSONDecoder().decode(LyoStreamChunk.self, from: data)
            applyChunk(chunk)
        } catch {
            // Might be a plain ping/pong or error envelope — try generic JSON
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                if let err = json["error"] as? String {
                    errorMessage = err
                }
                if json["is_complete"] as? Bool == true {
                    isComplete = true
                    isConnected = false
                }
            }
        }
    }

    private func applyChunk(_ chunk: LyoStreamChunk) {
        if let meta = chunk.metadata {
            metadata = meta
            return
        }
        if chunk.isComplete {
            isComplete = true
            isConnected = false
            return
        }
        if let card = chunk.card {
            currentCard       = card
            cardIndex         = chunk.cardIndex ?? cardIndex
            totalCards        = chunk.totalCards ?? totalCards
            isWaitingForServer = false

            // Auto-play audio if available
            if let urlString = card.audioUrl, let url = URL(string: urlString) {
                playAudio(from: url)
            }
        }
    }

    // MARK: - User Actions (the "Continue" button)

    /// Call this when the user taps Continue / advances a slide.
    func sendContinue() async {
        await sendAction(intent: .continue)
    }

    func sendSkip() async {
        await sendAction(intent: .skip)
    }

    func sendQuizAnswer(selectedIndex: Int, isCorrect: Bool) async {
        let payload: [String: Any] = [
            "action_intent": ActionIntent.quizSubmit.rawValue,
            "selected_index": selectedIndex,
            "is_correct": isCorrect,
            "card_index": cardIndex
        ]
        await sendJSON(payload)
    }

    private func sendAction(intent: ActionIntent, extra: [String: Any] = [:]) async {
        var payload: [String: Any] = [
            "action_intent": intent.rawValue,
            "session_id": sessionId,
            "card_index": cardIndex
        ]
        extra.forEach { payload[$0] = $1 }
        await sendJSON(payload)
        isWaitingForServer = true
    }

    private func sendJSON(_ payload: [String: Any]) async {
        guard let task = webSocketTask, isConnected else { return }
        do {
            let data = try JSONSerialization.data(withJSONObject: payload)
            let message = URLSessionWebSocketTask.Message.data(data)
            try await task.send(message)
        } catch {
            print("⚠️ Failed to send message: \(error)")
        }
    }

    // MARK: - Heartbeat

    private func startHeartbeat() {
        heartbeatTask = Task {
            while isConnected {
                try? await Task.sleep(nanoseconds: 25_000_000_000) // 25 s
                guard isConnected, let task = webSocketTask else { break }
                try? await task.send(.string("ping"))
            }
        }
    }

    // MARK: - Audio

    private func playAudio(from url: URL) {
        let item = AVPlayerItem(url: url)
        audioPlayer = AVPlayer(playerItem: item)
        audioPlayer?.play()
    }

    // MARK: - Computed helpers

    var progressFraction: Double {
        guard totalCards > 0 else { return 0 }
        return Double(cardIndex + 1) / Double(totalCards)
    }

    var cardCountText: String {
        guard totalCards > 0 else { return "" }
        return "\(cardIndex + 1) / \(totalCards)"
    }
}

// MARK: - SwiftUI Views

struct LyoClassroomView: View {
    let topic: String
    @StateObject private var vm = LivingClassroomViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            // Background gradient from palette
            if let palette = vm.metadata?.palette,
               let c1 = Color(hex: palette.color1Hex),
               let c2 = Color(hex: palette.color2Hex) {
                LinearGradient(colors: [c1, c2], startPoint: .topLeading, endPoint: .bottomTrailing)
                    .ignoresSafeArea()
            } else {
                LinearGradient(colors: [Color(hex: "#2B1A4A") ?? .indigo, Color(hex: "#1A51AC") ?? .blue],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
                    .ignoresSafeArea()
            }

            VStack(spacing: 0) {
                // Navigation bar
                HStack {
                    Button(action: { dismiss() }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title2)
                            .foregroundColor(.white.opacity(0.8))
                    }
                    Spacer()
                    if vm.totalCards > 0 {
                        Text(vm.cardCountText)
                            .font(.caption.weight(.semibold))
                            .foregroundColor(.white.opacity(0.7))
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 8)

                // Progress bar
                if vm.totalCards > 0 {
                    ProgressView(value: vm.progressFraction)
                        .progressViewStyle(.linear)
                        .tint(.white)
                        .padding(.horizontal, 20)
                        .padding(.top, 8)
                }

                Spacer()

                // Card area
                Group {
                    if let error = vm.errorMessage {
                        ErrorCardView(message: error, onRetry: {
                            Task { await vm.startLesson(topic: topic) }
                        })
                    } else if vm.isComplete {
                        LessonCompleteView(topic: topic, onDismiss: { dismiss() })
                    } else if let card = vm.currentCard {
                        LyoCardView(card: card, vm: vm)
                            .transition(.asymmetric(
                                insertion: .move(edge: .trailing).combined(with: .opacity),
                                removal: .move(edge: .leading).combined(with: .opacity)
                            ))
                            .id(vm.cardIndex) // forces SwiftUI to animate on card change
                    } else {
                        // Loading / connecting
                        VStack(spacing: 16) {
                            ProgressView()
                                .tint(.white)
                                .scaleEffect(1.5)
                            Text("Preparing your lesson…")
                                .foregroundColor(.white.opacity(0.8))
                                .font(.subheadline)
                        }
                    }
                }
                .padding(.horizontal, 20)

                Spacer()
            }
        }
        .animation(.easeInOut(duration: 0.4), value: vm.cardIndex)
        .task {
            await vm.startLesson(topic: topic)
        }
        .onDisappear {
            vm.disconnect()
        }
    }
}

// MARK: - Card View (routes to specific card type)

struct LyoCardView: View {
    let card: LyoCard
    @ObservedObject var vm: LivingClassroomViewModel

    var body: some View {
        VStack(spacing: 24) {
            cardContent
            continueButton
        }
    }

    @ViewBuilder
    private var cardContent: some View {
        switch card.type {
        case "transition_card":
            TransitionCardView(card: card)
        case "concept_card":
            ConceptCardView(card: card)
        case "analogy_card":
            AnalogyCardView(card: card)
        case "diagram_card":
            DiagramCardView(card: card)
        case "reflect_card":
            ReflectCardView(card: card)
        case "quiz_card":
            QuizCardView(card: card, vm: vm)
        case "summary_card":
            SummaryCardView(card: card)
        default:
            UnknownCardView(type: card.type)
        }
    }

    // ─── THE CONTINUE BUTTON (now actually wired up) ───────────────────────
    @ViewBuilder
    private var continueButton: some View {
        // Quiz cards handle their own "submit" flow; all others get Continue
        if card.type != "quiz_card" {
            Button(action: {
                Task { await vm.sendContinue() }
            }) {
                HStack(spacing: 8) {
                    if vm.isWaitingForServer {
                        ProgressView().tint(.white)
                    }
                    Text(vm.isWaitingForServer ? "Loading…" : continueLabel)
                        .font(.headline)
                        .foregroundColor(.white)
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(
                    vm.isWaitingForServer
                        ? Color.white.opacity(0.2)
                        : Color.white.opacity(0.3)
                )
                .cornerRadius(16)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.white.opacity(0.5), lineWidth: 1)
                )
            }
            .disabled(vm.isWaitingForServer)
        }
    }

    private var continueLabel: String {
        guard vm.totalCards > 0 else { return "Continue →" }
        return vm.cardIndex >= vm.totalCards - 2 ? "Finish →" : "Continue →"
    }
}

// MARK: - Individual Card Views

struct TransitionCardView: View {
    let card: LyoCard
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "sparkles")
                .font(.system(size: 56))
                .foregroundColor(.white)
            Text(card.title ?? "Welcome")
                .font(.largeTitle.bold())
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
            if let voice = card.voiceText {
                Text(voice)
                    .font(.body)
                    .foregroundColor(.white.opacity(0.8))
                    .multilineTextAlignment(.center)
            }
        }
        .cardStyle()
    }
}

struct ConceptCardView: View {
    let card: LyoCard
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(card.keyTerm ?? "")
                .font(.title.bold())
                .foregroundColor(.white)
            Text(card.bodyText ?? "")
                .font(.body)
                .foregroundColor(.white.opacity(0.9))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardStyle()
    }
}

struct AnalogyCardView: View {
    let card: LyoCard
    var body: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Abstract").font(.caption.weight(.semibold)).foregroundColor(.white.opacity(0.6))
                Text(card.conceptSide ?? "").font(.body).foregroundColor(.white)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(Color.white.opacity(0.1))
            .cornerRadius(12)

            Image(systemName: "arrow.left.arrow.right")
                .foregroundColor(.white)
                .font(.title3)

            VStack(alignment: .leading, spacing: 8) {
                Text("Analogy").font(.caption.weight(.semibold)).foregroundColor(.white.opacity(0.6))
                Text(card.analogySide ?? "").font(.body).foregroundColor(.white)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(Color.white.opacity(0.1))
            .cornerRadius(12)
        }
        .cardStyle()
    }
}

struct DiagramCardView: View {
    let card: LyoCard
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let voice = card.voiceText {
                Text(voice).font(.subheadline).foregroundColor(.white.opacity(0.8))
            }
            if let nodes = card.nodes {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 80))], spacing: 16) {
                    ForEach(nodes) { node in
                        VStack(spacing: 6) {
                            Image(systemName: node.symbolName)
                                .font(.largeTitle)
                                .foregroundColor(.white)
                            Text(node.label)
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.8))
                                .multilineTextAlignment(.center)
                        }
                    }
                }
            }
        }
        .cardStyle()
    }
}

struct ReflectCardView: View {
    let card: LyoCard
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "thought.bubble")
                .font(.system(size: 48))
                .foregroundColor(.white.opacity(0.8))
            Text(card.prompt ?? "")
                .font(.title3.italic())
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
        }
        .cardStyle()
    }
}

struct QuizCardView: View {
    let card: LyoCard
    @ObservedObject var vm: LivingClassroomViewModel
    @State private var selectedIndex: Int? = nil
    @State private var revealed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(card.question ?? "")
                .font(.headline).foregroundColor(.white)

            if let options = card.options {
                ForEach(options.indices, id: \.self) { i in
                    Button(action: {
                        guard !revealed else { return }
                        selectedIndex = i
                        revealed = true
                        let correct = i == (card.correctOptionIndex ?? -1)
                        Task {
                            await vm.sendQuizAnswer(selectedIndex: i, isCorrect: correct)
                            // Auto-advance after a brief pause to show the result
                            try? await Task.sleep(nanoseconds: 1_500_000_000) // 1.5 s
                            await vm.sendContinue()
                        }
                    }) {
                        HStack {
                            Text(options[i]).foregroundColor(.white)
                            Spacer()
                            if revealed && i == (card.correctOptionIndex ?? -1) {
                                Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                            } else if revealed && i == selectedIndex {
                                Image(systemName: "xmark.circle.fill").foregroundColor(.red)
                            }
                        }
                        .padding()
                        .background(optionBackground(i))
                        .cornerRadius(12)
                    }
                    .disabled(revealed)
                }
            }

            if revealed, let explanation = card.explanation {
                Text(explanation)
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.8))
                    .padding(.top, 4)
            }
        }
        .cardStyle()
    }

    private func optionBackground(_ i: Int) -> Color {
        if !revealed            { return Color.white.opacity(0.15) }
        if i == card.correctOptionIndex { return Color.green.opacity(0.4) }
        if i == selectedIndex   { return Color.red.opacity(0.4) }
        return Color.white.opacity(0.1)
    }
}

struct SummaryCardView: View {
    let card: LyoCard
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(card.title ?? "Summary")
                .font(.title.bold()).foregroundColor(.white)
            if let points = card.keyPoints {
                ForEach(points, id: \.self) { point in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.green)
                        Text(point).foregroundColor(.white.opacity(0.9))
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardStyle()
    }
}

struct UnknownCardView: View {
    let type: String
    var body: some View {
        Text("Unknown card: \(type)").foregroundColor(.white.opacity(0.5)).cardStyle()
    }
}

// MARK: - Lesson Complete View

struct LessonCompleteView: View {
    let topic: String
    let onDismiss: () -> Void
    var body: some View {
        VStack(spacing: 24) {
            Text("🎉").font(.system(size: 72))
            Text("Lesson Complete!").font(.largeTitle.bold()).foregroundColor(.white)
            Text("You just learned \(topic)")
                .font(.subheadline).foregroundColor(.white.opacity(0.8))
            Button(action: onDismiss) {
                Text("Back to Learning")
                    .font(.headline).foregroundColor(.white)
                    .frame(maxWidth: .infinity).padding()
                    .background(Color.white.opacity(0.3)).cornerRadius(16)
            }
        }
        .cardStyle()
    }
}

// MARK: - Error Card View

struct ErrorCardView: View {
    let message: String
    let onRetry: () -> Void
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 48)).foregroundColor(.yellow)
            Text("Something went wrong").font(.headline).foregroundColor(.white)
            Text(message).font(.caption).foregroundColor(.white.opacity(0.7)).multilineTextAlignment(.center)
            Button(action: onRetry) {
                Text("Retry").font(.headline).foregroundColor(.white)
                    .frame(maxWidth: .infinity).padding()
                    .background(Color.white.opacity(0.3)).cornerRadius(16)
            }
        }
        .cardStyle()
    }
}

// MARK: - View Modifier

private struct CardStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(24)
            .background(Color.white.opacity(0.12))
            .cornerRadius(20)
            .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.white.opacity(0.2), lineWidth: 1))
    }
}

extension View {
    func cardStyle() -> some View { modifier(CardStyle()) }
}

// MARK: - Color hex helper

extension Color {
    init?(hex: String) {
        var str = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if str.hasPrefix("#") { str.removeFirst() }
        guard str.count == 6, let value = UInt64(str, radix: 16) else { return nil }
        let r = Double((value >> 16) & 0xFF) / 255
        let g = Double((value >>  8) & 0xFF) / 255
        let b = Double( value        & 0xFF) / 255
        self.init(red: r, green: g, blue: b)
    }
}