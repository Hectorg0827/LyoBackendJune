import SwiftUI

// MARK: - Lyo Business Components
// These are pre-built native components that can be used in A2UI for complex UI patterns

struct LyoCourseCard: View {
    let title: String
    let description: String
    let imageUrl: String?
    let progress: Double
    let difficulty: String
    let duration: String
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 12) {
                // Course Image
                AsyncImage(url: imageUrl.flatMap(URL.init)) { image in
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                } placeholder: {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(LinearGradient(
                            colors: [Color.lyoPrimary.opacity(0.3), Color.lyoSecondary.opacity(0.3)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ))
                        .overlay(
                            Image(systemName: "book.fill")
                                .font(.title)
                                .foregroundColor(.white.opacity(0.8))
                        )
                }
                .frame(height: 120)
                .cornerRadius(8)
                .clipped()

                VStack(alignment: .leading, spacing: 8) {
                    // Title
                    Text(title)
                        .font(.headline)
                        .foregroundColor(.primary)
                        .lineLimit(2)

                    // Description
                    Text(description)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(3)

                    // Progress Bar
                    if progress > 0 {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text("Progress")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                Spacer()
                                Text("\(Int(progress))%")
                                    .font(.caption2)
                                    .fontWeight(.medium)
                                    .foregroundColor(.lyoPrimary)
                            }

                            ProgressView(value: progress / 100)
                                .progressViewStyle(LinearProgressViewStyle(tint: .lyoPrimary))
                        }
                    }

                    // Meta Information
                    HStack {
                        Label(difficulty, systemImage: "speedometer")
                            .font(.caption2)
                            .foregroundColor(.secondary)

                        Spacer()

                        Label(duration, systemImage: "clock")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal, 4)
            }
            .padding()
            .background(Color(.systemBackground))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color(.systemGray5), lineWidth: 1)
            )
            .cornerRadius(12)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

struct LyoLessonCard: View {
    let title: String
    let description: String
    let isCompleted: Bool
    let duration: String
    let lessonType: String
    let onTap: () -> Void

    private var typeIcon: String {
        switch lessonType.lowercased() {
        case "video":
            return "play.circle.fill"
        case "reading":
            return "doc.text.fill"
        case "quiz":
            return "questionmark.circle.fill"
        case "exercise":
            return "pencil.circle.fill"
        default:
            return "circle.fill"
        }
    }

    private var typeColor: Color {
        switch lessonType.lowercased() {
        case "video":
            return .red
        case "reading":
            return .blue
        case "quiz":
            return .purple
        case "exercise":
            return .green
        default:
            return .gray
        }
    }

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 16) {
                // Lesson Type Icon
                ZStack {
                    Circle()
                        .fill(typeColor.opacity(0.1))
                        .frame(width: 50, height: 50)

                    Image(systemName: typeIcon)
                        .font(.title2)
                        .foregroundColor(typeColor)
                }

                // Content
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(title)
                            .font(.headline)
                            .foregroundColor(.primary)
                            .lineLimit(2)

                        Spacer()

                        if isCompleted {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.lyoSuccess)
                                .font(.title3)
                        }
                    }

                    Text(description)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(2)

                    HStack {
                        Text(lessonType.capitalized)
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(typeColor.opacity(0.1))
                            .foregroundColor(typeColor)
                            .cornerRadius(6)

                        Spacer()

                        Label(duration, systemImage: "clock")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                // Chevron
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding()
            .background(Color(.systemBackground))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color(.systemGray5), lineWidth: 1)
            )
            .cornerRadius(10)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

struct LyoQuizComponent: View {
    let question: String
    let options: [String]
    let correctAnswer: Int
    let selectedAnswer: Int?
    let onAnswerSelected: (Int) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Question
            Text(question)
                .font(.headline)
                .foregroundColor(.primary)
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.systemGray6))
                .cornerRadius(10)

            // Options
            VStack(spacing: 12) {
                ForEach(Array(options.enumerated()), id: \.offset) { index, option in
                    Button(action: {
                        onAnswerSelected(index)
                    }) {
                        HStack {
                            // Option letter
                            ZStack {
                                Circle()
                                    .fill(getOptionBackgroundColor(index: index))
                                    .frame(width: 32, height: 32)

                                Text("\(Character(UnicodeScalar(65 + index)!))")
                                    .font(.headline)
                                    .fontWeight(.bold)
                                    .foregroundColor(getOptionTextColor(index: index))
                            }

                            // Option text
                            Text(option)
                                .font(.body)
                                .foregroundColor(.primary)
                                .multilineTextAlignment(.leading)

                            Spacer()

                            // Selection indicator
                            if selectedAnswer == index {
                                Image(systemName: getSelectionIcon(index: index))
                                    .foregroundColor(getSelectionColor(index: index))
                                    .font(.title3)
                            }
                        }
                        .padding()
                        .background(getOptionBackgroundColor(index: index).opacity(0.1))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(getOptionBorderColor(index: index), lineWidth: 2)
                        )
                        .cornerRadius(8)
                    }
                    .buttonStyle(PlainButtonStyle())
                    .disabled(selectedAnswer != nil)
                }
            }

            // Show explanation if answered
            if let selected = selectedAnswer {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Image(systemName: selected == correctAnswer ? "checkmark.circle.fill" : "x.circle.fill")
                            .foregroundColor(selected == correctAnswer ? .lyoSuccess : .lyoError)
                        Text(selected == correctAnswer ? "Correct!" : "Incorrect")
                            .font(.headline)
                            .foregroundColor(selected == correctAnswer ? .lyoSuccess : .lyoError)
                    }

                    if selected != correctAnswer {
                        Text("The correct answer is \(Character(UnicodeScalar(65 + correctAnswer)!)): \(options[correctAnswer])")
                            .font(.body)
                            .foregroundColor(.secondary)
                    }
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(8)
            }
        }
    }

    private func getOptionBackgroundColor(index: Int) -> Color {
        guard let selected = selectedAnswer else {
            return .lyoPrimary
        }

        if index == correctAnswer {
            return .lyoSuccess
        } else if index == selected && selected != correctAnswer {
            return .lyoError
        } else {
            return .gray
        }
    }

    private func getOptionTextColor(index: Int) -> Color {
        return .white
    }

    private func getOptionBorderColor(index: Int) -> Color {
        guard let selected = selectedAnswer else {
            return .clear
        }

        if index == correctAnswer {
            return .lyoSuccess
        } else if index == selected && selected != correctAnswer {
            return .lyoError
        } else {
            return .clear
        }
    }

    private func getSelectionIcon(index: Int) -> String {
        guard let selected = selectedAnswer else {
            return ""
        }

        if index == correctAnswer {
            return "checkmark.circle.fill"
        } else if index == selected && selected != correctAnswer {
            return "x.circle.fill"
        } else {
            return ""
        }
    }

    private func getSelectionColor(index: Int) -> Color {
        guard let selected = selectedAnswer else {
            return .clear
        }

        if index == correctAnswer {
            return .lyoSuccess
        } else if index == selected && selected != correctAnswer {
            return .lyoError
        } else {
            return .clear
        }
    }
}

// MARK: - Achievement Badge Component
struct LyoAchievementBadge: View {
    let title: String
    let description: String
    let iconName: String
    let rarity: String
    let isEarned: Bool
    let onTap: (() -> Void)?

    private var rarityColor: Color {
        switch rarity.lowercased() {
        case "common":
            return .gray
        case "uncommon":
            return .green
        case "rare":
            return .blue
        case "epic":
            return .purple
        case "legendary":
            return .orange
        default:
            return .gray
        }
    }

    var body: some View {
        Button(action: { onTap?() }) {
            VStack(spacing: 12) {
                // Badge Icon
                ZStack {
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [rarityColor.opacity(0.8), rarityColor.opacity(0.4)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 80, height: 80)
                        .overlay(
                            Circle()
                                .stroke(rarityColor, lineWidth: 3)
                        )

                    Image(systemName: iconName)
                        .font(.title)
                        .foregroundColor(.white)
                }
                .grayscale(isEarned ? 0 : 1)
                .opacity(isEarned ? 1 : 0.5)

                // Badge Info
                VStack(spacing: 4) {
                    Text(title)
                        .font(.headline)
                        .fontWeight(.bold)
                        .foregroundColor(.primary)
                        .multilineTextAlignment(.center)

                    Text(description)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .lineLimit(2)

                    // Rarity indicator
                    Text(rarity.uppercased())
                        .font(.caption2)
                        .fontWeight(.bold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(rarityColor.opacity(0.2))
                        .foregroundColor(rarityColor)
                        .cornerRadius(4)
                }
            }
            .padding()
            .frame(width: 140, height: 180)
            .background(Color(.systemBackground))
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(rarityColor.opacity(0.3), lineWidth: 1)
            )
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Lyo Stats Card
struct LyoStatsCard: View {
    let title: String
    let value: String
    let subtitle: String?
    let iconName: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: iconName)
                    .font(.title2)
                    .foregroundColor(color)

                Spacer()

                Text(title)
                    .font(.headline)
                    .foregroundColor(.primary)
            }

            Text(value)
                .font(.title)
                .fontWeight(.bold)
                .foregroundColor(.primary)

            if let subtitle = subtitle {
                Text(subtitle)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color(.systemGray5), lineWidth: 1)
        )
    }
}