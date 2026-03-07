// LessonAndQuizViews.swift
// Lyo
//
// Lesson reader with Markdown rendering and per-module quiz with scoring.
// Copy this file to: Lyo/Views/AIClassroom/LessonAndQuizViews.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import SwiftUI

// MARK: - Markdown Section Model

struct MarkdownSection: Identifiable {
    let id = UUID()
    enum Kind {
        case heading(level: Int, text: String)
        case codeBlock(language: String?, code: String)
        case body(String)
    }
    let kind: Kind
}

// MARK: - Markdown Parser

private func parseMarkdown(_ raw: String) -> [MarkdownSection] {
    var sections: [MarkdownSection] = []
    let lines = raw.components(separatedBy: "\n")
    var i = 0
    var bodyBuffer: [String] = []

    func flushBody() {
        let text = bodyBuffer.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty {
            sections.append(MarkdownSection(kind: .body(text)))
        }
        bodyBuffer.removeAll()
    }

    while i < lines.count {
        let line = lines[i]

        // Fenced code block
        if line.trimmingCharacters(in: .whitespaces).hasPrefix("```") {
            flushBody()
            let fence = line.trimmingCharacters(in: .whitespaces)
            let language = fence.count > 3 ? String(fence.dropFirst(3)).trimmingCharacters(in: .whitespaces) : nil
            var codeLines: [String] = []
            i += 1
            while i < lines.count && !lines[i].trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                codeLines.append(lines[i])
                i += 1
            }
            sections.append(MarkdownSection(kind: .codeBlock(language: language?.isEmpty == true ? nil : language, code: codeLines.joined(separator: "\n"))))
            i += 1
            continue
        }

        // ATX headings
        if line.hasPrefix("### ") {
            flushBody()
            sections.append(MarkdownSection(kind: .heading(level: 3, text: String(line.dropFirst(4)))))
            i += 1
            continue
        }
        if line.hasPrefix("## ") {
            flushBody()
            sections.append(MarkdownSection(kind: .heading(level: 2, text: String(line.dropFirst(3)))))
            i += 1
            continue
        }
        if line.hasPrefix("# ") {
            flushBody()
            sections.append(MarkdownSection(kind: .heading(level: 1, text: String(line.dropFirst(2)))))
            i += 1
            continue
        }

        bodyBuffer.append(line)
        i += 1
    }

    flushBody()
    return sections
}

// MARK: - Lesson Reader View

struct LessonReaderView: View {
    let lesson: CourseLesson
    let moduleTitle: String

    @State private var sections: [MarkdownSection] = []
    @State private var isComplete = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack(alignment: .bottom) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    // Lesson meta header
                    lessonHeader
                        .padding(.horizontal, 20)
                        .padding(.top, 16)

                    Divider()
                        .padding(.horizontal, 20)

                    // Content sections
                    if sections.isEmpty {
                        ProgressView("Loading content…")
                            .frame(maxWidth: .infinity)
                            .padding(.top, 40)
                    } else {
                        ForEach(sections) { section in
                            sectionView(section)
                                .padding(.horizontal, 20)
                        }
                    }

                    // Resources
                    if let resources = lesson.resources, !resources.isEmpty {
                        resourcesSection(resources)
                            .padding(.horizontal, 20)
                    }

                    // Bottom padding for the sticky footer
                    Spacer(minLength: 100)
                }
            }

            // Sticky "Mark Complete" footer
            completionFooter
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationTitle(lesson.title)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            sections = parseMarkdown(lesson.content)
        }
    }

    // MARK: - Subviews

    private var lessonHeader: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Module breadcrumb
            Text(moduleTitle)
                .font(.caption)
                .foregroundColor(.purple)
                .fontWeight(.medium)

            // Lesson title
            Text(lesson.title)
                .font(.title2)
                .fontWeight(.bold)
                .fixedSize(horizontal: false, vertical: true)

            // Meta row
            HStack(spacing: 12) {
                Label(lessonTypeLabel(lesson.type), systemImage: lessonTypeIcon(lesson.type))
                    .font(.caption)
                    .foregroundColor(lessonTypeColor(lesson.type))

                Text("·")
                    .foregroundColor(.secondary)
                    .font(.caption)

                Label("\(lesson.estimatedMinutes) min", systemImage: "clock")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }

    @ViewBuilder
    private func sectionView(_ section: MarkdownSection) -> some View {
        switch section.kind {
        case .heading(let level, let text):
            headingView(level: level, text: text)

        case .codeBlock(let language, let code):
            codeBlockView(language: language, code: code)

        case .body(let text):
            bodyTextView(text: text)
        }
    }

    private func headingView(level: Int, text: String) -> some View {
        let font: Font = {
            switch level {
            case 1: return .title2.bold()
            case 2: return .title3.bold()
            default: return .headline
            }
        }()
        return Text(text)
            .font(font)
            .foregroundColor(.primary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func codeBlockView(language: String?, code: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if let lang = language {
                HStack {
                    Text(lang)
                        .font(.caption2)
                        .fontWeight(.semibold)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                    Spacer()
                }
                .background(Color(.systemGray5))
            }

            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.system(.footnote, design: .monospaced))
                    .foregroundColor(.primary)
                    .padding(14)
            }
            .background(Color(.systemGray6))
        }
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color(.systemGray4), lineWidth: 1)
        )
    }

    private func bodyTextView(text: String) -> some View {
        // Use AttributedString for inline markdown (bold, italic, inline code, links)
        let attributed: Text = {
            if let attrString = try? AttributedString(
                markdown: text,
                options: AttributedString.MarkdownParsingOptions(
                    allowsExtendedAttributes: true,
                    interpretedSyntax: .inlineOnlyPreservingWhitespace
                )
            ) {
                return Text(attrString)
            } else {
                return Text(text)
            }
        }()

        return attributed
            .font(.body)
            .foregroundColor(.primary)
            .fixedSize(horizontal: false, vertical: true)
            .lineSpacing(4)
    }

    private func resourcesSection(_ resources: [LessonResource]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Further Reading")
                .font(.headline)
                .padding(.top, 8)

            ForEach(resources, id: \.url) { resource in
                HStack(spacing: 10) {
                    Image(systemName: resourceIcon(resource.type))
                        .foregroundColor(.purple)
                        .frame(width: 20)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(resource.title)
                            .font(.subheadline)
                            .foregroundColor(.primary)
                        if let desc = resource.description {
                            Text(desc)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding(12)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color(.secondarySystemGroupedBackground))
                )
            }
        }
    }

    private var completionFooter: some View {
        VStack(spacing: 0) {
            Divider()
            Button(action: {
                isComplete = true
                dismiss()
            }) {
                HStack(spacing: 8) {
                    Image(systemName: isComplete ? "checkmark.circle.fill" : "checkmark.circle")
                    Text(isComplete ? "Completed" : "Mark as Complete")
                        .fontWeight(.semibold)
                }
                .font(.body)
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(
                    RoundedRectangle(cornerRadius: 14)
                        .fill(
                            LinearGradient(colors: [.purple, .blue], startPoint: .leading, endPoint: .trailing)
                        )
                )
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
            }
            .background(Color(.systemGroupedBackground))
        }
    }

    // MARK: - Helpers

    private func lessonTypeIcon(_ type: LessonType) -> String {
        switch type {
        case .text: return "doc.text"
        case .video: return "play.circle"
        case .interactive: return "hand.tap"
        case .exercise: return "pencil.circle"
        case .reading: return "book"
        }
    }

    private func lessonTypeLabel(_ type: LessonType) -> String {
        switch type {
        case .text: return "Text"
        case .video: return "Video"
        case .interactive: return "Interactive"
        case .exercise: return "Exercise"
        case .reading: return "Reading"
        }
    }

    private func lessonTypeColor(_ type: LessonType) -> Color {
        switch type {
        case .text: return .blue
        case .video: return .red
        case .interactive: return .orange
        case .exercise: return .green
        case .reading: return .indigo
        }
    }

    private func resourceIcon(_ type: String) -> String {
        switch type.lowercased() {
        case "video": return "play.circle"
        case "article", "blog": return "doc.text"
        case "documentation", "docs": return "book.closed"
        case "github", "code": return "chevron.left.forwardslash.chevron.right"
        default: return "link"
        }
    }
}

// MARK: - Quiz View Model

@MainActor
class QuizViewModel: ObservableObject {
    let quiz: CourseQuiz

    @Published var currentIndex: Int = 0
    @Published var selectedOption: String? = nil
    @Published var score: Int = 0
    @Published var showExplanation: Bool = false
    @Published var isCorrect: Bool = false
    @Published var isComplete: Bool = false

    var currentQuestion: QuizQuestion? {
        guard currentIndex < quiz.questions.count else { return nil }
        return quiz.questions[currentIndex]
    }

    var progress: Double {
        guard !quiz.questions.isEmpty else { return 0 }
        return Double(currentIndex) / Double(quiz.questions.count)
    }

    var passed: Bool {
        let pct = Double(score) / Double(quiz.questions.count)
        let required = Double(quiz.passingScore ?? 70) / 100.0
        return pct >= required
    }

    init(quiz: CourseQuiz) {
        self.quiz = quiz
    }

    func submitAnswer() {
        guard let question = currentQuestion, let selected = selectedOption else { return }
        isCorrect = selected == question.correctAnswer.value ||
                    (question.options?.firstIndex(of: selected).map { String($0) } == question.correctAnswer.value.description)
        if isCorrect { score += 1 }
        showExplanation = true
    }

    func nextQuestion() {
        showExplanation = false
        selectedOption = nil
        if currentIndex + 1 < quiz.questions.count {
            currentIndex += 1
        } else {
            isComplete = true
        }
    }
}

// MARK: - Module Quiz View

struct ModuleQuizView: View {
    let quiz: CourseQuiz
    let moduleTitle: String

    @StateObject private var quizVM: QuizViewModel
    @State private var showCelebration = false
    @Environment(\.dismiss) private var dismiss

    init(quiz: CourseQuiz, moduleTitle: String) {
        self.quiz = quiz
        self.moduleTitle = moduleTitle
        _quizVM = StateObject(wrappedValue: QuizViewModel(quiz: quiz))
    }

    var body: some View {
        ZStack {
            Color(.systemGroupedBackground).ignoresSafeArea()

            if quizVM.isComplete {
                quizResultView
            } else if let question = quizVM.currentQuestion {
                questionView(question)
            }

            // Celebration overlay (replicates CelebrationOverlayView from InteractiveCinemaView)
            if showCelebration {
                celebrationOverlay
            }
        }
        .navigationTitle(quiz.title)
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: quizVM.isComplete) { complete in
            if complete && quizVM.passed {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    showCelebration = true
                }
            }
        }
    }

    // MARK: - Question View

    private func questionView(_ question: QuizQuestion) -> some View {
        VStack(spacing: 0) {
            // Progress header
            VStack(spacing: 12) {
                HStack {
                    Text("\(quizVM.currentIndex + 1) of \(quiz.questions.count)")
                        .font(.subheadline)
                        .foregroundColor(.secondary)

                    Spacer()

                    Text("Score: \(quizVM.score)")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.purple)
                }
                .padding(.horizontal, 20)

                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(Color.purple.opacity(0.15))
                            .frame(height: 4)
                        RoundedRectangle(cornerRadius: 2)
                            .fill(LinearGradient(colors: [.purple, .blue], startPoint: .leading, endPoint: .trailing))
                            .frame(width: geo.size.width * quizVM.progress, height: 4)
                            .animation(.easeInOut(duration: 0.3), value: quizVM.progress)
                    }
                }
                .frame(height: 4)
                .padding(.horizontal, 20)
            }
            .padding(.top, 20)
            .padding(.bottom, 16)
            .background(Color(.secondarySystemGroupedBackground))

            ScrollView {
                VStack(spacing: 24) {
                    // Question text
                    Text(question.question)
                        .font(.title3)
                        .fontWeight(.semibold)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 20)
                        .padding(.top, 24)

                    // Options
                    if let options = question.options {
                        VStack(spacing: 12) {
                            ForEach(Array(options.enumerated()), id: \.offset) { index, option in
                                quizOptionButton(
                                    label: option,
                                    optionValue: option,
                                    question: question,
                                    index: index
                                )
                            }
                        }
                        .padding(.horizontal, 20)
                    }

                    // Explanation (shown after submit)
                    if quizVM.showExplanation, let explanation = question.explanation {
                        explanationCard(explanation: explanation, isCorrect: quizVM.isCorrect)
                            .padding(.horizontal, 20)
                    }

                    Spacer(minLength: 100)
                }
            }

            // Bottom action bar
            VStack(spacing: 0) {
                Divider()
                Group {
                    if quizVM.showExplanation {
                        Button(action: { quizVM.nextQuestion() }) {
                            Text(quizVM.currentIndex + 1 < quiz.questions.count ? "Next Question" : "See Results")
                                .fontWeight(.semibold)
                                .foregroundColor(.white)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 16)
                                .background(
                                    RoundedRectangle(cornerRadius: 14)
                                        .fill(LinearGradient(colors: [.purple, .blue], startPoint: .leading, endPoint: .trailing))
                                )
                        }
                    } else {
                        Button(action: { quizVM.submitAnswer() }) {
                            Text("Submit Answer")
                                .fontWeight(.semibold)
                                .foregroundColor(.white)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 16)
                                .background(
                                    RoundedRectangle(cornerRadius: 14)
                                        .fill(
                                            quizVM.selectedOption != nil
                                                ? LinearGradient(colors: [.purple, .blue], startPoint: .leading, endPoint: .trailing)
                                                : LinearGradient(colors: [.gray], startPoint: .leading, endPoint: .trailing)
                                        )
                                )
                        }
                        .disabled(quizVM.selectedOption == nil)
                    }
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(Color(.systemGroupedBackground))
            }
        }
    }

    private func quizOptionButton(label: String, optionValue: String, question: QuizQuestion, index: Int) -> some View {
        let isSelected = quizVM.selectedOption == optionValue
        let isAnswered = quizVM.showExplanation
        let isCorrectAnswer = optionValue == question.correctAnswer.value ||
                              String(index) == question.correctAnswer.value

        let borderColor: Color = {
            if !isAnswered { return isSelected ? .purple : Color(.systemGray4) }
            if isCorrectAnswer { return .green }
            if isSelected && !isCorrectAnswer { return .red }
            return Color(.systemGray4)
        }()

        let bgColor: Color = {
            if !isAnswered { return isSelected ? .purple.opacity(0.1) : Color(.secondarySystemGroupedBackground) }
            if isCorrectAnswer { return .green.opacity(0.1) }
            if isSelected && !isCorrectAnswer { return .red.opacity(0.1) }
            return Color(.secondarySystemGroupedBackground)
        }()

        return Button(action: {
            guard !isAnswered else { return }
            quizVM.selectedOption = optionValue
        }) {
            HStack {
                Text(label)
                    .font(.subheadline)
                    .foregroundColor(.primary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer()

                if isAnswered {
                    if isCorrectAnswer {
                        Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                    } else if isSelected {
                        Image(systemName: "xmark.circle.fill").foregroundColor(.red)
                    }
                } else if isSelected {
                    Image(systemName: "checkmark.circle.fill").foregroundColor(.purple)
                }
            }
            .padding(14)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(bgColor)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(borderColor, lineWidth: 1.5)
                    )
            )
        }
        .buttonStyle(.plain)
        .animation(.easeInOut(duration: 0.15), value: isSelected)
        .animation(.easeInOut(duration: 0.15), value: isAnswered)
    }

    private func explanationCard(explanation: String, isCorrect: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: isCorrect ? "checkmark.circle.fill" : "lightbulb.fill")
                .foregroundColor(isCorrect ? .green : .orange)
                .font(.title3)

            VStack(alignment: .leading, spacing: 4) {
                Text(isCorrect ? "Correct!" : "Not quite — here's why:")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundColor(isCorrect ? .green : .orange)

                Text(explanation)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(isCorrect ? Color.green.opacity(0.08) : Color.orange.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(isCorrect ? Color.green.opacity(0.3) : Color.orange.opacity(0.3), lineWidth: 1)
                )
        )
    }

    // MARK: - Result View

    private var quizResultView: some View {
        VStack(spacing: 28) {
            Spacer()

            // Score circle
            ZStack {
                Circle()
                    .stroke(Color.purple.opacity(0.15), lineWidth: 10)
                    .frame(width: 130, height: 130)

                Circle()
                    .trim(from: 0, to: Double(quizVM.score) / Double(quiz.questions.count))
                    .stroke(
                        LinearGradient(colors: quizVM.passed ? [.purple, .blue] : [.orange, .red], startPoint: .leading, endPoint: .trailing),
                        style: StrokeStyle(lineWidth: 10, lineCap: .round)
                    )
                    .frame(width: 130, height: 130)
                    .rotationEffect(.degrees(-90))
                    .animation(.easeOut(duration: 0.8), value: quizVM.score)

                VStack(spacing: 2) {
                    Text("\(quizVM.score)/\(quiz.questions.count)")
                        .font(.title2)
                        .fontWeight(.bold)

                    Text(quizVM.passed ? "Passed!" : "Try again")
                        .font(.caption)
                        .foregroundColor(quizVM.passed ? .purple : .red)
                }
            }

            VStack(spacing: 8) {
                Text(quizVM.passed ? "Module Complete!" : "Keep Practicing")
                    .font(.title2)
                    .fontWeight(.bold)

                Text(quizVM.passed
                     ? "You scored \(Int(Double(quizVM.score) / Double(quiz.questions.count) * 100))% — great work!"
                     : "You scored \(Int(Double(quizVM.score) / Double(quiz.questions.count) * 100))%. You need \(quiz.passingScore ?? 70)% to pass.")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            VStack(spacing: 12) {
                Button(action: { dismiss() }) {
                    Text("Back to Course")
                        .fontWeight(.semibold)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(LinearGradient(colors: [.purple, .blue], startPoint: .leading, endPoint: .trailing))
                        )
                }

                if !quizVM.passed {
                    Button(action: {
                        quizVM.currentIndex = 0
                        quizVM.score = 0
                        quizVM.selectedOption = nil
                        quizVM.showExplanation = false
                        quizVM.isComplete = false
                    }) {
                        Text("Retry Quiz")
                            .fontWeight(.medium)
                            .foregroundColor(.purple)
                    }
                }
            }
            .padding(.horizontal, 32)

            Spacer()
        }
    }

    // MARK: - Celebration Overlay

    private var celebrationOverlay: some View {
        ZStack {
            Color.black.opacity(0.5).ignoresSafeArea()

            VStack(spacing: 20) {
                Text("🎓")
                    .font(.system(size: 80))
                    .transition(.scale.combined(with: .opacity))

                Text("Module Mastered!")
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundColor(.white)
            }
        }
        .transition(.opacity)
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                withAnimation { showCelebration = false }
            }
        }
    }
}

// MARK: - Previews

struct LessonReaderView_Previews: PreviewProvider {
    static let mockLesson = CourseLesson(
        lessonId: "l1",
        title: "Understanding Swift Closures",
        content: """
        # What are Closures?

        Closures are **self-contained blocks** of functionality that can be passed around and used in your code.

        ## Syntax

        ```swift
        let greet = { (name: String) -> String in
            return "Hello, \\(name)!"
        }
        ```

        They can capture values from the surrounding context, which is why they are often used for callbacks and async operations.

        ## Key Uses

        - Completion handlers
        - Sorting algorithms using `sorted(by:)`
        - Higher-order functions like `map`, `filter`, `reduce`
        """,
        type: .text,
        estimatedMinutes: 15,
        resources: nil
    )

    static var previews: some View {
        NavigationStack {
            LessonReaderView(lesson: mockLesson, moduleTitle: "Swift Fundamentals")
        }
    }
}

struct ModuleQuizView_Previews: PreviewProvider {
    static let mockQuiz = CourseQuiz(
        quizId: "q1",
        title: "Swift Closures Quiz",
        questions: [
            QuizQuestion(
                questionId: "qq1",
                question: "What keyword introduces the body of a closure?",
                type: .multipleChoice,
                options: ["in", "do", "begin", "return"],
                correctAnswer: QuizAnswer(value: "in", index: 0),
                explanation: "The `in` keyword separates the closure parameters and return type from the body."
            )
        ],
        passingScore: 70
    )

    static var previews: some View {
        NavigationStack {
            ModuleQuizView(quiz: mockQuiz, moduleTitle: "Swift Fundamentals")
        }
    }
}
