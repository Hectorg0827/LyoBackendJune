import Foundation
import SwiftUI
import Combine
import os.log

// MARK: - A2UI Action Handler with Priority Queue
@MainActor
final class A2UIActionHandler: ObservableObject {
    static let shared = A2UIActionHandler()

    @Published var isProcessing = false
    @Published var lastActionResult: ActionResult?
    @Published var queuedActionsCount = 0
    @Published var highPriorityQueueCount = 0

    // Priority queue system
    private let highPriorityQueue = DispatchQueue(label: "a2ui.actions.high", qos: .userInteractive)
    private let backgroundQueue = DispatchQueue(label: "a2ui.actions.background", qos: .utility)
    private let defaultQueue = DispatchQueue(label: "a2ui.actions.default", qos: .userInitiated)

    // Action tracking
    private var activeActions: Set<String> = []
    private var queuedActions: [ActionQueueItem] = []
    private let maxQueueSize = 50
    private let logger = Logger(subsystem: "com.lyo.a2ui", category: "actions")

    private var cancellables = Set<AnyCancellable>()

    // Action result types
    enum ActionResult {
        case success(String)
        case failure(String)
        case navigation(String)
        case ui_update(A2UIComponent)
    }

    // Action types for routing
    enum ActionType {
        case navigate
        case custom
        case ui_interaction
        case data_update
        case system

        init(from string: String) {
            switch string.lowercased() {
            case "navigate", "navigation":
                self = .navigate
            case "custom":
                self = .custom
            case "ui_interaction", "interaction":
                self = .ui_interaction
            case "data_update", "update":
                self = .data_update
            case "system":
                self = .system
            default:
                self = .custom
            }
        }
    }

    private init() {}

    // MARK: - Main Action Handler with Priority
    func handleAction(
        type: ActionType,
        payload: [String: Any],
        componentId: String? = nil,
        priority: ActionPriority = .normal
    ) {
        let actionId = UUID().uuidString
        let action = ActionQueueItem(
            id: actionId,
            type: type,
            payload: payload,
            componentId: componentId,
            priority: priority,
            timestamp: Date()
        )

        // Check if this action should be deduplicated
        if shouldDeduplicateAction(action) {
            logger.debug("Deduplicating similar action: \(type)")
            return
        }

        enqueueAction(action)
    }

    private func enqueueAction(_ action: ActionQueueItem) {
        // Check queue capacity
        if queuedActions.count >= maxQueueSize {
            logger.warning("Action queue at capacity, dropping oldest low-priority action")
            dropOldestLowPriorityAction()
        }

        queuedActions.append(action)
        updateQueueCounts()

        // Route to appropriate queue based on priority
        let queue = getQueueForPriority(action.priority)

        queue.async { [weak self] in
            Task {
                await self?.processQueuedAction(action)
            }
        }
    }

    private func processQueuedAction(_ action: ActionQueueItem) async {
        // Update UI state
        await MainActor.run {
            self.activeActions.insert(action.id)
            self.updateProcessingState()
        }

        do {
            let result = await processAction(
                type: action.type,
                payload: action.payload,
                componentId: action.componentId
            )

            await MainActor.run {
                self.completeAction(action.id, result: result)
            }

        } catch {
            await MainActor.run {
                self.completeAction(
                    action.id,
                    result: .failure("Action failed: \(error.localizedDescription)")
                )
            }
        }
    }

    private func completeAction(_ actionId: String, result: ActionResult) {
        activeActions.remove(actionId)
        queuedActions.removeAll { $0.id == actionId }

        lastActionResult = result
        updateQueueCounts()
        updateProcessingState()

        logger.debug("Completed action: \(actionId)")
    }

    private func updateProcessingState() {
        isProcessing = !activeActions.isEmpty
    }

    private func updateQueueCounts() {
        queuedActionsCount = queuedActions.count
        highPriorityQueueCount = queuedActions.filter { $0.priority == .high }.count
    }

    // MARK: - Action Processing
    private func processAction(
        type: ActionType,
        payload: [String: Any],
        componentId: String?
    ) async -> ActionResult {

        // Log action for debugging
        print("🎯 A2UIActionHandler: Processing \(type) action with payload: \(payload)")

        switch type {
        case .navigate:
            return await handleNavigationAction(payload: payload)

        case .custom:
            return await handleCustomAction(payload: payload, componentId: componentId)

        case .ui_interaction:
            return await handleUIInteraction(payload: payload, componentId: componentId)

        case .data_update:
            return await handleDataUpdate(payload: payload, componentId: componentId)

        case .system:
            return await handleSystemAction(payload: payload)
        }
    }

    // MARK: - Navigation Actions
    private func handleNavigationAction(payload: [String: Any]) async -> ActionResult {
        guard let destination = payload["destination"] as? String ??
              payload["screen"] as? String ??
              payload["homework_id"] as? String ??
              payload["mistake_id"] as? String else {
            return .failure("No navigation destination provided")
        }

        // Simulate navigation delay
        try? await Task.sleep(nanoseconds: 200_000_000) // 0.2s

        // In a real app, this would trigger navigation
        NotificationCenter.default.post(
            name: NSNotification.Name("A2UINavigate"),
            object: nil,
            userInfo: ["destination": destination, "payload": payload]
        )

        return .navigation(destination)
    }

    // MARK: - Custom Actions
    private func handleCustomAction(payload: [String: Any], componentId: String?) async -> ActionResult {
        guard let action = payload["action"] as? String else {
            return .failure("No action specified")
        }

        print("🔧 Handling custom action: \(action)")

        switch action {
        case "start_exercise":
            return await handleStartExercise(payload: payload)

        case "complete_step":
            return await handleCompleteStep(payload: payload)

        case "process_documents":
            return await handleProcessDocuments(payload: payload)

        case "process_image":
            return await handleProcessImage(payload: payload)

        case "generate_notes":
            return await handleGenerateNotes(payload: payload)

        case "create_flashcards":
            return await handleCreateFlashcards(payload: payload)

        case "save_extracted_text":
            return await handleSaveExtractedText(payload: payload)

        case "submit_homework":
            return await handleSubmitHomework(payload: payload)

        case "save_progress":
            return await handleSaveProgress(payload: payload)

        case "filter_homework":
            return await handleFilterHomework(payload: payload)

        case "view_attachment":
            return await handleViewAttachment(payload: payload)

        case "upload_new_document":
            return await handleUploadNewDocument(payload: payload)

        default:
            return await handleGenericCustomAction(action: action, payload: payload)
        }
    }

    // MARK: - UI Interaction Actions
    private func handleUIInteraction(payload: [String: Any], componentId: String?) async -> ActionResult {
        // Simulate UI interaction processing
        try? await Task.sleep(nanoseconds: 100_000_000) // 0.1s

        if let value = payload["value"] {
            print("📱 UI Interaction - Value changed: \(value)")

            // Notify observers of UI state change
            NotificationCenter.default.post(
                name: NSNotification.Name("A2UIStateChange"),
                object: nil,
                userInfo: ["componentId": componentId ?? "", "value": value]
            )
        }

        return .success("UI interaction handled")
    }

    // MARK: - Data Update Actions
    private func handleDataUpdate(payload: [String: Any], componentId: String?) async -> ActionResult {
        // Simulate data update processing
        try? await Task.sleep(nanoseconds: 300_000_000) // 0.3s

        print("💾 Data Update - Component: \(componentId ?? "unknown")")

        // In a real app, this would update backend data
        NotificationCenter.default.post(
            name: NSNotification.Name("A2UIDataUpdate"),
            object: nil,
            userInfo: payload
        )

        return .success("Data updated successfully")
    }

    // MARK: - System Actions
    private func handleSystemAction(payload: [String: Any]) async -> ActionResult {
        guard let action = payload["action"] as? String else {
            return .failure("No system action specified")
        }

        switch action {
        case "request_permissions":
            return await handleRequestPermissions(payload: payload)
        case "clear_cache":
            return await handleClearCache()
        case "sync_data":
            return await handleSyncData()
        default:
            return .failure("Unknown system action: \(action)")
        }
    }

    // MARK: - Specific Action Handlers

    private func handleStartExercise(payload: [String: Any]) async -> ActionResult {
        guard let exerciseId = payload["exercise_id"] as? String else {
            return .failure("No exercise ID provided")
        }

        // Simulate exercise loading
        try? await Task.sleep(nanoseconds: 500_000_000) // 0.5s

        return .navigation("exercise/\(exerciseId)")
    }

    private func handleCompleteStep(payload: [String: Any]) async -> ActionResult {
        guard let stepId = payload["step_id"] as? String else {
            return .failure("No step ID provided")
        }

        // Simulate step completion processing
        try? await Task.sleep(nanoseconds: 200_000_000) // 0.2s

        print("✅ Step completed: \(stepId)")
        return .success("Step marked as completed")
    }

    private func handleProcessDocuments(payload: [String: Any]) async -> ActionResult {
        guard let documentUrls = payload["document_urls"] as? [String] else {
            return .failure("No document URLs provided")
        }

        // Simulate document processing
        try? await Task.sleep(nanoseconds: 2_000_000_000) // 2s

        print("📄 Processing \(documentUrls.count) document(s)")

        // Mock OCR processing result
        let mockExtractedText = """
        This is mock extracted text from the processed document(s).

        Key Points:
        • Important concept 1
        • Important concept 2
        • Important concept 3

        The document contains valuable learning material that can be used to generate notes and flashcards.
        """

        // Simulate creating an OCR result component
        let ocrComponent = A2UIComponent(
            type: "ocr_result",
            props: [
                "extracted_text": .string(mockExtractedText),
                "confidence": .double(0.95),
                "source_type": .string("document"),
                "sections": .array([
                    .object([
                        "type": .string("heading"),
                        "content": .string("Important Document"),
                        "confidence": .double(0.98)
                    ]),
                    .object([
                        "type": .string("paragraph"),
                        "content": .string(mockExtractedText),
                        "confidence": .double(0.93)
                    ])
                ])
            ]
        )

        return .ui_update(ocrComponent)
    }

    private func handleProcessImage(payload: [String: Any]) async -> ActionResult {
        // Simulate image processing with OCR
        try? await Task.sleep(nanoseconds: 1_500_000_000) // 1.5s

        print("📸 Processing image for OCR")

        let mockExtractedText = """
        Handwritten Notes - Chapter 5

        Newton's Laws of Motion:
        1. An object at rest stays at rest
        2. F = ma
        3. Every action has an equal and opposite reaction

        Important formulas to remember for the exam.
        """

        let ocrComponent = A2UIComponent(
            type: "ocr_result",
            props: [
                "extracted_text": .string(mockExtractedText),
                "confidence": .double(0.87),
                "source_type": .string("image"),
                "sections": .array([
                    .object([
                        "type": .string("handwriting"),
                        "content": .string(mockExtractedText),
                        "confidence": .double(0.87)
                    ])
                ])
            ]
        )

        return .ui_update(ocrComponent)
    }

    private func handleGenerateNotes(payload: [String: Any]) async -> ActionResult {
        guard let extractedText = payload["extracted_text"] as? String else {
            return .failure("No text provided for note generation")
        }

        // Simulate AI note generation
        try? await Task.sleep(nanoseconds: 1_000_000_000) // 1s

        print("📝 Generating notes from extracted text")
        return .success("Notes generated successfully from extracted content")
    }

    private func handleCreateFlashcards(payload: [String: Any]) async -> ActionResult {
        // Simulate flashcard generation
        try? await Task.sleep(nanoseconds: 800_000_000) // 0.8s

        print("🎯 Creating flashcards from content")
        return .success("Flashcards created successfully")
    }

    private func handleSaveExtractedText(payload: [String: Any]) async -> ActionResult {
        guard let text = payload["text"] as? String else {
            return .failure("No text to save")
        }

        // Simulate saving text
        try? await Task.sleep(nanoseconds: 300_000_000) // 0.3s

        print("💾 Saved extracted text (\(text.count) characters)")
        return .success("Text saved to library")
    }

    private func handleSubmitHomework(payload: [String: Any]) async -> ActionResult {
        guard let homeworkId = payload["homework_id"] as? String else {
            return .failure("No homework ID provided")
        }

        // Simulate homework submission
        try? await Task.sleep(nanoseconds: 1_200_000_000) // 1.2s

        print("📚 Submitting homework: \(homeworkId)")
        return .success("Homework submitted successfully!")
    }

    private func handleSaveProgress(payload: [String: Any]) async -> ActionResult {
        // Simulate progress saving
        try? await Task.sleep(nanoseconds: 400_000_000) // 0.4s

        print("💾 Progress saved")
        return .success("Progress saved. You can continue later.")
    }

    private func handleFilterHomework(payload: [String: Any]) async -> ActionResult {
        guard let filter = payload["filter"] as? String else {
            return .failure("No filter specified")
        }

        print("🔍 Filtering homework by: \(filter)")
        return .success("Homework filtered by \(filter)")
    }

    private func handleViewAttachment(payload: [String: Any]) async -> ActionResult {
        guard let attachmentType = payload["attachment_type"] as? String else {
            return .failure("No attachment type specified")
        }

        print("👀 Viewing \(attachmentType) attachment")
        return .navigation("attachment_viewer")
    }

    private func handleUploadNewDocument(payload: [String: Any]) async -> ActionResult {
        print("📎 Opening document picker")

        // Trigger document picker via notification
        NotificationCenter.default.post(
            name: NSNotification.Name("A2UIShowDocumentPicker"),
            object: nil,
            userInfo: payload
        )

        return .success("Document picker opened")
    }

    private func handleRequestPermissions(payload: [String: Any]) async -> ActionResult {
        guard let permissions = payload["permissions"] as? [String] else {
            return .failure("No permissions specified")
        }

        print("🔐 Requesting permissions: \(permissions.joined(separator: ", "))")

        // Simulate permission request
        try? await Task.sleep(nanoseconds: 500_000_000) // 0.5s

        return .success("Permissions requested")
    }

    private func handleClearCache() async -> ActionResult {
        // Simulate cache clearing
        try? await Task.sleep(nanoseconds: 300_000_000) // 0.3s

        print("🗑️ Cache cleared")
        return .success("Cache cleared successfully")
    }

    private func handleSyncData() async -> ActionResult {
        // Simulate data synchronization
        try? await Task.sleep(nanoseconds: 1_000_000_000) // 1s

        print("🔄 Data synchronized")
        return .success("Data synchronized with server")
    }

    private func handleGenericCustomAction(action: String, payload: [String: Any]) async -> ActionResult {
        // Handle unknown custom actions
        try? await Task.sleep(nanoseconds: 200_000_000) // 0.2s

        print("⚙️ Generic custom action: \(action)")
        return .success("Action '\(action)' processed")
    }
}

    // MARK: - Queue Management Helpers

    private func shouldDeduplicateAction(_ action: ActionQueueItem) -> Bool {
        // Check if there's already a similar action in the queue
        let similarActions = queuedActions.filter { queuedAction in
            queuedAction.type == action.type &&
            queuedAction.componentId == action.componentId &&
            queuedAction.payload["action"] as? String == action.payload["action"] as? String
        }

        // Deduplicate rapid UI interactions
        switch action.type {
        case .ui_interaction:
            // Allow only one UI interaction per component
            return !similarActions.isEmpty
        case .data_update:
            // Deduplicate frequent data updates
            return similarActions.count > 0
        default:
            return false
        }
    }

    private func dropOldestLowPriorityAction() {
        // Find and remove the oldest low-priority action
        for (index, action) in queuedActions.enumerated() {
            if action.priority == .low {
                queuedActions.remove(at: index)
                logger.debug("Dropped low-priority action: \(action.type)")
                return
            }
        }

        // If no low-priority actions, remove oldest normal priority
        if let oldestIndex = queuedActions.enumerated()
            .filter({ $0.element.priority == .normal })
            .min(by: { $0.element.timestamp < $1.element.timestamp })?.offset {
            queuedActions.remove(at: oldestIndex)
            logger.debug("Dropped normal-priority action due to queue pressure")
        }
    }

    private func getQueueForPriority(_ priority: ActionPriority) -> DispatchQueue {
        switch priority {
        case .high:
            return highPriorityQueue
        case .normal:
            return defaultQueue
        case .low:
            return backgroundQueue
        }
    }

    // MARK: - Public Convenience Methods

    func handleUIInteraction(
        componentId: String,
        payload: [String: Any]
    ) {
        handleAction(
            type: .ui_interaction,
            payload: payload,
            componentId: componentId,
            priority: .high // UI interactions should be high priority
        )
    }

    func handleNavigation(to destination: String, payload: [String: Any] = [:]) {
        var navPayload = payload
        navPayload["destination"] = destination

        handleAction(
            type: .navigate,
            payload: navPayload,
            priority: .high // Navigation should be immediate
        )
    }

    func handleBackgroundTask(_ taskType: String, payload: [String: Any]) {
        var taskPayload = payload
        taskPayload["action"] = taskType

        handleAction(
            type: .custom,
            payload: taskPayload,
            priority: .low // Background tasks are low priority
        )
    }

    // MARK: - Queue Diagnostics

    func getQueueDiagnostics() -> ActionQueueDiagnostics {
        return ActionQueueDiagnostics(
            totalQueued: queuedActionsCount,
            highPriority: highPriorityQueueCount,
            normalPriority: queuedActions.filter { $0.priority == .normal }.count,
            lowPriority: queuedActions.filter { $0.priority == .low }.count,
            activeActions: activeActions.count,
            isProcessing: isProcessing
        )
    }

    func clearQueue() {
        queuedActions.removeAll()
        updateQueueCounts()
        logger.info("Action queue cleared")
    }
}

// MARK: - Supporting Types

enum ActionPriority: Int, Comparable {
    case high = 3    // UI interactions, navigation
    case normal = 2  // Standard actions
    case low = 1     // Background tasks, analytics

    static func < (lhs: ActionPriority, rhs: ActionPriority) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}

struct ActionQueueItem {
    let id: String
    let type: A2UIActionHandler.ActionType
    let payload: [String: Any]
    let componentId: String?
    let priority: ActionPriority
    let timestamp: Date
}

struct ActionQueueDiagnostics {
    let totalQueued: Int
    let highPriority: Int
    let normalPriority: Int
    let lowPriority: Int
    let activeActions: Int
    let isProcessing: Bool
}

// MARK: - Notification Extensions
extension NSNotification.Name {
    static let a2uiNavigate = NSNotification.Name("A2UINavigate")
    static let a2uiStateChange = NSNotification.Name("A2UIStateChange")
    static let a2uiDataUpdate = NSNotification.Name("A2UIDataUpdate")
    static let a2uiShowDocumentPicker = NSNotification.Name("A2UIShowDocumentPicker")
}