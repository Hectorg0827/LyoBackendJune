// LiveClassroomView.swift
// Lyo
//
// Live AI Classroom with Course Generation - Fixes job_id parsing error
// Copy this file to: Lyo/Views/LiveClassroom/LiveClassroomView.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import SwiftUI
import Combine

// MARK: - Live Classroom View

struct LiveClassroomView: View {
    @StateObject private var courseGeneration = CourseGenerationViewModel()
    @State private var topicInput = ""
    @State private var selectedDifficulty = "intermediate"
    @State private var showCourseResult = false
    @FocusState private var isInputFocused: Bool
    @Environment(\.dismiss) private var dismiss

    let difficulties = ["beginner", "intermediate", "advanced"]

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                if courseGeneration.isLoading {
                    courseGenerationView
                } else if let courseResult = courseGeneration.courseResult {
                    courseResultView(courseResult)
                } else {
                    courseRequestView
                }
            }
            .navigationTitle("AI Classroom")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close") {
                        courseGeneration.cancelGeneration()
                        dismiss()
                    }
                }

                if courseGeneration.isLoading {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Cancel") {
                            courseGeneration.cancelGeneration()
                        }
                        .foregroundColor(.red)
                    }
                }
            }
        }
        .alert("Error", isPresented: .constant(courseGeneration.errorMessage != nil)) {
            Button("OK") {
                courseGeneration.errorMessage = nil
            }
        } message: {
            Text(courseGeneration.errorMessage ?? "")
        }
    }

    // MARK: - Course Request View

    private var courseRequestView: some View {
        VStack(spacing: 24) {
            // Header
            VStack(spacing: 16) {
                Image(systemName: "graduationcap.fill")
                    .font(.system(size: 64))
                    .foregroundColor(.blue)

                Text("AI Course Generator")
                    .font(.title)
                    .fontWeight(.bold)

                Text("Enter any topic and I'll create a personalized course for you!")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            .padding(.top, 40)

            Spacer()

            // Input Section
            VStack(spacing: 20) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("What would you like to learn?")
                        .font(.headline)

                    TextField("e.g., Machine Learning, iOS Development, Spanish...", text: $topicInput)
                        .textFieldStyle(.roundedBorder)
                        .focused($isInputFocused)
                        .onSubmit {
                            generateCourse()
                        }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Difficulty Level")
                        .font(.headline)

                    Picker("Difficulty", selection: $selectedDifficulty) {
                        ForEach(difficulties, id: \.self) { difficulty in
                            Text(difficulty.capitalized).tag(difficulty)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Button(action: generateCourse) {
                    HStack {
                        Image(systemName: "sparkles")
                        Text("Generate Course")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(12)
                }
                .disabled(topicInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(.horizontal, 24)

            Spacer()

            // Examples
            VStack(alignment: .leading, spacing: 12) {
                Text("Popular Topics")
                    .font(.headline)
                    .padding(.horizontal, 24)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(exampleTopics, id: \.self) { topic in
                            Button(topic) {
                                topicInput = topic
                                generateCourse()
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(Color.blue.opacity(0.1))
                            .foregroundColor(.blue)
                            .cornerRadius(20)
                        }
                    }
                    .padding(.horizontal, 24)
                }
            }

            Spacer()
        }
    }

    // MARK: - Course Generation View

    private var courseGenerationView: some View {
        VStack(spacing: 32) {
            Spacer()

            VStack(spacing: 20) {
                // Animation
                ZStack {
                    Circle()
                        .stroke(Color.blue.opacity(0.2), lineWidth: 8)
                        .frame(width: 120, height: 120)

                    Circle()
                        .trim(from: 0, to: courseGeneration.progress)
                        .stroke(Color.blue, style: StrokeStyle(lineWidth: 8, lineCap: .round))
                        .frame(width: 120, height: 120)
                        .rotationEffect(.degrees(-90))
                        .animation(.easeInOut(duration: 0.5), value: courseGeneration.progress)

                    VStack {
                        Image(systemName: "brain.head.profile")
                            .font(.title)
                            .foregroundColor(.blue)

                        Text("\(Int(courseGeneration.progress * 100))%")
                            .font(.caption)
                            .fontWeight(.medium)
                    }
                }

                Text("Creating Your Course")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Topic: \(topicInput)")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                if let currentStep = courseGeneration.jobStatus?.currentStep {
                    Text(currentStep)
                        .font(.body)
                        .foregroundColor(.blue)
                        .padding(.horizontal)
                        .multilineTextAlignment(.center)
                }
            }

            Spacer()

            // Progress Steps
            VStack(spacing: 16) {
                progressStep("Analyzing Topic", completed: courseGeneration.progress > 0.2)
                progressStep("Structuring Curriculum", completed: courseGeneration.progress > 0.5)
                progressStep("Creating Content", completed: courseGeneration.progress > 0.8)
                progressStep("Finalizing Course", completed: courseGeneration.progress >= 1.0)
            }
            .padding(.horizontal, 24)

            Spacer()
        }
    }

    // MARK: - Course Result View

    private func courseResultView(_ course: CourseResult) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.green)
                            .font(.title)

                        Text("Course Ready!")
                            .font(.title2)
                            .fontWeight(.bold)

                        Spacer()
                    }

                    Text(course.title)
                        .font(.title)
                        .fontWeight(.bold)
                        .foregroundColor(.primary)

                    Text(course.description)
                        .font(.body)
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, 20)
                .padding(.top, 20)

                // Course Info
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        CourseInfoPill(
                            icon: "clock",
                            text: "\(Int(course.estimatedHours))h",
                            color: .blue
                        )

                        CourseInfoPill(
                            icon: "chart.bar",
                            text: course.difficulty.capitalized,
                            color: difficultyColor(course.difficulty)
                        )

                        CourseInfoPill(
                            icon: "book",
                            text: "\(course.modules.count) modules",
                            color: .green
                        )

                        Spacer()
                    }

                    if !course.learningObjectives.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Learning Objectives")
                                .font(.headline)

                            ForEach(course.learningObjectives.prefix(3), id: \.self) { objective in
                                HStack(alignment: .top) {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundColor(.green)
                                        .font(.caption)
                                        .padding(.top, 2)

                                    Text(objective)
                                        .font(.body)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, 20)

                // Modules
                VStack(alignment: .leading, spacing: 16) {
                    Text("Course Modules")
                        .font(.headline)
                        .padding(.horizontal, 20)

                    ForEach(course.modules.indices, id: \.self) { index in
                        let module = course.modules[index]
                        ModuleCardView(module: module, moduleNumber: index + 1)
                    }
                }

                // Action Button
                Button(action: {
                    // Handle starting the course
                    print("Starting course: \(course.courseId)")
                }) {
                    HStack {
                        Image(systemName: "play.fill")
                        Text("Start Learning")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(12)
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 20)
            }
        }
    }

    // MARK: - Helper Views

    private func progressStep(_ title: String, completed: Bool) -> some View {
        HStack {
            Image(systemName: completed ? "checkmark.circle.fill" : "circle")
                .foregroundColor(completed ? .green : .gray)

            Text(title)
                .font(.body)
                .foregroundColor(completed ? .primary : .secondary)

            Spacer()
        }
    }

    private func difficultyColor(_ difficulty: String) -> Color {
        switch difficulty.lowercased() {
        case "beginner": return .green
        case "intermediate": return .orange
        case "advanced": return .red
        default: return .blue
        }
    }

    // MARK: - Actions

    private func generateCourse() {
        let topic = topicInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !topic.isEmpty else { return }

        isInputFocused = false
        courseGeneration.generateCourse(topic: topic, difficulty: selectedDifficulty)
    }

    // MARK: - Constants

    private let exampleTopics = [
        "Machine Learning", "iOS Development", "Spanish Grammar",
        "Photography", "Python Programming", "Digital Marketing"
    ]
}

// MARK: - Supporting Views

struct CourseInfoPill: View {
    let icon: String
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption)
            Text(text)
                .font(.caption)
                .fontWeight(.medium)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(color.opacity(0.1))
        .foregroundColor(color)
        .cornerRadius(12)
    }
}

struct ModuleCardView: View {
    let module: CourseModule
    let moduleNumber: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Module \(moduleNumber)")
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundColor(.blue)

                Spacer()

                Text("\(module.estimatedMinutes) min")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Text(module.title)
                .font(.headline)
                .fontWeight(.semibold)

            Text(module.description)
                .font(.body)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if !module.lessons.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Lessons:")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundColor(.secondary)

                    ForEach(module.lessons.prefix(3), id: \.lessonId) { lesson in
                        HStack {
                            Image(systemName: lessonTypeIcon(lesson.type))
                                .foregroundColor(.blue)
                                .font(.caption)

                            Text(lesson.title)
                                .font(.caption)
                                .foregroundColor(.secondary)

                            Spacer()
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Color(.systemGray6))
        .cornerRadius(12)
        .padding(.horizontal, 20)
    }

    private func lessonTypeIcon(_ type: LessonType) -> String {
        switch type {
        case .text: return "doc.text"
        case .video: return "play.rectangle"
        case .interactive: return "hand.tap"
        case .exercise: return "pencil.and.outline"
        case .reading: return "book"
        }
    }
}

// MARK: - Preview

#Preview {
    LiveClassroomView()
}