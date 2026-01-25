import SwiftUI
#if canImport(Charts)
import Charts
#endif

struct A2UIMistakeCardRenderer: View {
    let component: A2UIComponent

    private var mistakeType: String {
        component.props["mistake_type"]?.stringValue ?? ""
    }

    private var subject: String {
        component.props["subject"]?.stringValue ?? ""
    }

    private var frequency: Int {
        component.props["frequency"]?.intValue ?? 0
    }

    private var lastOccurrence: String {
        component.props["last_occurrence"]?.stringValue ?? ""
    }

    private var difficulty: String {
        component.props["difficulty"]?.stringValue ?? "medium"
    }

    private var remediation: String {
        component.props["remediation"]?.stringValue ?? ""
    }

    private var difficultyColor: Color {
        switch difficulty {
        case "easy": return .green
        case "medium": return .orange
        case "hard": return .red
        default: return .gray
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(mistakeType)
                        .font(.headline)
                        .foregroundColor(.primary)

                    Text(subject)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(difficultyColor)
                            .frame(width: 8, height: 8)
                        Text(difficulty.capitalized)
                            .font(.caption)
                            .foregroundColor(difficultyColor)
                    }

                    Text("\(frequency)x")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            if !remediation.isEmpty {
                Text(remediation)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.gray.opacity(0.1))
                    .cornerRadius(4)
            }

            HStack {
                Text("Last: \(lastOccurrence)")
                    .font(.caption2)
                    .foregroundColor(.secondary)

                Spacer()

                Button("Practice") {
                    A2UIActionHandler.shared.handleAction(
                        type: .navigate,
                        payload: ["mistake_id": component.props["mistake_id"]?.stringValue ?? ""]
                    )
                }
                .font(.caption)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.blue.opacity(0.1))
                .foregroundColor(.blue)
                .cornerRadius(4)
            }
        }
        .padding()
        .background(Color.gray.opacity(0.05))
        .cornerRadius(8)
    }
}

struct A2UIMistakePatternAnalysisRenderer: View {
    let component: A2UIComponent

    private var patterns: [MistakePattern] {
        guard let patternsArray = component.props["patterns"]?.arrayValue else { return [] }
        return patternsArray.compactMap { value in
            guard let dict = value.dictionaryValue else { return nil }
            return MistakePattern(
                type: dict["type"]?.stringValue ?? "",
                frequency: dict["frequency"]?.intValue ?? 0,
                trend: dict["trend"]?.stringValue ?? "stable",
                subjects: dict["subjects"]?.arrayValue?.compactMap { $0.stringValue } ?? []
            )
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Mistake Patterns")
                .font(.title2)
                .fontWeight(.semibold)

            if !patterns.isEmpty {
                chartView(for: patterns)

                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(patterns.enumerated()), id: \.offset) { index, pattern in
                        HStack {
                            Circle()
                                .fill(trendColor(pattern.trend))
                                .frame(width: 8, height: 8)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(pattern.type)
                                    .font(.subheadline)
                                    .fontWeight(.medium)

                                HStack {
                                    Text("\(pattern.frequency) occurrences")
                                        .font(.caption)
                                        .foregroundColor(.secondary)

                                    Text("•")
                                        .foregroundColor(.secondary)

                                    Text(trendText(pattern.trend))
                                        .font(.caption)
                                        .foregroundColor(trendColor(pattern.trend))
                                }

                                if !pattern.subjects.isEmpty {
                                    Text("Subjects: \(pattern.subjects.joined(separator: ", "))")
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                }
                            }

                            Spacer()
                        }
                        .padding(.vertical, 4)
                    }
                }
            } else {
                Text("No patterns detected yet")
                    .foregroundColor(.secondary)
                    .padding()
            }
        }
        .padding()
    }

    @ViewBuilder
    private func chartView(for patterns: [MistakePattern]) -> some View {
        #if canImport(Charts)
        if #available(iOS 16.0, *) {
            Chart {
                ForEach(Array(patterns.enumerated()), id: \.offset) { index, pattern in
                    BarMark(
                        x: .value("Pattern", pattern.type),
                        y: .value("Frequency", pattern.frequency)
                    )
                    .foregroundStyle(trendColor(pattern.trend))
                    .opacity(0.8)
                }
            }
            .frame(height: 200)
            .chartYAxis {
                AxisMarks(position: .leading) { _ in
                    AxisValueLabel()
                    AxisGridLine()
                    AxisTick()
                }
            }
        } else {
            textBasedChart(for: patterns)
        }
        #else
        textBasedChart(for: patterns)
        #endif
    }

    @ViewBuilder
    private func textBasedChart(for patterns: [MistakePattern]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Pattern Frequency (Chart visualization requires iOS 16+)")
                .font(.caption)
                .foregroundColor(.secondary)

            ForEach(Array(patterns.enumerated()), id: \.offset) { index, pattern in
                HStack {
                    Text(pattern.type)
                        .font(.caption)
                        .frame(width: 80, alignment: .leading)

                    let maxFreq = patterns.map { $0.frequency }.max() ?? 1
                    let barWidth = CGFloat(pattern.frequency) / CGFloat(maxFreq) * 150

                    RoundedRectangle(cornerRadius: 2)
                        .fill(trendColor(pattern.trend))
                        .frame(width: barWidth, height: 12)

                    Text("\(pattern.frequency)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
        .background(Color.gray.opacity(0.1))
        .cornerRadius(8)
    }

    private func trendColor(_ trend: String) -> Color {
        switch trend {
        case "improving": return .green
        case "worsening": return .red
        case "stable": return .blue
        default: return .gray
        }
    }

    private func trendText(_ trend: String) -> String {
        switch trend {
        case "improving": return "↗ Improving"
        case "worsening": return "↘ Worsening"
        case "stable": return "→ Stable"
        default: return trend.capitalized
        }
    }
}

struct A2UIMistakeRemediationRenderer: View {
    let component: A2UIComponent

    private var mistakeId: String {
        component.props["mistake_id"]?.stringValue ?? ""
    }

    private var exercises: [RemediationExercise] {
        guard let exercisesArray = component.props["exercises"]?.arrayValue else { return [] }
        return exercisesArray.compactMap { value in
            guard let dict = value.dictionaryValue else { return nil }
            return RemediationExercise(
                id: dict["id"]?.stringValue ?? "",
                title: dict["title"]?.stringValue ?? "",
                difficulty: dict["difficulty"]?.stringValue ?? "medium",
                estimatedTime: dict["estimated_time"]?.intValue ?? 5,
                completed: dict["completed"]?.boolValue ?? false
            )
        }
    }

    private var explanation: String {
        component.props["explanation"]?.stringValue ?? ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Targeted Practice")
                .font(.title2)
                .fontWeight(.semibold)

            if !explanation.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Why this happens:")
                        .font(.headline)
                        .foregroundColor(.primary)

                    Text(explanation)
                        .font(.body)
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding()
                .background(Color.blue.opacity(0.1))
                .cornerRadius(8)
            }

            if !exercises.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Practice Exercises")
                        .font(.headline)

                    ForEach(Array(exercises.enumerated()), id: \.offset) { index, exercise in
                        HStack {
                            Button(action: {
                                A2UIActionHandler.shared.handleAction(
                                    type: .custom,
                                    payload: [
                                        "action": "start_exercise",
                                        "exercise_id": exercise.id,
                                        "mistake_id": mistakeId
                                    ]
                                )
                            }) {
                                HStack {
                                    Image(systemName: exercise.completed ? "checkmark.circle.fill" : "circle")
                                        .foregroundColor(exercise.completed ? .green : .gray)

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(exercise.title)
                                            .font(.subheadline)
                                            .fontWeight(.medium)
                                            .foregroundColor(.primary)

                                        HStack {
                                            Text("\(exercise.estimatedTime) min")
                                                .font(.caption)
                                                .foregroundColor(.secondary)

                                            Text("•")
                                                .foregroundColor(.secondary)

                                            Text(exercise.difficulty.capitalized)
                                                .font(.caption)
                                                .foregroundColor(difficultyColor(exercise.difficulty))
                                        }
                                    }

                                    Spacer()

                                    Image(systemName: "chevron.right")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                            .buttonStyle(PlainButtonStyle())
                        }
                        .padding()
                        .background(Color.gray.opacity(0.05))
                        .cornerRadius(8)
                    }
                }
            }
        }
        .padding()
    }

    private func difficultyColor(_ difficulty: String) -> Color {
        switch difficulty {
        case "easy": return .green
        case "medium": return .orange
        case "hard": return .red
        default: return .gray
        }
    }
}

struct A2UIMistakeProgressRenderer: View {
    let component: A2UIComponent

    private var totalMistakes: Int {
        component.props["total_mistakes"]?.intValue ?? 0
    }

    private var resolvedMistakes: Int {
        component.props["resolved_mistakes"]?.intValue ?? 0
    }

    private var improvementRate: Double {
        component.props["improvement_rate"]?.doubleValue ?? 0.0
    }

    private var weeklyData: [MistakeDataPoint] {
        guard let dataArray = component.props["weekly_data"]?.arrayValue else { return [] }
        return dataArray.compactMap { value in
            guard let dict = value.dictionaryValue else { return nil }
            return MistakeDataPoint(
                week: dict["week"]?.stringValue ?? "",
                count: dict["count"]?.intValue ?? 0
            )
        }
    }

    private var progressPercentage: Double {
        guard totalMistakes > 0 else { return 0 }
        return Double(resolvedMistakes) / Double(totalMistakes)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Progress Tracking")
                .font(.title2)
                .fontWeight(.semibold)

            VStack(spacing: 12) {
                HStack {
                    VStack(alignment: .leading) {
                        Text("Mistakes Resolved")
                            .font(.subheadline)
                            .foregroundColor(.secondary)

                        Text("\(resolvedMistakes)/\(totalMistakes)")
                            .font(.title)
                            .fontWeight(.bold)
                            .foregroundColor(.primary)
                    }

                    Spacer()

                    VStack(alignment: .trailing) {
                        Text("Improvement Rate")
                            .font(.subheadline)
                            .foregroundColor(.secondary)

                        Text("\(Int(improvementRate * 100))%")
                            .font(.title)
                            .fontWeight(.bold)
                            .foregroundColor(improvementRate > 0.5 ? .green : .orange)
                    }
                }

                ProgressView(value: progressPercentage)
                    .progressViewStyle(LinearProgressViewStyle(tint: .green))
                    .scaleEffect(x: 1, y: 2, anchor: .center)
            }
            .padding()
            .background(Color.gray.opacity(0.05))
            .cornerRadius(8)

            if !weeklyData.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Weekly Trend")
                        .font(.headline)

                    progressChartView(for: weeklyData)
                }
            }
        }
        .padding()
    }

    @ViewBuilder
    private func progressChartView(for data: [MistakeDataPoint]) -> some View {
        #if canImport(Charts)
        if #available(iOS 16.0, *) {
            Chart {
                ForEach(Array(data.enumerated()), id: \.offset) { index, dataPoint in
                    LineMark(
                        x: .value("Week", dataPoint.week),
                        y: .value("Mistakes", dataPoint.count)
                    )
                    .foregroundStyle(.red)
                    .interpolationMethod(.catmullRom)

                    PointMark(
                        x: .value("Week", dataPoint.week),
                        y: .value("Mistakes", dataPoint.count)
                    )
                    .foregroundStyle(.red)
                }
            }
            .frame(height: 150)
            .chartYAxis {
                AxisMarks(position: .leading) { _ in
                    AxisValueLabel()
                    AxisGridLine()
                    AxisTick()
                }
            }
        } else {
            textBasedProgressChart(for: data)
        }
        #else
        textBasedProgressChart(for: data)
        #endif
    }

    @ViewBuilder
    private func textBasedProgressChart(for data: [MistakeDataPoint]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Weekly Progress (Chart visualization requires iOS 16+)")
                .font(.caption)
                .foregroundColor(.secondary)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(Array(data.enumerated()), id: \.offset) { index, dataPoint in
                        VStack(spacing: 4) {
                            Text("\(dataPoint.count)")
                                .font(.caption2)
                                .fontWeight(.semibold)

                            let maxCount = data.map { $0.count }.max() ?? 1
                            let barHeight = CGFloat(dataPoint.count) / CGFloat(maxCount) * 60 + 10

                            RoundedRectangle(cornerRadius: 2)
                                .fill(.red)
                                .frame(width: 8, height: barHeight)

                            Text(dataPoint.week)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding(.horizontal)
            }
        }
        .padding()
        .background(Color.gray.opacity(0.1))
        .cornerRadius(8)
    }
}

private struct MistakePattern {
    let type: String
    let frequency: Int
    let trend: String
    let subjects: [String]
}

private struct RemediationExercise {
    let id: String
    let title: String
    let difficulty: String
    let estimatedTime: Int
    let completed: Bool
}

private struct MistakeDataPoint {
    let week: String
    let count: Int
}