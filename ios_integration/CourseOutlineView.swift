// CourseOutlineView.swift
// Lyo
//
// Course overview with expandable module/lesson list.
// Copy this file to: Lyo/Views/AIClassroom/CourseOutlineView.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import SwiftUI

// MARK: - Course Outline View

struct CourseOutlineView: View {
    let course: CourseResult
    @Binding var navigationPath: NavigationPath

    @State private var expandedModuleIds: Set<String> = []
    @State private var showObjectives = false

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 0, pinnedViews: [.sectionHeaders]) {
                // Course header card
                courseHeaderCard
                    .padding(.horizontal, 16)
                    .padding(.top, 16)
                    .padding(.bottom, 8)

                // Learning objectives
                objectivesSection
                    .padding(.horizontal, 16)
                    .padding(.bottom, 16)

                // Module list
                Section {
                    ForEach(course.modules) { module in
                        moduleRow(module)
                            .padding(.horizontal, 16)
                            .padding(.bottom, 8)
                    }
                } header: {
                    modulesHeader
                }
            }
            .padding(.bottom, 32)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationTitle(course.title)
        .navigationBarTitleDisplayMode(.large)
        .onAppear {
            // Auto-expand first module
            if let first = course.modules.first {
                expandedModuleIds.insert(first.moduleId)
            }
        }
    }

    // MARK: - Header Card

    private var courseHeaderCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Tags row
            if !course.tags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(course.tags, id: \.self) { tag in
                            Text(tag)
                                .font(.caption2)
                                .fontWeight(.medium)
                                .foregroundColor(.purple)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 4)
                                .background(Capsule().fill(Color.purple.opacity(0.12)))
                        }
                    }
                }
            }

            // Description
            Text(course.description)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Divider()

            // Stats row
            HStack(spacing: 20) {
                statPill(
                    icon: "chart.bar.fill",
                    label: course.difficulty.capitalized,
                    color: difficultyColor(course.difficulty)
                )
                statPill(
                    icon: "clock.fill",
                    label: String(format: "%.0f hrs", course.estimatedHours),
                    color: .blue
                )
                statPill(
                    icon: "square.stack.fill",
                    label: "\(course.modules.count) modules",
                    color: .indigo
                )
                let totalLessons = course.modules.reduce(0) { $0 + $1.lessons.count }
                statPill(
                    icon: "doc.text.fill",
                    label: "\(totalLessons) lessons",
                    color: .teal
                )
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color(.secondarySystemGroupedBackground))
                .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 2)
        )
    }

    // MARK: - Objectives

    private var objectivesSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            DisclosureGroup(
                isExpanded: $showObjectives,
                content: {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(course.learningObjectives, id: \.self) { objective in
                            HStack(alignment: .top, spacing: 10) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(.green)
                                    .font(.subheadline)
                                    .padding(.top, 1)

                                Text(objective)
                                    .font(.subheadline)
                                    .foregroundColor(.primary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    .padding(.top, 12)
                },
                label: {
                    Label("Learning Objectives", systemImage: "target")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                }
            )
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.secondarySystemGroupedBackground))
            )
        }
    }

    // MARK: - Modules Header

    private var modulesHeader: some View {
        HStack {
            Text("Course Modules")
                .font(.headline)
                .fontWeight(.bold)

            Spacer()

            Button(action: toggleAllModules) {
                Text(expandedModuleIds.count == course.modules.count ? "Collapse All" : "Expand All")
                    .font(.caption)
                    .foregroundColor(.purple)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color(.systemGroupedBackground))
    }

    // MARK: - Module Row

    private func moduleRow(_ module: CourseModule) -> some View {
        VStack(spacing: 0) {
            // Module header (tap to expand/collapse)
            Button(action: { toggleModule(module.moduleId) }) {
                HStack(spacing: 12) {
                    // Module index circle
                    let index = course.modules.firstIndex(where: { $0.moduleId == module.moduleId }) ?? 0
                    ZStack {
                        Circle()
                            .fill(
                                LinearGradient(
                                    colors: [.purple.opacity(0.7), .blue.opacity(0.7)],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 32, height: 32)
                        Text("\(index + 1)")
                            .font(.caption)
                            .fontWeight(.bold)
                            .foregroundColor(.white)
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text(module.title)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .foregroundColor(.primary)
                            .multilineTextAlignment(.leading)

                        HStack(spacing: 6) {
                            Text("\(module.lessons.count) lessons")
                                .font(.caption2)
                                .foregroundColor(.secondary)

                            Text("·")
                                .font(.caption2)
                                .foregroundColor(.secondary)

                            Text("\(module.estimatedMinutes) min")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }

                    Spacer()

                    Image(systemName: expandedModuleIds.contains(module.moduleId) ? "chevron.up" : "chevron.down")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(14)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            // Expanded content
            if expandedModuleIds.contains(module.moduleId) {
                VStack(spacing: 0) {
                    Divider()
                        .padding(.horizontal, 14)

                    // Lesson rows
                    ForEach(module.lessons) { lesson in
                        lessonRow(lesson, moduleTitle: module.title)

                        if lesson.lessonId != module.lessons.last?.lessonId {
                            Divider()
                                .padding(.leading, 52)
                        }
                    }

                    // Quiz button (if quiz exists)
                    if let quiz = module.quiz {
                        Divider()
                            .padding(.horizontal, 14)

                        Button(action: {
                            navigationPath.append(CourseDestination.moduleQuiz(quiz, moduleTitle: module.title))
                        }) {
                            HStack(spacing: 12) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(Color.purple.opacity(0.15))
                                        .frame(width: 32, height: 32)
                                    Image(systemName: "questionmark.circle.fill")
                                        .font(.subheadline)
                                        .foregroundColor(.purple)
                                }

                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Module Quiz")
                                        .font(.subheadline)
                                        .fontWeight(.semibold)
                                        .foregroundColor(.purple)
                                    Text("\(quiz.questions.count) questions")
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                }

                                Spacer()

                                Image(systemName: "chevron.right")
                                    .font(.caption)
                                    .foregroundColor(.purple.opacity(0.6))
                            }
                            .padding(14)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color(.secondarySystemGroupedBackground))
                .shadow(color: .black.opacity(0.04), radius: 4, x: 0, y: 2)
        )
        .animation(.easeInOut(duration: 0.2), value: expandedModuleIds.contains(module.moduleId))
    }

    // MARK: - Lesson Row

    private func lessonRow(_ lesson: CourseLesson, moduleTitle: String) -> some View {
        Button(action: {
            navigationPath.append(CourseDestination.lessonReader(lesson, moduleTitle: moduleTitle))
        }) {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(lessonTypeColor(lesson.type).opacity(0.12))
                        .frame(width: 32, height: 32)
                    Image(systemName: lessonTypeIcon(lesson.type))
                        .font(.subheadline)
                        .foregroundColor(lessonTypeColor(lesson.type))
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(lesson.title)
                        .font(.subheadline)
                        .foregroundColor(.primary)
                        .multilineTextAlignment(.leading)

                    HStack(spacing: 6) {
                        Text(lessonTypeLabel(lesson.type))
                            .font(.caption2)
                            .foregroundColor(.secondary)

                        Text("·")
                            .font(.caption2)
                            .foregroundColor(.secondary)

                        Text("\(lesson.estimatedMinutes) min")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundColor(.secondary.opacity(0.5))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - Helpers

    private func toggleModule(_ id: String) {
        withAnimation(.easeInOut(duration: 0.2)) {
            if expandedModuleIds.contains(id) {
                expandedModuleIds.remove(id)
            } else {
                expandedModuleIds.insert(id)
            }
        }
    }

    private func toggleAllModules() {
        withAnimation(.easeInOut(duration: 0.2)) {
            if expandedModuleIds.count == course.modules.count {
                expandedModuleIds.removeAll()
            } else {
                expandedModuleIds = Set(course.modules.map(\.moduleId))
            }
        }
    }

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

    private func difficultyColor(_ difficulty: String) -> Color {
        switch difficulty.lowercased() {
        case "beginner": return .green
        case "intermediate": return .orange
        case "advanced": return .red
        default: return .secondary
        }
    }

    private func statPill(icon: String, label: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
                .foregroundColor(color)
            Text(label)
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - Codable Identifiable Conformances

extension CourseModule: Identifiable {
    public var id: String { moduleId }
}

extension CourseLesson: Identifiable {
    public var id: String { lessonId }
}

// MARK: - Preview

struct CourseOutlineView_Previews: PreviewProvider {
    static let mockCourse = CourseResult(
        courseId: "preview-1",
        title: "SwiftUI Animations",
        description: "Master SwiftUI animations from basics to advanced techniques.",
        difficulty: "intermediate",
        estimatedHours: 3.0,
        modules: [
            CourseModule(
                moduleId: "m1",
                title: "Getting Started with Animations",
                description: "Learn the fundamentals.",
                estimatedMinutes: 45,
                lessons: [
                    CourseLesson(lessonId: "l1", title: "Implicit vs Explicit Animations", content: "Content here", type: .text, estimatedMinutes: 15, resources: nil),
                    CourseLesson(lessonId: "l2", title: "withAnimation deep dive", content: "Content here", type: .reading, estimatedMinutes: 20, resources: nil)
                ],
                quiz: nil
            )
        ],
        prerequisites: [],
        learningObjectives: ["Understand animation types", "Build custom transitions"],
        tags: ["SwiftUI", "iOS", "Animations"]
    )

    static var previews: some View {
        NavigationStack {
            CourseOutlineView(course: mockCourse, navigationPath: .constant(NavigationPath()))
        }
    }
}
