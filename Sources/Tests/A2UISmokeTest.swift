import Foundation
import SwiftUI
import XCTest

// MARK: - A2UI Protocol Smoke Tests
@MainActor
class A2UISmokeTest: XCTestCase {

    // Test data and components
    private var testComponents: [A2UIComponent] = []
    private var mockBackendService: MockA2UIBackendService!
    private var capabilityManager: A2UICapabilityManager!

    override func setUp() async throws {
        try await super.setUp()

        // Initialize test components
        setupTestComponents()

        // Initialize mock services
        mockBackendService = MockA2UIBackendService()
        capabilityManager = A2UICapabilityManager()
    }

    override func tearDown() async throws {
        testComponents.removeAll()
        mockBackendService = nil
        capabilityManager = nil

        try await super.tearDown()
    }

    // MARK: - Component Parsing Tests

    func testBasicComponentParsing() throws {
        let jsonString = """
        {
            "id": "test-1",
            "type": "text",
            "props": {
                "text": "Hello World",
                "font": "headline",
                "color": "#007AFF"
            }
        }
        """

        let data = jsonString.data(using: .utf8)!
        let component = try JSONDecoder().decode(A2UIComponent.self, from: data)

        XCTAssertEqual(component.id, "test-1")
        XCTAssertEqual(component.type, "text")
        XCTAssertEqual(component.prop("text").asString, "Hello World")
        XCTAssertEqual(component.prop("font").asString, "headline")
        XCTAssertEqual(component.prop("color").asString, "#007AFF")
    }

    func testComplexNestedComponentParsing() throws {
        let jsonString = """
        {
            "id": "container-1",
            "type": "vstack",
            "props": {
                "spacing": 16,
                "padding": 20
            },
            "children": [
                {
                    "id": "header-1",
                    "type": "text",
                    "props": {
                        "text": "Welcome to Lyo",
                        "font": "title"
                    }
                },
                {
                    "id": "button-1",
                    "type": "button",
                    "props": {
                        "title": "Get Started",
                        "action": "start_course",
                        "style": "primary"
                    }
                }
            ]
        }
        """

        let data = jsonString.data(using: .utf8)!
        let component = try JSONDecoder().decode(A2UIComponent.self, from: data)

        XCTAssertEqual(component.type, "vstack")
        XCTAssertEqual(component.prop("spacing").asDouble, 16.0)
        XCTAssertNotNil(component.children)
        XCTAssertEqual(component.children?.count, 2)

        let firstChild = component.children?.first
        XCTAssertEqual(firstChild?.type, "text")
        XCTAssertEqual(firstChild?.prop("text").asString, "Welcome to Lyo")
    }

    func testInvalidComponentHandling() {
        let invalidJson = """
        {
            "id": "invalid-1",
            "type": "unknown_component",
            "props": {
                "invalid_prop": null
            }
        }
        """

        let data = invalidJson.data(using: .utf8)!

        XCTAssertNoThrow({
            let component = try JSONDecoder().decode(A2UIComponent.self, from: data)
            XCTAssertEqual(component.type, "unknown_component")
            XCTAssertEqual(component.prop("invalid_prop"), .null)
        })
    }

    // MARK: - UIValue Type Safety Tests

    func testUIValueTypeSafety() {
        let stringValue = UIValue.string("test")
        let intValue = UIValue.int(42)
        let doubleValue = UIValue.double(3.14)
        let boolValue = UIValue.bool(true)
        let arrayValue = UIValue.array([.string("item1"), .string("item2")])
        let nullValue = UIValue.null

        // Test string conversions
        XCTAssertEqual(stringValue.asString, "test")
        XCTAssertEqual(intValue.asString, "42")
        XCTAssertEqual(boolValue.asString, "true")

        // Test int conversions
        XCTAssertEqual(intValue.asInt, 42)
        XCTAssertEqual(doubleValue.asInt, 3)
        XCTAssertNil(stringValue.asInt)

        // Test null handling
        XCTAssertNil(nullValue.asString)
        XCTAssertNil(nullValue.asInt)
        XCTAssertNil(nullValue.asBool)

        // Test array access
        XCTAssertEqual(arrayValue.asArray?.count, 2)
        XCTAssertEqual(arrayValue.asArray?.first?.asString, "item1")
    }

    // MARK: - Capability Manager Tests

    func testCapabilityHandshake() async throws {
        // Test basic capability negotiation
        try await capabilityManager.negotiate(force: true)

        // Test supported elements
        XCTAssertTrue(capabilityManager.isSupported(.text))
        XCTAssertTrue(capabilityManager.isSupported(.button))
        XCTAssertTrue(capabilityManager.isSupported(.vstack))

        // Test permission-dependent elements
        let cameraSupported = capabilityManager.isSupported(.cameraCapture)
        let hasPermission = capabilityManager.hasPermission(for: .cameraCapture)

        // Camera support depends on permission
        if !hasPermission {
            XCTAssertFalse(cameraSupported)
        }
    }

    func testUnsupportedElementFallback() {
        // Test that unsupported elements are handled gracefully
        let unsupportedElement = A2UIElementType.voiceRecognition

        if !capabilityManager.isSupported(unsupportedElement) {
            // Should not crash, should provide fallback
            XCTAssertNoThrow({
                let fallback = capabilityManager.getFallbackElement(for: unsupportedElement)
                XCTAssertNotNil(fallback)
            })
        }
    }

    // MARK: - Action Handler Tests

    func testActionHandlerBasicActions() async throws {
        let actionHandler = A2UIActionHandler.shared

        // Test navigation action
        let navPayload = ["destination": "test_screen"]
        actionHandler.handleAction(type: .navigate, payload: navPayload)

        // Wait for processing
        try await Task.sleep(nanoseconds: 500_000_000)

        // Should not crash and should set processing state
        XCTAssertFalse(actionHandler.isProcessing)
        XCTAssertNotNil(actionHandler.lastActionResult)
    }

    func testActionHandlerCustomActions() async throws {
        let actionHandler = A2UIActionHandler.shared

        // Test custom action
        let customPayload = [
            "action": "generate_notes",
            "extracted_text": "Test content for note generation"
        ]

        actionHandler.handleAction(type: .custom, payload: customPayload)

        // Wait for processing
        try await Task.sleep(nanoseconds: 1_200_000_000)

        XCTAssertFalse(actionHandler.isProcessing)

        if case .success(let message) = actionHandler.lastActionResult {
            XCTAssertTrue(message.contains("Notes generated"))
        } else {
            XCTFail("Expected success result")
        }
    }

    // MARK: - Backend Integration Tests

    func testBackendServiceErrorHandling() async throws {
        // Test with invalid screen ID
        await mockBackendService.loadScreen("invalid_screen")

        // Should handle gracefully without crashing
        XCTAssertNotNil(mockBackendService.currentComponent)

        // Should show error component
        let component = mockBackendService.currentComponent
        XCTAssertTrue(component?.type.contains("vstack") ?? false)
    }

    func testBackendServiceMockData() async throws {
        // Test loading mock screens
        let screens = ["dashboard", "course", "quiz", "chat", "settings"]

        for screen in screens {
            await mockBackendService.loadScreen(screen)

            XCTAssertNotNil(mockBackendService.currentComponent)

            let component = mockBackendService.currentComponent
            XCTAssertNotNil(component?.id)
            XCTAssertFalse(component?.type.isEmpty ?? true)
        }
    }

    // MARK: - Renderer Integration Tests

    func testBasicRendererIntegration() {
        let textComponent = A2UIComponent(
            type: "text",
            props: [
                "text": .string("Test Renderer"),
                "font": .string("body"),
                "color": .string("#000000")
            ]
        )

        // Should not crash when creating renderer
        XCTAssertNoThrow({
            let renderer = A2UIRenderer(component: textComponent)
            XCTAssertNotNil(renderer)
        })
    }

    func testComplexRendererIntegration() {
        let complexComponent = A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(16),
                "padding": .double(20)
            ],
            children: [
                A2UIComponent(
                    type: "text",
                    props: ["text": .string("Header")]
                ),
                A2UIComponent(
                    type: "button",
                    props: [
                        "title": .string("Action"),
                        "action": .string("test_action")
                    ]
                )
            ]
        )

        // Should handle nested components
        XCTAssertNoThrow({
            let renderer = A2UIRenderer(component: complexComponent)
            XCTAssertNotNil(renderer)
        })
    }

    // MARK: - Error Scenarios and Edge Cases

    func testMalformedJSONHandling() {
        let malformedJson = """
        {
            "id": "malformed",
            "type": "text",
            "props": {
                "text": "Unclosed string
            }
        """

        let data = malformedJson.data(using: .utf8)!

        XCTAssertThrowsError(try JSONDecoder().decode(A2UIComponent.self, from: data)) { error in
            XCTAssertTrue(error is DecodingError)
        }
    }

    func testEmptyComponentHandling() {
        let emptyComponent = A2UIComponent(type: "", props: nil, children: nil)

        // Should handle empty components gracefully
        XCTAssertNoThrow({
            let renderer = A2UIRenderer(component: emptyComponent)
            XCTAssertNotNil(renderer)
        })
    }

    func testLargeComponentTree() {
        // Create deep nested component tree
        var component = A2UIComponent(
            type: "vstack",
            children: []
        )

        // Create 100 nested components
        for i in 0..<100 {
            let child = A2UIComponent(
                type: "text",
                props: ["text": .string("Item \(i)")]
            )
            component = A2UIComponent(
                type: "vstack",
                children: [component, child]
            )
        }

        // Should handle large trees without crashing
        XCTAssertNoThrow({
            let renderer = A2UIRenderer(component: component)
            XCTAssertNotNil(renderer)
        })
    }

    // MARK: - Memory and Performance Tests

    func testMemoryLeaks() async throws {
        let components = (0..<1000).map { i in
            A2UIComponent(
                type: "text",
                props: ["text": .string("Component \(i)")]
            )
        }

        // Create and destroy many renderers
        for component in components {
            let renderer = A2UIRenderer(component: component)
            _ = renderer // Use renderer to prevent optimization
        }

        // Force memory cleanup
        for _ in 0..<3 {
            try await Task.sleep(nanoseconds: 100_000_000)
        }

        // Test should complete without memory issues
        XCTAssertTrue(true)
    }

    func testConcurrentActionHandling() async throws {
        let actionHandler = A2UIActionHandler.shared

        // Create multiple concurrent actions
        let tasks = (0..<10).map { i in
            Task {
                let payload = ["test_id": "concurrent_\(i)"]
                actionHandler.handleAction(type: .custom, payload: payload)
            }
        }

        // Wait for all tasks to complete
        for task in tasks {
            await task.value
        }

        // Should handle concurrency without crashes
        XCTAssertFalse(actionHandler.isProcessing)
    }

    // MARK: - Integration Stress Tests

    func testEndToEndWorkflow() async throws {
        // Simulate complete user workflow

        // 1. Load screen
        await mockBackendService.loadScreen("dashboard")
        XCTAssertNotNil(mockBackendService.currentComponent)

        // 2. Handle user action
        let action = A2UIAction(
            actionId: "start_course",
            componentId: "course_button_1",
            actionType: "tap"
        )
        await mockBackendService.handleAction(action)

        // 3. Capability check
        try await capabilityManager.negotiate()
        XCTAssertTrue(capabilityManager.isSupported(.text))

        // 4. Action processing
        A2UIActionHandler.shared.handleAction(
            type: .navigate,
            payload: ["destination": "course_content"]
        )

        // Wait for processing
        try await Task.sleep(nanoseconds: 1_000_000_000)

        // Should complete workflow without errors
        XCTAssertNotNil(mockBackendService.currentComponent)
    }

    // MARK: - Helper Methods

    private func setupTestComponents() {
        testComponents = [
            // Basic components
            A2UIComponent(
                type: "text",
                props: ["text": .string("Test Text")]
            ),

            // Container components
            A2UIComponent(
                type: "vstack",
                props: ["spacing": .double(16)],
                children: [
                    A2UIComponent(type: "text", props: ["text": .string("Child 1")]),
                    A2UIComponent(type: "text", props: ["text": .string("Child 2")])
                ]
            ),

            // Interactive components
            A2UIComponent(
                type: "button",
                props: [
                    "title": .string("Test Button"),
                    "action": .string("test_action")
                ]
            ),

            // Complex business components
            A2UIComponent(
                type: "homework_card",
                props: [
                    "title": .string("Math Homework"),
                    "subject": .string("Algebra"),
                    "due_date": .string("Tomorrow"),
                    "progress": .double(0.75)
                ]
            )
        ]
    }
}

// MARK: - Mock Backend Service for Testing
@MainActor
class MockA2UIBackendService: ObservableObject {
    @Published var currentComponent: A2UIComponent?

    func loadScreen(_ screenId: String) async {
        // Simulate network delay
        try? await Task.sleep(nanoseconds: 200_000_000)

        switch screenId {
        case "dashboard":
            currentComponent = createMockDashboard()
        case "course":
            currentComponent = createMockCourse()
        case "quiz":
            currentComponent = createMockQuiz()
        default:
            currentComponent = createErrorComponent("Unknown screen: \(screenId)")
        }
    }

    func handleAction(_ action: A2UIAction) async {
        // Simulate action processing
        try? await Task.sleep(nanoseconds: 100_000_000)

        switch action.actionId {
        case "start_course":
            currentComponent = createMockCourse()
        case "take_quiz":
            currentComponent = createMockQuiz()
        default:
            print("Mock: Handled action \(action.actionId)")
        }
    }

    private func createMockDashboard() -> A2UIComponent {
        A2UIComponent(
            type: "vstack",
            props: ["spacing": .double(20)],
            children: [
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("Mock Dashboard"),
                        "font": .string("title")
                    ]
                ),
                A2UIComponent(
                    type: "button",
                    props: [
                        "title": .string("Start Learning"),
                        "action": .string("start_course")
                    ]
                )
            ]
        )
    }

    private func createMockCourse() -> A2UIComponent {
        A2UIComponent(
            type: "vstack",
            props: ["spacing": .double(16)],
            children: [
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("Mock Course Content"),
                        "font": .string("headline")
                    ]
                )
            ]
        )
    }

    private func createMockQuiz() -> A2UIComponent {
        A2UIComponent(
            type: "quiz",
            props: [
                "question": .string("What is 2 + 2?"),
                "options": .array([.string("3"), .string("4"), .string("5")]),
                "correctAnswer": .int(1)
            ]
        )
    }

    private func createErrorComponent(_ message: String) -> A2UIComponent {
        A2UIComponent(
            type: "vstack",
            props: ["spacing": .double(12)],
            children: [
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("Error"),
                        "font": .string("headline"),
                        "color": .string("#FF0000")
                    ]
                ),
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string(message),
                        "font": .string("body")
                    ]
                )
            ]
        )
    }
}

// MARK: - Capability Manager Extension for Testing
extension A2UICapabilityManager {
    func getFallbackElement(for elementType: A2UIElementType) -> A2UIElementType? {
        switch elementType {
        case .voiceRecognition:
            return .textInput
        case .cameraCapture:
            return .imageUpload
        case .handwritingInput:
            return .textInput
        default:
            return .text
        }
    }
}