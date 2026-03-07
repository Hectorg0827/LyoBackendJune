// CourseFlowView.swift
// Lyo
//
// Root coordinator for the full AI course generation + display flow.
// Copy this file to: Lyo/Views/AIClassroom/CourseFlowView.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import SwiftUI
import Combine

// MARK: - Navigation Destination Enum

enum CourseDestination: Hashable {
    case outline(CourseResult)
    case lessonReader(CourseLesson, moduleTitle: String)
    case moduleQuiz(CourseQuiz, moduleTitle: String)

    // Hashable conformance
    func hash(into hasher: inout Hasher) {
        switch self {
        case .outline(let course):
            hasher.combine("outline")
            hasher.combine(course.courseId)
        case .lessonReader(let lesson, let moduleTitle):
            hasher.combine("lessonReader")
            hasher.combine(lesson.lessonId)
            hasher.combine(moduleTitle)
        case .moduleQuiz(let quiz, let moduleTitle):
            hasher.combine("moduleQuiz")
            hasher.combine(quiz.quizId)
            hasher.combine(moduleTitle)
        }
    }

    static func == (lhs: CourseDestination, rhs: CourseDestination) -> Bool {
        switch (lhs, rhs) {
        case (.outline(let a), .outline(let b)):
            return a.courseId == b.courseId
        case (.lessonReader(let a, let mt1), .lessonReader(let b, let mt2)):
            return a.lessonId == b.lessonId && mt1 == mt2
        case (.moduleQuiz(let a, let mt1), .moduleQuiz(let b, let mt2)):
            return a.quizId == b.quizId && mt1 == mt2
        default:
            return false
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
        case .beginner:
            return "No prior knowledge needed. Concepts explained from scratch."
        case .intermediate:
            return "Some familiarity assumed. Builds on foundational knowledge."
        case .advanced:
            return "Deep dive for experienced learners. Fast-paced and thorough."
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
    @StateObject private var generationVM = CourseGenerationViewModel()
    @State private var navigationPath = NavigationPath()
    @State private var topic: String = ""
    @State private var selectedDifficulty: CourseDifficulty = .intermediate

    var body: some View {
        NavigationStack(path: $navigationPath) {
            CourseInputView(
                topic: $topic,
                selectedDifficulty: $selectedDifficulty,
                generationVM: generationVM,
                onGenerate: handleGenerate
            )
            .navigationDestination(for: CourseDestination.self) { destination in
                switch destination {
                case .outline(let course):
                    CourseOutlineView(course: course, navigationPath: $navigationPath)
                case .lessonReader(let lesson, let moduleTitle):
                    LessonReaderView(lesson: lesson, moduleTitle: moduleTitle)
                case .moduleQuiz(let quiz, let moduleTitle):
                    ModuleQuizView(quiz: quiz, moduleTitle: moduleTitle)
                }
            }
        }
        .onChange(of: generationVM.courseResult) { result in
            guard let result = result else { return }
            // Auto-navigate to outline when generation completes
            navigationPath.append(CourseDestination.outline(result))
        }
    }

    private func handleGenerate() {
        let trimmed = topic.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        generationVM.generateCourse(topic: trimmed, difficulty: selectedDifficulty.rawValue)
    }
}

// MARK: - Preview

struct CourseFlowView_Previews: PreviewProvider {
    static var previews: some View {
        CourseFlowView()
    }
}
