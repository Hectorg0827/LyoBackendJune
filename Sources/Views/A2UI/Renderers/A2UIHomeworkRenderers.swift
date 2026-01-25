import SwiftUI

struct A2UIHomeworkCardRenderer: View {
    let component: A2UIComponent

    private var title: String {
        component.props["title"]?.stringValue ?? ""
    }

    private var subject: String {
        component.props["subject"]?.stringValue ?? ""
    }

    private var dueDate: String {
        component.props["due_date"]?.stringValue ?? ""
    }

    private var progress: Double {
        component.props["progress"]?.doubleValue ?? 0.0
    }

    private var difficulty: String {
        component.props["difficulty"]?.stringValue ?? "medium"
    }

    private var estimatedTime: Int {
        component.props["estimated_time"]?.intValue ?? 0
    }

    private var status: String {
        component.props["status"]?.stringValue ?? "pending"
    }

    private var priority: String {
        component.props["priority"]?.stringValue ?? "medium"
    }

    private var statusColor: Color {
        switch status {
        case "completed": return .green
        case "in_progress": return .blue
        case "overdue": return .red
        case "pending": return .orange
        default: return .gray
        }
    }

    private var priorityColor: Color {
        switch priority {
        case "high": return .red
        case "medium": return .orange
        case "low": return .green
        default: return .gray
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.headline)
                        .foregroundColor(.primary)
                        .lineLimit(2)

                    Text(subject)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(priorityColor)
                            .frame(width: 6, height: 6)
                        Text(priority.capitalized)
                            .font(.caption2)
                            .foregroundColor(priorityColor)
                    }

                    Text(status.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(statusColor.opacity(0.2))
                        .foregroundColor(statusColor)
                        .cornerRadius(4)
                }
            }

            if progress > 0 {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Progress")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        Spacer()

                        Text("\(Int(progress * 100))%")
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundColor(.primary)
                    }

                    ProgressView(value: progress)
                        .progressViewStyle(LinearProgressViewStyle(tint: statusColor))
                }
            }

            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Due: \(dueDate)")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    if estimatedTime > 0 {
                        Text("\(estimatedTime) min estimated")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }

                Spacer()

                Button(status == "completed" ? "Review" : "Continue") {
                    A2UIActionHandler.shared.handleAction(
                        type: .navigate,
                        payload: ["homework_id": component.props["homework_id"]?.stringValue ?? ""]
                    )
                }
                .font(.caption)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(statusColor.opacity(0.1))
                .foregroundColor(statusColor)
                .cornerRadius(6)
            }
        }
        .padding()
        .background(Color.gray.opacity(0.05))
        .cornerRadius(8)
    }
}

struct A2UIHomeworkStepRenderer: View {
    let component: A2UIComponent

    private var stepNumber: Int {
        component.props["step_number"]?.intValue ?? 1
    }

    private var instruction: String {
        component.props["instruction"]?.stringValue ?? ""
    }

    private var hint: String {
        component.props["hint"]?.stringValue ?? ""
    }

    private var completed: Bool {
        component.props["completed"]?.boolValue ?? false
    }

    private var hasAttachment: Bool {
        component.props["has_attachment"]?.boolValue ?? false
    }

    private var attachmentType: String {
        component.props["attachment_type"]?.stringValue ?? ""
    }

    @State private var showHint = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                HStack(spacing: 8) {
                    ZStack {
                        Circle()
                            .fill(completed ? Color.green : Color.blue.opacity(0.2))
                            .frame(width: 24, height: 24)

                        if completed {
                            Image(systemName: "checkmark")
                                .font(.caption)
                                .foregroundColor(.white)
                        } else {
                            Text("\(stepNumber)")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundColor(.blue)
                        }
                    }

                    Text("Step \(stepNumber)")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundColor(completed ? .green : .primary)
                }

                Spacer()

                if !hint.isEmpty {
                    Button(action: { showHint.toggle() }) {
                        Image(systemName: showHint ? "lightbulb.fill" : "lightbulb")
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                }
            }

            Text(instruction)
                .font(.body)
                .foregroundColor(.primary)
                .fixedSize(horizontal: false, vertical: true)

            if showHint && !hint.isEmpty {
                HStack {
                    Image(systemName: "lightbulb.fill")
                        .font(.caption)
                        .foregroundColor(.orange)

                    Text(hint)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color.orange.opacity(0.1))
                .cornerRadius(6)
            }

            if hasAttachment {
                Button(action: {
                    A2UIActionHandler.shared.handleAction(
                        type: .custom,
                        payload: [
                            "action": "view_attachment",
                            "step_id": component.props["step_id"]?.stringValue ?? "",
                            "attachment_type": attachmentType
                        ]
                    )
                }) {
                    HStack {
                        Image(systemName: attachmentIcon(for: attachmentType))
                            .font(.caption)

                        Text("View \(attachmentType.capitalized)")
                            .font(.caption)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.blue.opacity(0.1))
                    .foregroundColor(.blue)
                    .cornerRadius(4)
                }
            }

            if !completed {
                Button("Mark Complete") {
                    A2UIActionHandler.shared.handleAction(
                        type: .custom,
                        payload: [
                            "action": "complete_step",
                            "step_id": component.props["step_id"]?.stringValue ?? ""
                        ]
                    )
                }
                .font(.caption)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.green.opacity(0.1))
                .foregroundColor(.green)
                .cornerRadius(6)
            }
        }
        .padding()
        .background(completed ? Color.green.opacity(0.05) : Color.gray.opacity(0.05))
        .cornerRadius(8)
    }

    private func attachmentIcon(for type: String) -> String {
        switch type.lowercased() {
        case "image": return "photo"
        case "video": return "play.rectangle"
        case "document": return "doc.text"
        case "link": return "link"
        default: return "paperclip"
        }
    }
}

struct A2UIHomeworkProgressRenderer: View {
    let component: A2UIComponent

    private var totalSteps: Int {
        component.props["total_steps"]?.intValue ?? 0
    }

    private var completedSteps: Int {
        component.props["completed_steps"]?.intValue ?? 0
    }

    private var currentStep: Int {
        component.props["current_step"]?.intValue ?? 1
    }

    private var timeSpent: Int {
        component.props["time_spent"]?.intValue ?? 0
    }

    private var estimatedTimeRemaining: Int {
        component.props["estimated_time_remaining"]?.intValue ?? 0
    }

    private var progressPercentage: Double {
        guard totalSteps > 0 else { return 0 }
        return Double(completedSteps) / Double(totalSteps)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Progress Overview")
                .font(.headline)
                .fontWeight(.semibold)

            VStack(spacing: 12) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Steps Completed")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        Text("\(completedSteps)/\(totalSteps)")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundColor(.primary)
                    }

                    Spacer()

                    VStack(alignment: .trailing, spacing: 2) {
                        Text("Current Step")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        Text("#\(currentStep)")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundColor(.blue)
                    }
                }

                ProgressView(value: progressPercentage)
                    .progressViewStyle(LinearProgressViewStyle(tint: .green))
                    .scaleEffect(x: 1, y: 2, anchor: .center)

                HStack {
                    Text("\(Int(progressPercentage * 100))% Complete")
                        .font(.caption)
                        .foregroundColor(.green)

                    Spacer()

                    if progressPercentage < 1.0 {
                        Text("\(estimatedTimeRemaining) min remaining")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding()
            .background(Color.gray.opacity(0.05))
            .cornerRadius(8)

            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Time Spent")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Text(formatTime(timeSpent))
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.primary)
                }

                Spacer()

                if progressPercentage >= 1.0 {
                    Button("Submit Homework") {
                        A2UIActionHandler.shared.handleAction(
                            type: .custom,
                            payload: [
                                "action": "submit_homework",
                                "homework_id": component.props["homework_id"]?.stringValue ?? ""
                            ]
                        )
                    }
                    .font(.subheadline)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(Color.green)
                    .foregroundColor(.white)
                    .cornerRadius(8)
                } else {
                    Button("Take a Break") {
                        A2UIActionHandler.shared.handleAction(
                            type: .custom,
                            payload: [
                                "action": "save_progress",
                                "homework_id": component.props["homework_id"]?.stringValue ?? ""
                            ]
                        )
                    }
                    .font(.caption)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.orange.opacity(0.1))
                    .foregroundColor(.orange)
                    .cornerRadius(6)
                }
            }
        }
        .padding()
    }

    private func formatTime(_ minutes: Int) -> String {
        let hours = minutes / 60
        let remainingMinutes = minutes % 60

        if hours > 0 {
            return "\(hours)h \(remainingMinutes)m"
        } else {
            return "\(remainingMinutes)m"
        }
    }
}

struct A2UIHomeworkListRenderer: View {
    let component: A2UIComponent

    private var assignments: [HomeworkAssignment] {
        guard let assignmentsArray = component.props["assignments"]?.arrayValue else { return [] }
        return assignmentsArray.compactMap { value in
            guard let dict = value.dictionaryValue else { return nil }
            return HomeworkAssignment(
                id: dict["id"]?.stringValue ?? "",
                title: dict["title"]?.stringValue ?? "",
                subject: dict["subject"]?.stringValue ?? "",
                dueDate: dict["due_date"]?.stringValue ?? "",
                status: dict["status"]?.stringValue ?? "pending",
                priority: dict["priority"]?.stringValue ?? "medium",
                progress: dict["progress"]?.doubleValue ?? 0.0
            )
        }
    }

    private var filterBy: String {
        component.props["filter_by"]?.stringValue ?? "all"
    }

    private var sortBy: String {
        component.props["sort_by"]?.stringValue ?? "due_date"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Homework Assignments")
                    .font(.title2)
                    .fontWeight(.semibold)

                Spacer()

                Menu("Filter") {
                    Button("All") {
                        A2UIActionHandler.shared.handleAction(
                            type: .custom,
                            payload: ["action": "filter_homework", "filter": "all"]
                        )
                    }
                    Button("Pending") {
                        A2UIActionHandler.shared.handleAction(
                            type: .custom,
                            payload: ["action": "filter_homework", "filter": "pending"]
                        )
                    }
                    Button("In Progress") {
                        A2UIActionHandler.shared.handleAction(
                            type: .custom,
                            payload: ["action": "filter_homework", "filter": "in_progress"]
                        )
                    }
                    Button("Completed") {
                        A2UIActionHandler.shared.handleAction(
                            type: .custom,
                            payload: ["action": "filter_homework", "filter": "completed"]
                        )
                    }
                    Button("Overdue") {
                        A2UIActionHandler.shared.handleAction(
                            type: .custom,
                            payload: ["action": "filter_homework", "filter": "overdue"]
                        )
                    }
                }
                .font(.caption)
            }

            if !assignments.isEmpty {
                LazyVStack(spacing: 12) {
                    ForEach(filteredAssignments, id: \.id) { assignment in
                        HomeworkAssignmentRow(assignment: assignment)
                    }
                }
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "book.closed")
                        .font(.largeTitle)
                        .foregroundColor(.secondary)

                    Text("No assignments found")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 32)
            }
        }
        .padding()
    }

    private var filteredAssignments: [HomeworkAssignment] {
        let filtered = filterBy == "all" ? assignments : assignments.filter { $0.status == filterBy }

        switch sortBy {
        case "priority":
            return filtered.sorted { assignment1, assignment2 in
                let priority1 = priorityValue(assignment1.priority)
                let priority2 = priorityValue(assignment2.priority)
                return priority1 > priority2
            }
        case "subject":
            return filtered.sorted { $0.subject < $1.subject }
        default: // due_date
            return filtered // Assume already sorted by due date from backend
        }
    }

    private func priorityValue(_ priority: String) -> Int {
        switch priority {
        case "high": return 3
        case "medium": return 2
        case "low": return 1
        default: return 0
        }
    }
}

private struct HomeworkAssignmentRow: View {
    let assignment: HomeworkAssignment

    private var statusColor: Color {
        switch assignment.status {
        case "completed": return .green
        case "in_progress": return .blue
        case "overdue": return .red
        case "pending": return .orange
        default: return .gray
        }
    }

    var body: some View {
        Button(action: {
            A2UIActionHandler.shared.handleAction(
                type: .navigate,
                payload: ["homework_id": assignment.id]
            )
        }) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(assignment.title)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.primary)
                        .multilineTextAlignment(.leading)

                    HStack {
                        Text(assignment.subject)
                            .font(.caption)
                            .foregroundColor(.secondary)

                        Text("•")
                            .foregroundColor(.secondary)

                        Text("Due: \(assignment.dueDate)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    if assignment.progress > 0 && assignment.status != "completed" {
                        ProgressView(value: assignment.progress)
                            .progressViewStyle(LinearProgressViewStyle(tint: statusColor))
                            .frame(height: 4)
                    }
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    Text(assignment.status.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(statusColor.opacity(0.2))
                        .foregroundColor(statusColor)
                        .cornerRadius(4)

                    if assignment.progress > 0 && assignment.status != "completed" {
                        Text("\(Int(assignment.progress * 100))%")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .buttonStyle(PlainButtonStyle())
        .padding()
        .background(Color.gray.opacity(0.05))
        .cornerRadius(8)
    }
}

private struct HomeworkAssignment {
    let id: String
    let title: String
    let subject: String
    let dueDate: String
    let status: String
    let priority: String
    let progress: Double
}