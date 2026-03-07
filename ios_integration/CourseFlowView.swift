// CourseFlowView.swift
// Lyo
//
// Root coordinator for the full AI course generation + display flow.
// Uses ProgressiveCourseViewModel for outline-first loading:
//   1. POST /outline  → scaffold arrives in ~2s, UI shows immediately
//   2. Tap module → SSE streams lessons progressively into the UI
//
// Copy this file to: Lyo/Views/AIClassroom/CourseFlowView.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import SwiftUI
import Combine

// MARK: - Navigation Destination Enum

enum CourseDestination: Hashable {
    case progressiveOutline             // pushed immediately when scaffold arrives
    case lessonReader(BackendLesson, moduleTitle: String)
    case legacyOutline(CourseResult)    // kept for compatibility with CourseOutlineView

    func hash(into hasher: inout Hasher) {
        switch self {
        case .progressiveOutline:
            hasher.combine("progressiveOutline")
        case .lessonReader(let lesson, let moduleTitle):
            hasher.combine("lessonReader")
            hasher.combine(lesson.id)
            hasher.combine(moduleTitle)
        case .legacyOutline(let course):
            hasher.combine("legacyOutline")
            hasher.combine(course.courseId)
        }
    }

    static func == (lhs: CourseDestination, rhs: CourseDestination) -> Bool {
        switch (lhs, rhs) {
        case (.progressiveOutline, .progressiveOutline): return true
        case (.lessonReader(let a, let mt1), .lessonReader(let b, let mt2)):
            return a.id == b.id && mt1 == mt2
        case (.legacyOutline(let a), .legacyOutline(let b)):
            return a.courseId == b.courseId
        default: return false
        }
    }
}

// MARK: - Difficulty Enum

enum CourseDifficulty: String, CaseIterable, Identifiable {
    case beginner = "beginner"
    case intermediate = "intermediate"
    case advanced = "advanced"

    var id: String { rawValue }
    var displayName: String { rawValue.capitalized }

    var icon: String {
        switch self {
        case .beginner: return "1.circle.fill"
        case .intermediate: return "2.circle.fill"
        case .advanced: return "3.circle.fill"
        }
    }

    var description: String {
        switch self {
        case .beginner:  return "No prior knowledge needed. Concepts explained from scratch."
        case .intermediate: return "Some familiarity assumed. Builds on foundational knowledge."
        case .advanced:  return "Deep dive for experienced learners. Fast-paced and thorough."
        }
    }

    var color: Color {
        switch self {
        case .beginner: return .green
        case .intermediate: return .orange
        case .advanced: return .red
        }
    }
}

// MARK: - Course Flow View

struct CourseFlowView: View {
    @StateObject private var progressiveVM = ProgressiveCourseViewModel()
    @State private var navigationPath = NavigationPath()
    @State private var topic: String = ""
    @State private var selectedDifficulty: CourseDifficulty = .intermediate

    var body: some View {
        NavigationStack(path: $navigationPath) {
            CourseInputProgressiveView(
                topic: $topic,
                selectedDifficulty: $selectedDifficulty,
                progressiveVM: progressiveVM,
                onGenerate: handleGenerate
            )
            .navigationDestination(for: CourseDestination.self) { destination in
                switch destination {
                case .progressiveOutline:
                    ProgressiveCourseOutlineView(
                        progressiveVM: progressiveVM,
                        navigationPath: $navigationPath
                    )
                case .lessonReader(let lesson, let moduleTitle):
                    BackendLessonReaderView(lesson: lesson, moduleTitle: moduleTitle)
                case .legacyOutline(let course):
                    CourseOutlineView(course: course, navigationPath: $navigationPath)
                }
            }
        }
        // Navigate to outline as soon as scaffold is ready — no more blank waiting screen
        .onChange(of: progressiveVM.stage) { stage in
            switch stage {
            case .scaffoldReady:
                if !navigationPath.isEmpty { return } // already navigated
                navigationPath.append(CourseDestination.progressiveOutline)
            default:
                break
            }
        }
    }

    private func handleGenerate() {
        let trimmed = topic.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        navigationPath = NavigationPath() // reset nav on new generation
        progressiveVM.startCourse(topic: trimmed, difficulty: selectedDifficulty.rawValue)
    }
}

// MARK: - Lightweight Input Wrapper for Progressive VM

struct CourseInputProgressiveView: View {
    @Binding var topic: String
    @Binding var selectedDifficulty: CourseDifficulty
    @ObservedObject var progressiveVM: ProgressiveCourseViewModel
    let onGenerate: () -> Void

    // Wrap into the isLoading / errorMessage / progress shape CourseInputView expects
    @StateObject private var bridgeVM = BridgeCourseVM()

    var body: some View {
        CourseInputView(
            topic: $topic,
            selectedDifficulty: $selectedDifficulty,
            generationVM: bridgeVM.vm,
            onGenerate: {
                bridgeVM.vm.isLoading = true
                bridgeVM.vm.errorMessage = nil
                bridgeVM.vm.progress = 0.0
                onGenerate()
            }
        )
        .onChange(of: progressiveVM.stage) { stage in
            switch stage {
            case .scaffolding:
                bridgeVM.vm.isLoading = true
                bridgeVM.vm.progress = 0.1
            case .scaffoldReady:
                bridgeVM.vm.isLoading = false
                bridgeVM.vm.progress = 1.0
            case .failed(let msg):
                bridgeVM.vm.isLoading = false
                bridgeVM.vm.errorMessage = msg
            default:
                break
            }
        }
    }
}

// Thin ObservableObject bridge so CourseInputView (which expects CourseGenerationViewModel)
// can be reused without modification.
@MainActor
private class BridgeCourseVM: ObservableObject {
    let vm = CourseGenerationViewModel()
}

// MARK: - Progressive Course Outline View

struct ProgressiveCourseOutlineView: View {
    @ObservedObject var progressiveVM: ProgressiveCourseViewModel
    @Binding var navigationPath: NavigationPath

    var body: some View {
        Group {
            if let course = progressiveVM.course {
                ScrollView {
                    LazyVStack(spacing: 12) {
                        courseHeaderCard(course)
                            .padding(.horizontal, 16)
                            .padding(.top, 16)

                        ForEach(course.modules) { module in
                            progressiveModuleRow(module, course: course)
                                .padding(.horizontal, 16)
                        }

                        Spacer(minLength: 32)
                    }
                }
                .background(Color(.systemGroupedBackground).ignoresSafeArea())
                .navigationTitle(course.title)
                .navigationBarTitleDisplayMode(.large)
            } else {
                ProgressView("Building course…")
                    .navigationTitle("Loading")
            }
        }
    }

    // MARK: - Header

    private func courseHeaderCard(_ course: ProgressiveCourse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(course.description)
                .font(.subheadline)
                .foregroundColor(.secondary)

            HStack(spacing: 16) {
                difficultyBadge(course.difficulty)
                Label("\(course.estimatedDuration) min", systemImage: "clock.fill")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Label("\(course.modules.count) modules", systemImage: "square.stack.fill")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color(.secondarySystemGroupedBackground))
                .shadow(color: .black.opacity(0.04), radius: 4, x: 0, y: 2)
        )
    }

    // MARK: - Module Row

    @ViewBuilder
    private func progressiveModuleRow(_ module: ProgressiveModule, course: ProgressiveCourse) -> some View {
        let index = course.modules.firstIndex(where: { $0.id == module.id }) ?? 0

        VStack(alignment: .leading, spacing: 0) {
            // Module header
            HStack(spacing: 12) {
                moduleIndexCircle(index + 1)

                VStack(alignment: .leading, spacing: 3) {
                    Text(module.title)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Text(module.description)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }

                Spacer()

                moduleStateIndicator(module)
            }
            .padding(14)

            // Lesson rows (shown when ready) or skeleton
            switch module.state {
            case .skeleton:
                skeletonLessons()
                    .padding(.horizontal, 14)
                    .padding(.bottom, 14)

            case .streaming:
                streamingIndicator()
                    .padding(.horizontal, 14)
                    .padding(.bottom, 14)

            case .ready(let lessons):
                VStack(spacing: 0) {
                    Divider().padding(.horizontal, 14)
                    ForEach(lessons) { lesson in
                        lessonRow(lesson, moduleTitle: module.title)
                        if lesson.id != lessons.last?.id {
                            Divider().padding(.leading, 52)
                        }
                    }
                }

            case .failed:
                retryButton(moduleId: module.id)
                    .padding(14)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color(.secondarySystemGroupedBackground))
                .shadow(color: .black.opacity(0.04), radius: 4, x: 0, y: 2)
        )
        // Auto-stream when module becomes visible (lazy load)
        .onAppear {
            if case .skeleton = module.state {
                progressiveVM.streamModule(moduleId: module.id)
            }
        }
    }

    // MARK: - Lesson Row

    private func lessonRow(_ lesson: BackendLesson, moduleTitle: String) -> some View {
        Button(action: {
            navigationPath.append(CourseDestination.lessonReader(lesson, moduleTitle: moduleTitle))
        }) {
            HStack(spacing: 12) {
                Image(systemName: "doc.text")
                    .foregroundColor(.blue)
                    .frame(width: 20)

                VStack(alignment: .leading, spacing: 2) {
                    Text(lesson.title)
                        .font(.subheadline)
                        .foregroundColor(.primary)
                    Text("\(lesson.durationMinutes) min")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundColor(.secondary.opacity(0.5))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - State Indicators

    private func moduleIndexCircle(_ index: Int) -> some View {
        ZStack {
            Circle()
                .fill(LinearGradient(colors: [.purple.opacity(0.7), .blue.opacity(0.7)],
                                     startPoint: .topLeading, endPoint: .bottomTrailing))
                .frame(width: 32, height: 32)
            Text("\(index)")
                .font(.caption).fontWeight(.bold).foregroundColor(.white)
        }
    }

    @ViewBuilder
    private func moduleStateIndicator(_ module: ProgressiveModule) -> some View {
        switch module.state {
        case .skeleton:
            Image(systemName: "arrow.down.circle")
                .foregroundColor(.secondary.opacity(0.4))
                .font(.subheadline)
        case .streaming:
            ProgressView()
                .scaleEffect(0.7)
        case .ready(let lessons):
            Text("\(lessons.count) lessons")
                .font(.caption2)
                .foregroundColor(.secondary)
        case .failed:
            Image(systemName: "exclamationmark.circle")
                .foregroundColor(.red)
                .font(.subheadline)
        }
    }

    private func skeletonLessons() -> some View {
        VStack(spacing: 8) {
            ForEach(0..<3, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.systemGray5))
                    .frame(height: 14)
                    .opacity(0.6)
            }
        }
    }

    private func streamingIndicator() -> some View {
        HStack(spacing: 8) {
            ProgressView()
                .scaleEffect(0.8)
            Text("Generating lessons…")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 8)
    }

    private func retryButton(moduleId: String) -> some View {
        Button(action: { progressiveVM.streamModule(moduleId: moduleId) }) {
            Label("Retry", systemImage: "arrow.clockwise")
                .font(.caption)
                .foregroundColor(.purple)
        }
    }

    private func difficultyBadge(_ difficulty: String) -> some View {
        let color: Color = {
            switch difficulty.lowercased() {
            case "beginner": return .green
            case "advanced": return .red
            default: return .orange
            }
        }()
        return Text(difficulty.capitalized)
            .font(.caption2)
            .fontWeight(.semibold)
            .foregroundColor(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Capsule().fill(color.opacity(0.12)))
    }
}

// MARK: - Backend Lesson Reader View
// Thin wrapper around LessonReaderView for BackendLesson type

struct BackendLessonReaderView: View {
    let lesson: BackendLesson
    let moduleTitle: String

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text(moduleTitle)
                        .font(.caption)
                        .foregroundColor(.purple)
                        .fontWeight(.medium)

                    Text(lesson.title)
                        .font(.title2)
                        .fontWeight(.bold)

                    Label("\(lesson.durationMinutes) min", systemImage: "clock")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 20)
                .padding(.top, 16)

                Divider().padding(.horizontal, 20)

                // Content — use the Markdown renderer from LessonAndQuizViews.swift
                if let content = lesson.content, !content.isEmpty {
                    // Reuse the same body text approach from LessonReaderView
                    let attributed = (try? AttributedString(
                        markdown: content,
                        options: AttributedString.MarkdownParsingOptions(
                            allowsExtendedAttributes: true,
                            interpretedSyntax: .inlineOnlyPreservingWhitespace
                        )
                    )) ?? AttributedString(content)

                    Text(attributed)
                        .font(.body)
                        .lineSpacing(4)
                        .padding(.horizontal, 20)
                } else {
                    Text("Content is being generated…")
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 20)
                }

                Spacer(minLength: 80)
            }
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationTitle(lesson.title)
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            Button(action: { dismiss() }) {
                Text("Mark as Complete")
                    .fontWeight(.semibold)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(
                        RoundedRectangle(cornerRadius: 14)
                            .fill(LinearGradient(colors: [.purple, .blue], startPoint: .leading, endPoint: .trailing))
                    )
                    .padding(.horizontal, 20)
                    .padding(.vertical, 12)
            }
            .background(Color(.systemGroupedBackground))
        }
    }
}

// MARK: - Preview

struct CourseFlowView_Previews: PreviewProvider {
    static var previews: some View {
        CourseFlowView()
    }
}
