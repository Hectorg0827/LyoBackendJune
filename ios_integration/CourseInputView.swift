// CourseInputView.swift
// Lyo
//
// Topic entry, difficulty picker, and generation progress screen.
// Copy this file to: Lyo/Views/AIClassroom/CourseInputView.swift
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import SwiftUI
import Combine

// MARK: - Course Input View

struct CourseInputView: View {
    @Binding var topic: String
    @Binding var selectedDifficulty: CourseDifficulty
    @ObservedObject var generationVM: CourseGenerationViewModel
    let onGenerate: () -> Void

    @State private var showError = false

    var body: some View {
        ScrollView {
            VStack(spacing: 28) {
                // Hero header
                heroHeader

                // Topic input
                topicInputSection

                // Difficulty picker
                difficultySection

                // Generate button or progress
                if generationVM.isLoading {
                    generationProgressSection
                } else {
                    generateButton
                }

                // Error banner
                if let errorMessage = generationVM.errorMessage {
                    errorBanner(message: errorMessage)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 32)
        }
        .navigationTitle("AI Course Generator")
        .navigationBarTitleDisplayMode(.large)
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
    }

    // MARK: - Subviews

    private var heroHeader: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [.purple.opacity(0.2), .blue.opacity(0.2)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 80, height: 80)

                Image(systemName: "sparkles")
                    .font(.system(size: 36))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.purple, .blue],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            }

            Text("What do you want to learn?")
                .font(.title2)
                .fontWeight(.bold)
                .multilineTextAlignment(.center)

            Text("Describe any topic and AI will build a structured course tailored for you.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 8)
    }

    private var topicInputSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Topic", systemImage: "text.cursor")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(.secondary)

            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.secondarySystemGroupedBackground))
                    .shadow(color: .black.opacity(0.04), radius: 4, x: 0, y: 2)

                if topic.isEmpty {
                    Text("e.g. SwiftUI animations, machine learning basics, Spanish for beginners…")
                        .foregroundColor(.secondary.opacity(0.6))
                        .font(.body)
                        .padding(14)
                        .allowsHitTesting(false)
                }

                TextEditor(text: $topic)
                    .font(.body)
                    .frame(minHeight: 80, maxHeight: 120)
                    .padding(10)
                    .scrollContentBackground(.hidden)
                    .background(Color.clear)
            }
            .frame(minHeight: 80)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(topic.isEmpty ? Color.clear : Color.purple.opacity(0.4), lineWidth: 1.5)
            )

            // Character hint
            HStack {
                Spacer()
                Text("\(topic.count) chars")
                    .font(.caption2)
                    .foregroundColor(.secondary.opacity(0.6))
            }
        }
    }

    private var difficultySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Difficulty", systemImage: "chart.bar.fill")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(.secondary)

            // Segmented picker
            Picker("Difficulty", selection: $selectedDifficulty) {
                ForEach(CourseDifficulty.allCases) { level in
                    Text(level.displayName).tag(level)
                }
            }
            .pickerStyle(.segmented)

            // Live description card for selected difficulty
            HStack(spacing: 12) {
                Image(systemName: selectedDifficulty.icon)
                    .font(.title3)
                    .foregroundColor(selectedDifficulty.color)
                    .frame(width: 28)

                Text(selectedDifficulty.description)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(selectedDifficulty.color.opacity(0.08))
            )
            .animation(.easeInOut(duration: 0.2), value: selectedDifficulty)
        }
    }

    private var generateButton: some View {
        Button(action: onGenerate) {
            HStack(spacing: 10) {
                Image(systemName: "sparkles")
                Text("Generate Course")
                    .fontWeight(.semibold)
            }
            .font(.body)
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(
                        topic.trimmingCharacters(in: .whitespaces).isEmpty
                            ? LinearGradient(colors: [.gray], startPoint: .leading, endPoint: .trailing)
                            : LinearGradient(colors: [.purple, .blue], startPoint: .leading, endPoint: .trailing)
                    )
            )
            .shadow(
                color: topic.isEmpty ? .clear : .purple.opacity(0.3),
                radius: 8, x: 0, y: 4
            )
        }
        .disabled(topic.trimmingCharacters(in: .whitespaces).isEmpty)
        .animation(.easeInOut(duration: 0.15), value: topic.isEmpty)
    }

    private var generationProgressSection: some View {
        VStack(spacing: 20) {
            // Progress ring + step label
            VStack(spacing: 16) {
                ZStack {
                    Circle()
                        .stroke(Color.purple.opacity(0.15), lineWidth: 6)
                        .frame(width: 72, height: 72)

                    Circle()
                        .trim(from: 0, to: generationVM.progress)
                        .stroke(
                            LinearGradient(colors: [.purple, .blue], startPoint: .leading, endPoint: .trailing),
                            style: StrokeStyle(lineWidth: 6, lineCap: .round)
                        )
                        .frame(width: 72, height: 72)
                        .rotationEffect(.degrees(-90))
                        .animation(.easeInOut(duration: 0.5), value: generationVM.progress)

                    Text("\(Int(generationVM.progress * 100))%")
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundColor(.purple)
                }

                VStack(spacing: 6) {
                    Text(statusTitle)
                        .font(.headline)
                        .foregroundColor(.primary)

                    if let step = generationVM.jobStatus?.currentStep {
                        Text(step)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                }
            }

            // Thin progress bar (replicates ProgressBar from InteractiveCinemaView)
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.purple.opacity(0.15))
                        .frame(height: 4)

                    RoundedRectangle(cornerRadius: 2)
                        .fill(
                            LinearGradient(colors: [.purple, .blue], startPoint: .leading, endPoint: .trailing)
                        )
                        .frame(width: geometry.size.width * generationVM.progress, height: 4)
                        .animation(.easeInOut(duration: 0.5), value: generationVM.progress)
                }
            }
            .frame(height: 4)

            // Cancel button
            Button(action: { generationVM.cancelGeneration() }) {
                Text("Cancel")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color(.secondarySystemGroupedBackground))
                .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 2)
        )
    }

    private var statusTitle: String {
        switch generationVM.jobStatus?.status {
        case .pending:
            return "Queuing your request…"
        case .inProgress:
            return "Building your course…"
        case .completed:
            return "Course ready!"
        case .failed, .cancelled:
            return "Generation stopped"
        case .none:
            return "Starting…"
        }
    }

    private func errorBanner(message: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.red)

            Text(message)
                .font(.caption)
                .foregroundColor(.red)
                .fixedSize(horizontal: false, vertical: true)

            Spacer()

            Button(action: { generationVM.errorMessage = nil }) {
                Image(systemName: "xmark")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.red.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.red.opacity(0.2), lineWidth: 1)
                )
        )
    }
}

// MARK: - Preview

struct CourseInputView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            CourseInputView(
                topic: .constant(""),
                selectedDifficulty: .constant(.intermediate),
                generationVM: CourseGenerationViewModel(),
                onGenerate: {}
            )
        }
    }
}
