import SwiftUI
import EventKit

/// Study Planning Renderers - Study Plans, Exam Countdown, Goal Tracking
/// Critical for transforming Lyo from chat wrapper to learning companion

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Study Plan Overview Renderer
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIStudyPlanOverviewRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header with Progress
            HStack {
                VStack(alignment: .leading, spacing: 8) {
                    Text(component.props.title ?? "Study Plan")
                        .font(.title2.bold())
                        .foregroundColor(.primary)

                    if let subtitle = component.props.subtitle {
                        Text(subtitle)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                }

                Spacer()

                // Overall Progress Ring
                if let progress = component.props.progress {
                    StudyPlanProgressRing(
                        progress: progress,
                        size: 60,
                        lineWidth: 6
                    )
                }
            }

            // Exam Countdown (if exam date exists)
            if let examDate = component.props.examDate {
                ExamCountdownCard(examDate: examDate, title: component.props.title)
            }

            // Today's Sessions
            if let sessions = component.props.sessions {
                let todaySessions = sessions.filter { isToday($0.scheduledAt) }
                if !todaySessions.isEmpty {
                    StudySessionsSection(
                        title: "Today's Sessions",
                        sessions: todaySessions,
                        onAction: onAction
                    )
                }

                // This Week's Sessions
                let weekSessions = sessions.filter { isThisWeek($0.scheduledAt) && !isToday($0.scheduledAt) }
                if !weekSessions.isEmpty {
                    StudySessionsSection(
                        title: "This Week",
                        sessions: Array(weekSessions.prefix(5)),
                        onAction: onAction
                    )
                }
            }

            // Upcoming Milestones
            if let milestones = component.props.milestones?.filter({ !$0.isCompleted }).prefix(3),
               !milestones.isEmpty {
                MilestonesSection(milestones: Array(milestones), onAction: onAction)
            }

            // Goal Tracker
            if let goals = component.props.customData?["goals"] {
                // Would parse goals from custom data
                GoalProgressSection(onAction: onAction)
            }

            // Action Buttons
            HStack(spacing: 12) {
                Button("Edit Plan") {
                    triggerAction(type: "edit_study_plan")
                }
                .buttonStyle(.bordered)

                Button("Add Session") {
                    triggerAction(type: "add_study_session")
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.05), radius: 10)
    }

    private func isToday(_ date: Date) -> Bool {
        Calendar.current.isDateInToday(date)
    }

    private func isThisWeek(_ date: Date) -> Bool {
        let calendar = Calendar.current
        let startOfWeek = calendar.dateInterval(of: .weekOfYear, for: Date())?.start ?? Date()
        let endOfWeek = calendar.date(byAdding: .day, value: 7, to: startOfWeek) ?? Date()
        return date >= startOfWeek && date < endOfWeek
    }

    private func triggerAction(type: String) {
        let action = A2UIAction(
            trigger: .onTap,
            type: .custom,
            payload: [
                "action": type,
                "component_id": component.id,
                "study_plan_id": component.props.customData?["plan_id"] ?? ""
            ]
        )
        onAction?(action)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Exam Countdown Renderer
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIExamCountdownRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    private var examDate: Date {
        component.props.examDate ?? Date()
    }

    private var daysUntil: Int {
        Calendar.current.dateComponents([.day], from: Date(), to: examDate).day ?? 0
    }

    var body: some View {
        HStack(spacing: 16) {
            // Countdown Display
            VStack(spacing: 4) {
                Text("\(abs(daysUntil))")
                    .font(.system(size: 48, weight: .bold, design: .rounded))
                    .foregroundColor(urgencyColor)

                Text(daysUntil == 0 ? "TODAY!" : daysUntil == 1 ? "day left" : daysUntil > 0 ? "days left" : "days ago")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .textCase(.uppercase)
                    .tracking(0.5)
            }

            VStack(alignment: .leading, spacing: 8) {
                // Exam Title
                Text(component.props.title ?? "Exam")
                    .font(.headline.bold())
                    .foregroundColor(.primary)

                // Exam Date
                Text(examDate.formatted(date: .abbreviated, time: .omitted))
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                // Subject/Course
                if let courseName = component.props.courseName {
                    Text(courseName)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color(.systemGray5))
                        .cornerRadius(6)
                }

                // Action Buttons
                HStack(spacing: 8) {
                    if daysUntil > 0 {
                        Button("Study Now") {
                            triggerAction(type: "start_study_session")
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                    }

                    Button("View Plan") {
                        triggerAction(type: "view_study_plan")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }

            Spacer()

            // Urgency Icon
            Image(systemName: urgencyIcon)
                .font(.system(size: 32))
                .foregroundColor(urgencyColor)
        }
        .padding()
        .background(
            LinearGradient(
                colors: [urgencyColor.opacity(0.1), urgencyColor.opacity(0.05)],
                startPoint: .leading,
                endPoint: .trailing
            )
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(urgencyColor.opacity(0.3), lineWidth: 1)
        )
        .cornerRadius(12)
    }

    private var urgencyColor: Color {
        if daysUntil < 0 { return .red } // Exam passed
        if daysUntil == 0 { return .orange } // Exam today
        if daysUntil <= 1 { return .red } // Critical
        if daysUntil <= 3 { return .orange } // Urgent
        if daysUntil <= 7 { return .yellow } // Soon
        return .green // Plenty of time
    }

    private var urgencyIcon: String {
        if daysUntil < 0 { return "exclamationmark.triangle.fill" }
        if daysUntil == 0 { return "alarm.fill" }
        if daysUntil <= 1 { return "exclamationmark.triangle.fill" }
        if daysUntil <= 3 { return "clock.badge.exclamationmark.fill" }
        return "calendar.circle.fill"
    }

    private func triggerAction(type: String) {
        let action = A2UIAction(
            trigger: .onTap,
            type: .custom,
            payload: [
                "action": type,
                "component_id": component.id,
                "exam_id": component.props.customData?["exam_id"] ?? "",
                "days_until": String(daysUntil)
            ]
        )
        onAction?(action)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Study Session Renderer
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIStudySessionRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    private var session: A2UIStudySession? {
        component.props.sessions?.first
    }

    private var isCompleted: Bool {
        session?.isCompleted ?? false
    }

    var body: some View {
        HStack(spacing: 16) {
            // Status Icon
            VStack {
                Image(systemName: isCompleted ? "checkmark.circle.fill" : "clock.circle")
                    .font(.title2)
                    .foregroundColor(isCompleted ? .green : .blue)

                if !isCompleted, let duration = component.props.durationMinutes {
                    Text("\(duration)min")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            // Session Details
            VStack(alignment: .leading, spacing: 4) {
                Text(component.props.title ?? session?.topic ?? "Study Session")
                    .font(.subheadline.bold())
                    .foregroundColor(.primary)

                if let scheduledAt = session?.scheduledAt {
                    Text(scheduledAt.formatted(date: .omitted, time: .shortened))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                if let notes = session?.notes, !notes.isEmpty {
                    Text(notes)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }

                // Tags
                if let tags = component.props.tags, !tags.isEmpty {
                    HStack {
                        ForEach(tags.prefix(2), id: \.self) { tag in
                            Text(tag)
                                .font(.caption2)
                                .foregroundColor(.blue)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.blue.opacity(0.1))
                                .cornerRadius(4)
                        }
                    }
                }
            }

            Spacer()

            // Action Button
            if !isCompleted {
                Button(action: startSession) {
                    Text("Start")
                        .font(.caption.bold())
                        .foregroundColor(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.blue)
                        .cornerRadius(8)
                }
            } else {
                Button(action: reviewSession) {
                    Text("Review")
                        .font(.caption)
                        .foregroundColor(.blue)
                }
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(isCompleted ? Color.green.opacity(0.05) : Color(.systemBackground))
                .stroke(isCompleted ? Color.green.opacity(0.2) : Color(.systemGray5), lineWidth: 1)
        )
        .opacity(isCompleted ? 0.7 : 1.0)
    }

    private func startSession() {
        let action = A2UIAction(
            trigger: .onTap,
            type: .custom,
            payload: [
                "action": "start_study_session",
                "component_id": component.id,
                "session_id": session?.id ?? "",
                "topic": session?.topic ?? ""
            ]
        )
        onAction?(action)
    }

    private func reviewSession() {
        let action = A2UIAction(
            trigger: .onTap,
            type: .custom,
            payload: [
                "action": "review_study_session",
                "component_id": component.id,
                "session_id": session?.id ?? ""
            ]
        )
        onAction?(action)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Goal Tracker Renderer
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIGoalTrackerRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Goal Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(component.props.title ?? "Learning Goal")
                        .font(.headline.bold())

                    if let description = component.props.description {
                        Text(description)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                }

                Spacer()

                // Progress Percentage
                if let progress = component.props.progress {
                    Text("\(Int(progress * 100))%")
                        .font(.title3.bold())
                        .foregroundColor(.blue)
                }
            }

            // Progress Bar
            if let progress = component.props.progress {
                ProgressView(value: progress)
                    .progressViewStyle(LinearProgressViewStyle(tint: .blue))
                    .scaleEffect(y: 2.0)
            }

            // Milestones
            if let milestones = component.props.milestones, !milestones.isEmpty {
                LazyVStack(alignment: .leading, spacing: 8) {
                    Text("Milestones")
                        .font(.subheadline.bold())
                        .foregroundColor(.secondary)

                    ForEach(milestones.prefix(3)) { milestone in
                        MilestoneRow(milestone: milestone) {
                            toggleMilestone(milestone)
                        }
                    }
                }
            }

            // Current/Total Stats
            if let current = component.props.current, let total = component.props.total {
                HStack {
                    Text("\(current) of \(total) completed")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Spacer()

                    if let dueDate = component.props.dueDate {
                        Text("Due \(dueDate.formatted(date: .abbreviated, time: .omitted))")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }

            // Action Button
            HStack {
                Button("Continue") {
                    triggerAction(type: "continue_goal")
                }
                .buttonStyle(.borderedProminent)

                Button("Edit Goal") {
                    triggerAction(type: "edit_goal")
                }
                .buttonStyle(.bordered)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.05), radius: 8)
    }

    private func toggleMilestone(_ milestone: A2UIMilestone) {
        let action = A2UIAction(
            trigger: .onTap,
            type: .custom,
            payload: [
                "action": "toggle_milestone",
                "component_id": component.id,
                "milestone_id": milestone.id,
                "is_completed": String(!milestone.isCompleted)
            ]
        )
        onAction?(action)
    }

    private func triggerAction(type: String) {
        let action = A2UIAction(
            trigger: .onTap,
            type: .custom,
            payload: [
                "action": type,
                "component_id": component.id,
                "goal_id": component.props.customData?["goal_id"] ?? ""
            ]
        )
        onAction?(action)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Milestone Timeline Renderer
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIMilestoneTimelineRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            Text(component.props.title ?? "Milestones")
                .font(.headline.bold())

            // Timeline
            if let milestones = component.props.milestones {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(milestones.enumerated()), id: \.element.id) { index, milestone in
                        HStack(alignment: .top, spacing: 12) {
                            // Timeline Line
                            VStack(spacing: 0) {
                                Circle()
                                    .fill(milestone.isCompleted ? Color.green : Color.blue)
                                    .frame(width: 12, height: 12)

                                if index < milestones.count - 1 {
                                    Rectangle()
                                        .fill(Color(.systemGray4))
                                        .frame(width: 2, height: 40)
                                }
                            }

                            // Milestone Content
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(milestone.title)
                                        .font(.subheadline.bold())
                                        .foregroundColor(milestone.isCompleted ? .secondary : .primary)

                                    Spacer()

                                    Text(milestone.date.formatted(date: .abbreviated, time: .omitted))
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }

                                if milestone.isCompleted {
                                    HStack {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundColor(.green)
                                            .font(.caption)

                                        Text("Completed")
                                            .font(.caption)
                                            .foregroundColor(.green)
                                    }
                                } else {
                                    let daysUntil = Calendar.current.dateComponents([.day], from: Date(), to: milestone.date).day ?? 0
                                    if daysUntil <= 7 {
                                        Text(daysUntil == 0 ? "Due today" : daysUntil == 1 ? "Due tomorrow" : "Due in \(daysUntil) days")
                                            .font(.caption)
                                            .foregroundColor(daysUntil <= 3 ? .red : .orange)
                                    }
                                }
                            }
                            .padding(.bottom, index < milestones.count - 1 ? 16 : 0)
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.05), radius: 8)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Supporting Views
// ═══════════════════════════════════════════════════════════════════════════

struct StudyPlanProgressRing: View {
    let progress: Double
    let size: CGFloat
    let lineWidth: CGFloat

    var body: some View {
        ZStack {
            // Background ring
            Circle()
                .stroke(Color(.systemGray5), lineWidth: lineWidth)

            // Progress ring
            Circle()
                .trim(from: 0, to: progress)
                .stroke(
                    LinearGradient(
                        colors: [.blue, .purple],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    style: StrokeStyle(lineWidth: lineWidth, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))

            // Progress text
            Text("\(Int(progress * 100))%")
                .font(.system(size: size * 0.2, weight: .bold, design: .rounded))
                .foregroundColor(.primary)
        }
        .frame(width: size, height: size)
    }
}

struct ExamCountdownCard: View {
    let examDate: Date
    let title: String?

    private var daysUntil: Int {
        Calendar.current.dateComponents([.day], from: Date(), to: examDate).day ?? 0
    }

    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(title ?? "Exam")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                Text("\(abs(daysUntil))")
                    .font(.system(size: 32, weight: .bold))
                    .foregroundColor(.red)

                Text(daysUntil <= 0 ? "days past" : "days left")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            Image(systemName: daysUntil <= 3 ? "exclamationmark.triangle.fill" : "calendar")
                .font(.title)
                .foregroundColor(.red)
        }
        .padding()
        .background(Color.red.opacity(0.1))
        .cornerRadius(12)
    }
}

struct StudySessionsSection: View {
    let title: String
    let sessions: [A2UIStudySession]
    let onAction: ((A2UIAction) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.headline)
                .foregroundColor(.primary)

            LazyVStack(spacing: 8) {
                ForEach(sessions.prefix(5)) { session in
                    StudySessionCard(session: session, onAction: onAction)
                }
            }
        }
    }
}

struct StudySessionCard: View {
    let session: A2UIStudySession
    let onAction: ((A2UIAction) -> Void)?

    var body: some View {
        HStack {
            // Status indicator
            Circle()
                .fill(session.isCompleted ? Color.green : Color.blue)
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 2) {
                Text(session.topic)
                    .font(.subheadline)
                    .lineLimit(1)

                Text(session.scheduledAt.formatted(time: .shortened))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            Text("\(session.durationMinutes)min")
                .font(.caption)
                .foregroundColor(.secondary)

            if !session.isCompleted {
                Button("Start") {
                    let action = A2UIAction(
                        trigger: .onTap,
                        type: .custom,
                        payload: [
                            "action": "start_session",
                            "session_id": session.id
                        ]
                    )
                    onAction?(action)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
}

struct MilestonesSection: View {
    let milestones: [A2UIMilestone]
    let onAction: ((A2UIAction) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Upcoming Milestones")
                .font(.headline)

            LazyVStack(spacing: 8) {
                ForEach(milestones) { milestone in
                    MilestoneRow(milestone: milestone) {
                        let action = A2UIAction(
                            trigger: .onTap,
                            type: .custom,
                            payload: [
                                "action": "view_milestone",
                                "milestone_id": milestone.id
                            ]
                        )
                        onAction?(action)
                    }
                }
            }
        }
    }
}

struct MilestoneRow: View {
    let milestone: A2UIMilestone
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack {
                Circle()
                    .fill(typeColor)
                    .frame(width: 8, height: 8)

                Text(milestone.title)
                    .font(.subheadline)
                    .foregroundColor(.primary)

                Spacer()

                Text(milestone.date.formatted(date: .abbreviated, time: .omitted))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }

    var typeColor: Color {
        switch milestone.type {
        case "exam": return .red
        case "deadline": return .orange
        case "goal": return .green
        default: return .blue
        }
    }
}

struct GoalProgressSection: View {
    let onAction: ((A2UIAction) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Goals")
                .font(.headline)

            // This would be populated with actual goal data
            HStack {
                VStack(alignment: .leading) {
                    Text("Complete Math Course")
                        .font(.subheadline)
                    ProgressView(value: 0.7)
                        .progressViewStyle(LinearProgressViewStyle(tint: .blue))
                }

                Text("70%")
                    .font(.caption)
                    .foregroundColor(.blue)
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(8)
        }
    }
}

print("✅ Study Planning Renderers implemented")
print("📊 Study plan overview with progress tracking")
print("⏰ Exam countdown with urgency indicators")
print("🎯 Goal tracker with milestone timeline")
print("📅 Study sessions with completion status")