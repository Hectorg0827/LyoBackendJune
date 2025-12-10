// InteractiveCinemaView.swift
// Lyo
//
// Netflix-like Interactive Cinema Player View
// Copy this file to: Lyo/Views/AIClassroom/InteractiveCinemaView.swift

import SwiftUI
import AVKit

// MARK: - Main Player View

struct InteractiveCinemaView: View {
    let courseId: String
    
    @StateObject private var cinema = InteractiveCinemaService.shared
    @State private var showInteraction = false
    @State private var selectedAnswer: String?
    @State private var interactionStartTime = Date()
    @State private var showCelebration = false
    @State private var celebrationConfig: CelebrationConfig?
    
    var body: some View {
        ZStack {
            // Background
            Color.black.ignoresSafeArea()
            
            if cinema.isLoading {
                LoadingView()
            } else if let node = cinema.currentNode {
                VStack(spacing: 0) {
                    // Progress bar
                    ProgressBar(progress: cinema.progressPercent)
                    
                    // Main content area
                    ZStack {
                        // Visual content
                        NodeVisualView(node: node)
                        
                        // Interaction overlay
                        if node.nodeType == .interaction {
                            InteractionOverlayView(
                                node: node,
                                selectedAnswer: $selectedAnswer,
                                onSubmit: submitInteraction
                            )
                        }
                        
                        // Narration subtitle
                        if let script = node.scriptText, node.nodeType != .interaction {
                            NarrationSubtitleView(text: script)
                        }
                    }
                    
                    // Controls
                    PlayerControlsView(
                        isPlaying: cinema.isPlaying,
                        canAdvance: node.nodeType != .interaction,
                        onPlayPause: togglePlayback,
                        onAdvance: advanceToNext,
                        onBack: goBack
                    )
                }
                
                // Celebration overlay
                if showCelebration, let config = celebrationConfig {
                    CelebrationOverlayView(config: config) {
                        showCelebration = false
                    }
                }
            } else {
                // Start screen
                StartCourseView(onStart: startCourse)
            }
        }
        .onAppear {
            setupNotifications()
        }
        .onDisappear {
            cinema.stopPlayback()
        }
    }
    
    // MARK: - Actions
    
    private func startCourse() {
        Task {
            do {
                _ = try await cinema.startCourse(courseId: courseId)
                cinema.playCurrentNodeAudio()
            } catch {
                cinema.error = error
            }
        }
    }
    
    private func advanceToNext() {
        Task {
            do {
                _ = try await cinema.advance(courseId: courseId)
                cinema.playCurrentNodeAudio()
            } catch {
                cinema.error = error
            }
        }
    }
    
    private func goBack() {
        // Implement back navigation if needed
    }
    
    private func togglePlayback() {
        if cinema.isPlaying {
            cinema.pauseAudio()
        } else {
            cinema.playCurrentNodeAudio()
        }
    }
    
    private func submitInteraction() {
        guard let nodeId = cinema.currentNode?.id,
              let answerId = selectedAnswer else { return }
        
        let timeTaken = Date().timeIntervalSince(interactionStartTime)
        
        Task {
            do {
                let result = try await cinema.submitInteraction(
                    courseId: courseId,
                    nodeId: nodeId,
                    answerId: answerId,
                    timeTaken: timeTaken
                )
                
                // Show feedback
                if result.isCorrect {
                    // Play success animation
                } else {
                    // Show explanation, then navigate to remediation
                }
                
                selectedAnswer = nil
                interactionStartTime = Date()
                cinema.playCurrentNodeAudio()
            } catch {
                cinema.error = error
            }
        }
    }
    
    private func setupNotifications() {
        NotificationCenter.default.addObserver(
            forName: .showCelebration,
            object: nil,
            queue: .main
        ) { notification in
            if let userInfo = notification.userInfo,
               let type = userInfo["type"] as? String,
               let animation = userInfo["animation"] as? String,
               let sound = userInfo["sound"] as? String,
               let message = userInfo["message"] as? String,
               let duration = userInfo["duration"] as? Int {
                celebrationConfig = CelebrationConfig(
                    type: type,
                    animation: animation,
                    sound: sound,
                    message: message,
                    durationMs: duration
                )
                showCelebration = true
            }
        }
    }
}

// MARK: - Supporting Views

struct LoadingView: View {
    var body: some View {
        VStack(spacing: 20) {
            ProgressView()
                .scaleEffect(1.5)
                .tint(.white)
            
            Text("Loading your lesson...")
                .foregroundColor(.white.opacity(0.7))
        }
    }
}

struct ProgressBar: View {
    let progress: Double
    
    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Rectangle()
                    .fill(Color.white.opacity(0.3))
                    .frame(height: 3)
                
                Rectangle()
                    .fill(Color.purple)
                    .frame(width: geometry.size.width * CGFloat(progress / 100), height: 3)
            }
        }
        .frame(height: 3)
    }
}

struct NodeVisualView: View {
    let node: LearningNode
    
    var body: some View {
        GeometryReader { geometry in
            if let imageUrl = node.imageUrl, let url = URL(string: imageUrl) {
                AsyncImage(url: url) { image in
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: geometry.size.width, height: geometry.size.height)
                        .clipped()
                } placeholder: {
                    Rectangle()
                        .fill(Color.gray.opacity(0.3))
                }
            } else {
                // Fallback gradient background
                LinearGradient(
                    colors: [.purple.opacity(0.6), .blue.opacity(0.6)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            }
        }
    }
}

struct NarrationSubtitleView: View {
    let text: String
    
    var body: some View {
        VStack {
            Spacer()
            
            Text(text)
                .font(.body)
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.black.opacity(0.7))
                )
                .padding(.horizontal, 16)
                .padding(.bottom, 100)
        }
    }
}

struct InteractionOverlayView: View {
    let node: LearningNode
    @Binding var selectedAnswer: String?
    let onSubmit: () -> Void
    
    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            
            // Question
            if let question = node.interactionData?.question {
                Text(question)
                    .font(.title2)
                    .fontWeight(.semibold)
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
            }
            
            // Options
            if let options = node.interactionData?.options {
                VStack(spacing: 12) {
                    ForEach(options) { option in
                        OptionButton(
                            option: option,
                            isSelected: selectedAnswer == option.id,
                            onTap: { selectedAnswer = option.id }
                        )
                    }
                }
                .padding(.horizontal, 24)
            }
            
            // Submit button
            Button(action: onSubmit) {
                Text("Submit Answer")
                    .font(.headline)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(selectedAnswer != nil ? Color.purple : Color.gray)
                    )
            }
            .disabled(selectedAnswer == nil)
            .padding(.horizontal, 24)
            
            Spacer()
        }
        .background(Color.black.opacity(0.8))
    }
}

struct OptionButton: View {
    let option: InteractionOption
    let isSelected: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            HStack {
                Text(option.label)
                    .foregroundColor(.white)
                
                Spacer()
                
                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.purple)
                }
            }
            .padding()
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(isSelected ? Color.purple : Color.white.opacity(0.3), lineWidth: 2)
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(isSelected ? Color.purple.opacity(0.2) : Color.clear)
                    )
            )
        }
    }
}

struct PlayerControlsView: View {
    let isPlaying: Bool
    let canAdvance: Bool
    let onPlayPause: () -> Void
    let onAdvance: () -> Void
    let onBack: () -> Void
    
    var body: some View {
        HStack(spacing: 40) {
            // Back button
            Button(action: onBack) {
                Image(systemName: "backward.fill")
                    .font(.title2)
                    .foregroundColor(.white.opacity(0.7))
            }
            
            // Play/Pause
            Button(action: onPlayPause) {
                Image(systemName: isPlaying ? "pause.circle.fill" : "play.circle.fill")
                    .font(.system(size: 60))
                    .foregroundColor(.white)
            }
            
            // Forward/Next
            Button(action: onAdvance) {
                Image(systemName: "forward.fill")
                    .font(.title2)
                    .foregroundColor(canAdvance ? .white : .white.opacity(0.3))
            }
            .disabled(!canAdvance)
        }
        .padding(.vertical, 20)
        .background(
            LinearGradient(
                colors: [.clear, .black.opacity(0.8)],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }
}

struct StartCourseView: View {
    let onStart: () -> Void
    
    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "play.circle.fill")
                .font(.system(size: 80))
                .foregroundColor(.purple)
            
            Text("Ready to Learn?")
                .font(.title)
                .fontWeight(.bold)
                .foregroundColor(.white)
            
            Text("Tap to begin your interactive lesson")
                .foregroundColor(.white.opacity(0.7))
            
            Button(action: onStart) {
                Text("Start Lesson")
                    .font(.headline)
                    .foregroundColor(.white)
                    .padding(.horizontal, 40)
                    .padding(.vertical, 16)
                    .background(
                        RoundedRectangle(cornerRadius: 25)
                            .fill(Color.purple)
                    )
            }
            .padding(.top, 20)
        }
    }
}

struct CelebrationOverlayView: View {
    let config: CelebrationConfig
    let onDismiss: () -> Void
    
    @State private var scale: CGFloat = 0.5
    @State private var opacity: Double = 0
    
    var body: some View {
        ZStack {
            Color.black.opacity(0.5)
                .ignoresSafeArea()
            
            VStack(spacing: 20) {
                // Animation placeholder - implement based on config.animation
                celebrationIcon
                    .font(.system(size: 80))
                    .scaleEffect(scale)
                
                Text(config.message)
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)
            }
            .opacity(opacity)
        }
        .onAppear {
            withAnimation(.spring(response: 0.5, dampingFraction: 0.6)) {
                scale = 1.0
                opacity = 1.0
            }
            
            // Auto-dismiss after duration
            DispatchQueue.main.asyncAfter(deadline: .now() + Double(config.durationMs) / 1000) {
                withAnimation {
                    opacity = 0
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    onDismiss()
                }
            }
        }
    }
    
    @ViewBuilder
    private var celebrationIcon: some View {
        switch config.type {
        case "first_correct":
            Text("🎉")
        case "concept_mastered":
            Text("🌟")
        case "streak_milestone":
            Text("🔥")
        case "perfect_score":
            Text("⭐")
        case "course_complete":
            Text("🎓")
        case "struggle_overcome":
            Text("💪")
        case "speed_bonus":
            Text("⚡")
        default:
            Text("🎉")
        }
    }
}

// MARK: - Review View

struct DailyReviewView: View {
    @StateObject private var cinema = InteractiveCinemaService.shared
    @State private var currentReviewIndex = 0
    @State private var selectedAnswer: String?
    @State private var reviewStartTime = Date()
    @State private var showResult = false
    @State private var lastResult: ReviewSubmitResponse?
    
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            
            if cinema.reviewQueue.isEmpty {
                EmptyReviewView(streakDays: cinema.streakDays)
            } else if currentReviewIndex < cinema.reviewQueue.count {
                let item = cinema.reviewQueue[currentReviewIndex]
                
                VStack(spacing: 24) {
                    // Header
                    ReviewHeaderView(
                        current: currentReviewIndex + 1,
                        total: cinema.reviewQueue.count,
                        streakDays: cinema.streakDays
                    )
                    
                    // Review content
                    ReviewCardView(
                        item: item,
                        selectedAnswer: $selectedAnswer,
                        onSubmit: submitReview
                    )
                }
            } else {
                ReviewCompleteView(streakDays: cinema.streakDays)
            }
        }
        .onAppear {
            loadReviews()
        }
    }
    
    private func loadReviews() {
        Task {
            _ = try? await cinema.getTodaysReviews()
        }
    }
    
    private func submitReview() {
        guard currentReviewIndex < cinema.reviewQueue.count,
              let answerId = selectedAnswer else { return }
        
        let item = cinema.reviewQueue[currentReviewIndex]
        let timeTaken = Date().timeIntervalSince(reviewStartTime)
        
        Task {
            do {
                let result = try await cinema.submitReview(
                    scheduleId: item.id,
                    answerId: answerId,
                    timeTaken: timeTaken
                )
                
                lastResult = result
                showResult = true
                
                // Move to next after delay
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                    showResult = false
                    currentReviewIndex += 1
                    selectedAnswer = nil
                    reviewStartTime = Date()
                }
            } catch {
                cinema.error = error
            }
        }
    }
}

struct ReviewHeaderView: View {
    let current: Int
    let total: Int
    let streakDays: Int
    
    var body: some View {
        HStack {
            Text("\(current) / \(total)")
                .foregroundColor(.white.opacity(0.7))
            
            Spacer()
            
            HStack(spacing: 4) {
                Image(systemName: "flame.fill")
                    .foregroundColor(.orange)
                Text("\(streakDays)")
                    .foregroundColor(.white)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 10)
    }
}

struct ReviewCardView: View {
    let item: ReviewItem
    @Binding var selectedAnswer: String?
    let onSubmit: () -> Void
    
    var body: some View {
        VStack(spacing: 20) {
            // Concept name
            Text(item.conceptName)
                .font(.caption)
                .foregroundColor(.purple)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Capsule().fill(Color.purple.opacity(0.2)))
            
            // Question from node
            if let question = item.node.interactionData?.question {
                Text(question)
                    .font(.title3)
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            
            // Options
            if let options = item.node.interactionData?.options {
                VStack(spacing: 12) {
                    ForEach(options) { option in
                        OptionButton(
                            option: option,
                            isSelected: selectedAnswer == option.id,
                            onTap: { selectedAnswer = option.id }
                        )
                    }
                }
                .padding(.horizontal)
            }
            
            // Submit
            Button(action: onSubmit) {
                Text("Check Answer")
                    .font(.headline)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(selectedAnswer != nil ? Color.purple : Color.gray)
                    )
            }
            .disabled(selectedAnswer == nil)
            .padding(.horizontal)
        }
        .padding(.vertical, 30)
        .background(
            RoundedRectangle(cornerRadius: 20)
                .fill(Color.white.opacity(0.1))
        )
        .padding(.horizontal, 16)
    }
}

struct EmptyReviewView: View {
    let streakDays: Int
    
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 60))
                .foregroundColor(.green)
            
            Text("All caught up!")
                .font(.title2)
                .foregroundColor(.white)
            
            Text("No reviews due today")
                .foregroundColor(.white.opacity(0.7))
            
            if streakDays > 0 {
                HStack {
                    Image(systemName: "flame.fill")
                        .foregroundColor(.orange)
                    Text("\(streakDays) day streak!")
                        .foregroundColor(.orange)
                }
                .padding(.top, 10)
            }
        }
    }
}

struct ReviewCompleteView: View {
    let streakDays: Int
    
    var body: some View {
        VStack(spacing: 20) {
            Text("🎉")
                .font(.system(size: 80))
            
            Text("Review Complete!")
                .font(.title)
                .fontWeight(.bold)
                .foregroundColor(.white)
            
            if streakDays > 0 {
                HStack {
                    Image(systemName: "flame.fill")
                        .foregroundColor(.orange)
                    Text("\(streakDays) day streak!")
                        .foregroundColor(.orange)
                        .fontWeight(.semibold)
                }
            }
            
            Text("Great job keeping your knowledge fresh!")
                .foregroundColor(.white.opacity(0.7))
        }
    }
}

// MARK: - Preview

struct InteractiveCinemaView_Previews: PreviewProvider {
    static var previews: some View {
        InteractiveCinemaView(courseId: "preview-course")
    }
}
