import XCTest
import SwiftUI
@testable import Lyo

class A2UIRendererTests: XCTestCase {

    var renderer: A2UIRenderer!
    var testActions: [A2UIAction] = []

    override func setUp() {
        super.setUp()
        testActions = []
    }

    // MARK: - Basic Component Tests

    func testTextComponentRendering() {
        let textComponent = A2UIComponent(
            type: "text",
            props: [
                "text": .string("Hello World"),
                "font": .string("title"),
                "color": .string("#FF0000")
            ]
        )

        renderer = A2UIRenderer(component: textComponent) { action in
            testActions.append(action)
        }

        XCTAssertNotNil(renderer)
        XCTAssertEqual(textComponent.prop("text").asString, "Hello World")
        XCTAssertEqual(textComponent.prop("font").asString, "title")
    }

    func testButtonComponentWithAction() {
        let buttonComponent = A2UIComponent(
            type: "button",
            props: [
                "title": .string("Click Me"),
                "action": .string("test_tap"),
                "style": .string("primary")
            ]
        )

        renderer = A2UIRenderer(component: buttonComponent) { action in
            testActions.append(action)
        }

        // Simulate button tap
        let action = A2UIAction(
            actionId: "test_tap",
            componentId: buttonComponent.id,
            actionType: "tap"
        )
        renderer.onAction?(action)

        XCTAssertEqual(testActions.count, 1)
        XCTAssertEqual(testActions.first?.actionId, "test_tap")
    }

    func testImageComponentRendering() {
        let imageComponent = A2UIComponent(
            type: "image",
            props: [
                "url": .string("https://example.com/image.jpg"),
                "width": .double(100),
                "height": .double(100),
                "aspectRatio": .string("fill")
            ]
        )

        renderer = A2UIRenderer(component: imageComponent)
        XCTAssertNotNil(renderer)
    }

    // MARK: - Layout Container Tests

    func testVStackWithChildren() {
        let vStackComponent = A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(16),
                "align": .string("leading")
            ],
            children: [
                A2UIComponent(
                    type: "text",
                    props: ["text": .string("First Item")]
                ),
                A2UIComponent(
                    type: "text",
                    props: ["text": .string("Second Item")]
                )
            ]
        )

        renderer = A2UIRenderer(component: vStackComponent)
        XCTAssertNotNil(renderer)
        XCTAssertEqual(vStackComponent.children?.count, 2)
    }

    func testHStackWithChildren() {
        let hStackComponent = A2UIComponent(
            type: "hstack",
            props: [
                "spacing": .double(12),
                "align": .string("center")
            ],
            children: [
                A2UIComponent(
                    type: "text",
                    props: ["text": .string("Left")]
                ),
                A2UIComponent(
                    type: "text",
                    props: ["text": .string("Right")]
                )
            ]
        )

        renderer = A2UIRenderer(component: hStackComponent)
        XCTAssertNotNil(renderer)
    }

    func testGridLayoutWithColumns() {
        let gridComponent = A2UIComponent(
            type: "grid",
            props: [
                "columns": .int(3),
                "spacing": .double(8)
            ],
            children: Array(1...6).map { index in
                A2UIComponent(
                    type: "text",
                    props: ["text": .string("Item \(index)")]
                )
            }
        )

        renderer = A2UIRenderer(component: gridComponent)
        XCTAssertNotNil(renderer)
        XCTAssertEqual(gridComponent.children?.count, 6)
    }

    // MARK: - Business Component Tests

    func testCourseCardComponent() {
        let courseCardComponent = A2UIComponent(
            type: "coursecard",
            props: [
                "title": .string("Swift Programming"),
                "description": .string("Learn iOS development"),
                "imageUrl": .string("https://example.com/swift.jpg"),
                "progress": .double(75.5),
                "difficulty": .string("Intermediate"),
                "duration": .string("2 hours"),
                "action": .string("course_tap")
            ]
        )

        renderer = A2UIRenderer(component: courseCardComponent) { action in
            testActions.append(action)
        }

        XCTAssertNotNil(renderer)
        XCTAssertEqual(courseCardComponent.prop("title").asString, "Swift Programming")
        XCTAssertEqual(courseCardComponent.prop("progress").asDouble, 75.5)
    }

    func testLessonCardComponent() {
        let lessonCardComponent = A2UIComponent(
            type: "lessoncard",
            props: [
                "title": .string("Variables and Constants"),
                "description": .string("Learn about var and let in Swift"),
                "completed": .bool(false),
                "duration": .string("15 min"),
                "type": .string("video"),
                "action": .string("lesson_tap")
            ]
        )

        renderer = A2UIRenderer(component: lessonCardComponent) { action in
            testActions.append(action)
        }

        XCTAssertNotNil(renderer)
        XCTAssertEqual(lessonCardComponent.prop("type").asString, "video")
        XCTAssertEqual(lessonCardComponent.prop("completed").asBool, false)
    }

    func testQuizComponent() {
        let quizComponent = A2UIComponent(
            type: "quiz",
            props: [
                "question": .string("What is the difference between var and let in Swift?"),
                "options": .array([
                    .string("var is for constants, let is for variables"),
                    .string("let is for constants, var is for variables"),
                    .string("There is no difference"),
                    .string("Both are deprecated")
                ]),
                "correctAnswer": .int(1),
                "selectedAnswer": .null,
                "action": .string("answer_selected")
            ]
        )

        renderer = A2UIRenderer(component: quizComponent) { action in
            testActions.append(action)
        }

        // Simulate answer selection
        let selectAction = A2UIAction(
            actionId: "answer_selected",
            componentId: quizComponent.id,
            actionType: "selection",
            params: ["selectedAnswer": 1]
        )
        renderer.onAction?(selectAction)

        XCTAssertEqual(testActions.count, 1)
        XCTAssertEqual(testActions.first?.params?["selectedAnswer"] as? Int, 1)
    }

    // MARK: - Interactive Component Tests

    func testSliderComponent() {
        let sliderComponent = A2UIComponent(
            type: "slider",
            props: [
                "min": .double(0),
                "max": .double(100),
                "value": .double(50)
            ]
        )

        renderer = A2UIRenderer(component: sliderComponent)
        XCTAssertNotNil(renderer)
    }

    func testToggleComponent() {
        let toggleComponent = A2UIComponent(
            type: "toggle",
            props: [
                "label": .string("Enable Notifications"),
                "value": .bool(true)
            ]
        )

        renderer = A2UIRenderer(component: toggleComponent)
        XCTAssertNotNil(renderer)
    }

    func testPickerComponent() {
        let pickerComponent = A2UIComponent(
            type: "picker",
            props: [
                "options": .array([
                    .string("Option 1"),
                    .string("Option 2"),
                    .string("Option 3")
                ]),
                "selectedIndex": .int(0)
            ]
        )

        renderer = A2UIRenderer(component: pickerComponent)
        XCTAssertNotNil(renderer)
    }

    // MARK: - Complex Nested Component Tests

    func testComplexNestedComponent() {
        let complexComponent = A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(20),
                "padding": .double(16)
            ],
            children: [
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("Course Overview"),
                        "font": .string("title")
                    ]
                ),
                A2UIComponent(
                    type: "hstack",
                    props: ["spacing": .double(16)],
                    children: [
                        A2UIComponent(
                            type: "coursecard",
                            props: [
                                "title": .string("SwiftUI Basics"),
                                "description": .string("Learn the fundamentals"),
                                "progress": .double(60),
                                "difficulty": .string("Beginner"),
                                "duration": .string("3 hours")
                            ]
                        ),
                        A2UIComponent(
                            type: "coursecard",
                            props: [
                                "title": .string("Advanced SwiftUI"),
                                "description": .string("Master complex layouts"),
                                "progress": .double(30),
                                "difficulty": .string("Advanced"),
                                "duration": .string("5 hours")
                            ]
                        )
                    ]
                ),
                A2UIComponent(
                    type: "button",
                    props: [
                        "title": .string("View All Courses"),
                        "action": .string("view_all"),
                        "style": .string("primary"),
                        "fullWidth": .bool(true)
                    ]
                )
            ]
        )

        renderer = A2UIRenderer(component: complexComponent) { action in
            testActions.append(action)
        }

        XCTAssertNotNil(renderer)
        XCTAssertEqual(complexComponent.children?.count, 3)
        XCTAssertEqual(complexComponent.children?[1].children?.count, 2)
    }

    // MARK: - Error Handling Tests

    func testUnknownComponentType() {
        let unknownComponent = A2UIComponent(
            type: "unknowntype",
            props: ["someProperty": .string("value")]
        )

        renderer = A2UIRenderer(component: unknownComponent)
        XCTAssertNotNil(renderer) // Should render error component instead of crashing
    }

    func testMissingRequiredProperties() {
        let incompleteComponent = A2UIComponent(
            type: "text",
            props: [:] // Missing text content
        )

        renderer = A2UIRenderer(component: incompleteComponent)
        XCTAssertNotNil(renderer) // Should handle gracefully with defaults
    }

    // MARK: - Style and Modifier Tests

    func testCommonModifiers() {
        let styledComponent = A2UIComponent(
            type: "text",
            props: [
                "text": .string("Styled Text"),
                "padding": .double(20),
                "margin": .double(10),
                "backgroundColor": .string("#F0F0F0"),
                "cornerRadius": .double(8),
                "borderWidth": .double(1),
                "borderColor": .string("#CCCCCC"),
                "opacity": .double(0.8)
            ]
        )

        renderer = A2UIRenderer(component: styledComponent)
        XCTAssertNotNil(renderer)
        XCTAssertEqual(styledComponent.prop("padding").asDouble, 20)
        XCTAssertEqual(styledComponent.prop("opacity").asDouble, 0.8)
    }

    // MARK: - Real-World Scenario Tests

    func testLearningDashboardScenario() {
        let dashboardComponent = createLearningDashboard()

        renderer = A2UIRenderer(component: dashboardComponent) { action in
            testActions.append(action)
        }

        XCTAssertNotNil(renderer)
        XCTAssertTrue(dashboardComponent.children?.count ?? 0 > 0)
    }

    func testQuizSessionScenario() {
        let quizSessionComponent = createQuizSession()

        renderer = A2UIRenderer(component: quizSessionComponent) { action in
            testActions.append(action)
        }

        XCTAssertNotNil(renderer)
    }

    // MARK: - Helper Methods

    private func createLearningDashboard() -> A2UIComponent {
        return A2UIComponent(
            type: "scroll",
            children: [
                A2UIComponent(
                    type: "vstack",
                    props: [
                        "spacing": .double(20),
                        "padding": .double(16)
                    ],
                    children: [
                        // Header
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string("Your Learning Dashboard"),
                                "font": .string("title"),
                                "textAlign": .string("center")
                            ]
                        ),

                        // Stats Row
                        A2UIComponent(
                            type: "hstack",
                            props: ["spacing": .double(16)],
                            children: [
                                createStatsCard(title: "Courses", value: "12", icon: "book.fill"),
                                createStatsCard(title: "Progress", value: "78%", icon: "chart.line.uptrend.xyaxis"),
                                createStatsCard(title: "Streak", value: "5 days", icon: "flame.fill")
                            ]
                        ),

                        // Current Courses
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string("Continue Learning"),
                                "font": .string("headline")
                            ]
                        ),

                        A2UIComponent(
                            type: "vstack",
                            props: ["spacing": .double(12)],
                            children: [
                                A2UIComponent(
                                    type: "coursecard",
                                    props: [
                                        "title": .string("iOS Development"),
                                        "description": .string("Build your first iOS app"),
                                        "progress": .double(65),
                                        "difficulty": .string("Intermediate"),
                                        "duration": .string("6 hours"),
                                        "action": .string("continue_ios")
                                    ]
                                ),
                                A2UIComponent(
                                    type: "coursecard",
                                    props: [
                                        "title": .string("Machine Learning"),
                                        "description": .string("Introduction to ML concepts"),
                                        "progress": .double(30),
                                        "difficulty": .string("Advanced"),
                                        "duration": .string("8 hours"),
                                        "action": .string("continue_ml")
                                    ]
                                )
                            ]
                        )
                    ]
                )
            ]
        )
    }

    private func createStatsCard(title: String, value: String, icon: String) -> A2UIComponent {
        return A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(8),
                "padding": .double(16),
                "backgroundColor": .string("#F8F9FA"),
                "cornerRadius": .double(12)
            ],
            children: [
                A2UIComponent(
                    type: "image",
                    props: [
                        "systemName": .string(icon),
                        "font": .string("title2"),
                        "color": .string("#007AFF")
                    ]
                ),
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string(value),
                        "font": .string("title2"),
                        "fontWeight": .string("bold")
                    ]
                ),
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string(title),
                        "font": .string("caption"),
                        "color": .string("#666666")
                    ]
                )
            ]
        )
    }

    private func createQuizSession() -> A2UIComponent {
        return A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(20),
                "padding": .double(16)
            ],
            children: [
                A2UIComponent(
                    type: "progressbar",
                    props: [
                        "progress": .double(60),
                        "color": .string("#34C759")
                    ]
                ),
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("Question 3 of 5"),
                        "font": .string("caption"),
                        "textAlign": .string("center")
                    ]
                ),
                A2UIComponent(
                    type: "quiz",
                    props: [
                        "question": .string("What is the time complexity of binary search?"),
                        "options": .array([
                            .string("O(n)"),
                            .string("O(log n)"),
                            .string("O(n log n)"),
                            .string("O(1)")
                        ]),
                        "correctAnswer": .int(1),
                        "action": .string("quiz_answer")
                    ]
                )
            ]
        )
    }
}

// MARK: - Test Utilities Extension
extension A2UIRendererTests {

    func testPerformanceOfComplexRendering() {
        let complexComponent = createLearningDashboard()

        measure {
            renderer = A2UIRenderer(component: complexComponent) { _ in }
        }
    }

    func testMemoryUsageWithManyComponents() {
        let manyComponents = A2UIComponent(
            type: "vstack",
            children: Array(0..<100).map { index in
                A2UIComponent(
                    type: "text",
                    props: ["text": .string("Item \(index)")]
                )
            }
        )

        renderer = A2UIRenderer(component: manyComponents)
        XCTAssertNotNil(renderer)
        XCTAssertEqual(manyComponents.children?.count, 100)
    }
}