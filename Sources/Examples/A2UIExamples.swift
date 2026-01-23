import SwiftUI

// MARK: - A2UI Renderer Examples and Integration Demo
struct A2UIExamplesView: View {
    @State private var selectedExample = 0
    @State private var actionLog: [String] = []

    private let examples = [
        "Learning Dashboard",
        "Interactive Course",
        "Quiz Session",
        "Live Chat",
        "Settings Panel"
    ]

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Example Selector
                Picker("Select Example", selection: $selectedExample) {
                    ForEach(Array(examples.enumerated()), id: \.offset) { index, example in
                        Text(example).tag(index)
                    }
                }
                .pickerStyle(SegmentedPickerStyle())
                .padding()

                // A2UI Renderer Display
                ScrollView {
                    A2UIRenderer(
                        component: getExampleComponent(selectedExample),
                        onAction: handleAction
                    )
                    .padding()
                }

                // Action Log
                if !actionLog.isEmpty {
                    VStack(alignment: .leading) {
                        Text("Action Log:")
                            .font(.headline)
                            .padding(.horizontal)

                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack {
                                ForEach(actionLog.suffix(5), id: \.self) { action in
                                    Text(action)
                                        .font(.caption)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(Color.blue.opacity(0.1))
                                        .cornerRadius(8)
                                }
                            }
                            .padding(.horizontal)
                        }
                    }
                    .frame(height: 80)
                    .background(Color(.systemGray6))
                }
            }
            .navigationTitle("A2UI Examples")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Clear Log") {
                        actionLog.removeAll()
                    }
                }
            }
        }
    }

    private func handleAction(_ action: A2UIAction) {
        let actionDescription = "\(action.actionId) (\(action.actionType))"
        actionLog.append(actionDescription)

        // Keep only last 10 actions
        if actionLog.count > 10 {
            actionLog.removeFirst()
        }

        // Handle specific actions
        switch action.actionId {
        case "start_course":
            print("🎓 Starting course...")
        case "take_quiz":
            print("❓ Starting quiz...")
        case "play_video":
            print("▶️ Playing video...")
        case "chat_message":
            if let message = action.params?["message"] as? String {
                print("💬 Chat message: \(message)")
            }
        default:
            print("🔄 Action: \(action.actionId)")
        }
    }

    private func getExampleComponent(_ index: Int) -> A2UIComponent {
        switch index {
        case 0: return createLearningDashboard()
        case 1: return createInteractiveCourse()
        case 2: return createQuizSession()
        case 3: return createLiveChat()
        case 4: return createSettingsPanel()
        default: return createLearningDashboard()
        }
    }

    // MARK: - Example Component Creators

    private func createLearningDashboard() -> A2UIComponent {
        return A2UIComponent(
            type: "scroll",
            props: ["showIndicators": .bool(false)],
            children: [
                A2UIComponent(
                    type: "vstack",
                    props: [
                        "spacing": .double(24),
                        "padding": .double(16)
                    ],
                    children: [
                        // Welcome Header
                        A2UIComponent(
                            type: "vstack",
                            props: [
                                "spacing": .double(8),
                                "align": .string("center")
                            ],
                            children: [
                                A2UIComponent(
                                    type: "text",
                                    props: [
                                        "text": .string("Welcome back, Alex! 👋"),
                                        "font": .string("title"),
                                        "textAlign": .string("center")
                                    ]
                                ),
                                A2UIComponent(
                                    type: "text",
                                    props: [
                                        "text": .string("Ready to continue your learning journey?"),
                                        "font": .string("subheadline"),
                                        "color": .string("#666666"),
                                        "textAlign": .string("center")
                                    ]
                                )
                            ]
                        ),

                        // Stats Cards
                        A2UIComponent(
                            type: "hstack",
                            props: ["spacing": .double(12)],
                            children: [
                                createStatsCard("12", "Courses", "book.fill", "#007AFF"),
                                createStatsCard("87%", "Progress", "chart.line.uptrend.xyaxis", "#34C759"),
                                createStatsCard("15", "Streak", "flame.fill", "#FF9500")
                            ]
                        ),

                        // Continue Learning Section
                        A2UIComponent(
                            type: "vstack",
                            props: [
                                "spacing": .double(16),
                                "align": .string("leading")
                            ],
                            children: [
                                A2UIComponent(
                                    type: "text",
                                    props: [
                                        "text": .string("Continue Learning"),
                                        "font": .string("headline")
                                    ]
                                ),
                                A2UIComponent(
                                    type: "coursecard",
                                    props: [
                                        "title": .string("SwiftUI Mastery"),
                                        "description": .string("Build beautiful iOS apps with declarative UI"),
                                        "imageUrl": .string("https://developer.apple.com/swift/images/swift-og.png"),
                                        "progress": .double(68.5),
                                        "difficulty": .string("Intermediate"),
                                        "duration": .string("4.5 hours"),
                                        "action": .string("continue_swiftui")
                                    ]
                                ),
                                A2UIComponent(
                                    type: "coursecard",
                                    props: [
                                        "title": .string("Machine Learning Basics"),
                                        "description": .string("Introduction to AI and ML concepts"),
                                        "progress": .double(25.0),
                                        "difficulty": .string("Beginner"),
                                        "duration": .string("6 hours"),
                                        "action": .string("continue_ml")
                                    ]
                                )
                            ]
                        ),

                        // Quick Actions
                        A2UIComponent(
                            type: "vstack",
                            props: [
                                "spacing": .double(12),
                                "align": .string("leading")
                            ],
                            children: [
                                A2UIComponent(
                                    type: "text",
                                    props: [
                                        "text": .string("Quick Actions"),
                                        "font": .string("headline")
                                    ]
                                ),
                                A2UIComponent(
                                    type: "hstack",
                                    props: ["spacing": .double(12)],
                                    children: [
                                        createQuickActionButton("Take Quiz", "questionmark.circle.fill", "take_quiz"),
                                        createQuickActionButton("Browse Courses", "magnifyingglass", "browse_courses")
                                    ]
                                )
                            ]
                        )
                    ]
                )
            ]
        )
    }

    private func createInteractiveCourse() -> A2UIComponent {
        return A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(20),
                "padding": .double(16)
            ],
            children: [
                // Course Header
                A2UIComponent(
                    type: "vstack",
                    props: [
                        "spacing": .double(12),
                        "align": .string("leading")
                    ],
                    children: [
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string("SwiftUI Fundamentals"),
                                "font": .string("title")
                            ]
                        ),
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string("Chapter 3: State Management"),
                                "font": .string("headline"),
                                "color": .string("#007AFF")
                            ]
                        ),
                        A2UIComponent(
                            type: "progressbar",
                            props: [
                                "progress": .double(65),
                                "color": .string("#007AFF")
                            ]
                        )
                    ]
                ),

                // Video Player
                A2UIComponent(
                    type: "vstack",
                    props: ["spacing": .double(8)],
                    children: [
                        A2UIComponent(
                            type: "video",
                            props: [
                                "url": .string("https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4"),
                                "height": .double(200),
                                "controls": .bool(true),
                                "action": .string("play_video")
                            ]
                        ),
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string("Introduction to @State and @Binding"),
                                "font": .string("caption"),
                                "color": .string("#666666"),
                                "textAlign": .string("center")
                            ]
                        )
                    ]
                ),

                // Interactive Code Example
                A2UIComponent(
                    type: "vstack",
                    props: [
                        "spacing": .double(12),
                        "backgroundColor": .string("#F8F9FA"),
                        "cornerRadius": .double(12),
                        "padding": .double(16)
                    ],
                    children: [
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string("Try it yourself:"),
                                "font": .string("headline")
                            ]
                        ),
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string("@State private var count = 0\n\nButton(\"Count: \\(count)\") {\n    count += 1\n}"),
                                "font": .string("code"),
                                "backgroundColor": .string("#FFFFFF"),
                                "padding": .double(12),
                                "cornerRadius": .double(8)
                            ]
                        ),
                        A2UIComponent(
                            type: "button",
                            props: [
                                "title": .string("Run Code"),
                                "action": .string("run_code"),
                                "style": .string("primary")
                            ]
                        )
                    ]
                ),

                // Next Lesson
                A2UIComponent(
                    type: "lessoncard",
                    props: [
                        "title": .string("Property Wrappers Deep Dive"),
                        "description": .string("Learn about @StateObject, @ObservedObject, and more"),
                        "completed": .bool(false),
                        "duration": .string("12 min"),
                        "type": .string("video"),
                        "action": .string("next_lesson")
                    ]
                )
            ]
        )
    }

    private func createQuizSession() -> A2UIComponent {
        return A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(24),
                "padding": .double(16)
            ],
            children: [
                // Quiz Header
                A2UIComponent(
                    type: "vstack",
                    props: [
                        "spacing": .double(8),
                        "align": .string("center")
                    ],
                    children: [
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string("SwiftUI Knowledge Check"),
                                "font": .string("title2"),
                                "textAlign": .string("center")
                            ]
                        ),
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string("Question 2 of 5"),
                                "font": .string("subheadline"),
                                "color": .string("#666666"),
                                "textAlign": .string("center")
                            ]
                        ),
                        A2UIComponent(
                            type: "progressbar",
                            props: [
                                "progress": .double(40),
                                "color": .string("#34C759")
                            ]
                        )
                    ]
                ),

                // Quiz Question
                A2UIComponent(
                    type: "quiz",
                    props: [
                        "question": .string("Which property wrapper is used for simple local state in SwiftUI?"),
                        "options": .array([
                            .string("@State"),
                            .string("@Binding"),
                            .string("@StateObject"),
                            .string("@ObservedObject")
                        ]),
                        "correctAnswer": .int(0),
                        "selectedAnswer": .null,
                        "action": .string("quiz_answer")
                    ]
                ),

                // Quiz Navigation
                A2UIComponent(
                    type: "hstack",
                    props: ["spacing": .double(12)],
                    children: [
                        A2UIComponent(
                            type: "button",
                            props: [
                                "title": .string("Previous"),
                                "action": .string("quiz_previous"),
                                "style": .string("outline")
                            ]
                        ),
                        A2UIComponent(
                            type: "spacer",
                            props: [:]
                        ),
                        A2UIComponent(
                            type: "button",
                            props: [
                                "title": .string("Next Question"),
                                "action": .string("quiz_next"),
                                "style": .string("primary")
                            ]
                        )
                    ]
                )
            ]
        )
    }

    private func createLiveChat() -> A2UIComponent {
        return A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(16),
                "padding": .double(16)
            ],
            children: [
                // Chat Header
                A2UIComponent(
                    type: "hstack",
                    props: ["spacing": .double(12)],
                    children: [
                        A2UIComponent(
                            type: "image",
                            props: [
                                "systemName": .string("person.circle.fill"),
                                "font": .string("title"),
                                "color": .string("#007AFF")
                            ]
                        ),
                        A2UIComponent(
                            type: "vstack",
                            props: [
                                "spacing": .double(2),
                                "align": .string("leading")
                            ],
                            children: [
                                A2UIComponent(
                                    type: "text",
                                    props: [
                                        "text": .string("AI Tutor"),
                                        "font": .string("headline")
                                    ]
                                ),
                                A2UIComponent(
                                    type: "text",
                                    props: [
                                        "text": .string("Online • Helping you learn"),
                                        "font": .string("caption"),
                                        "color": .string("#34C759")
                                    ]
                                )
                            ]
                        )
                    ]
                ),

                // Chat Messages
                A2UIComponent(
                    type: "scroll",
                    props: ["direction": .string("vertical")],
                    children: [
                        A2UIComponent(
                            type: "vstack",
                            props: [
                                "spacing": .double(16),
                                "align": .string("leading")
                            ],
                            children: [
                                createChatMessage("Hello! I'm here to help you learn SwiftUI. What would you like to know?", false),
                                createChatMessage("How do I create a custom button in SwiftUI?", true),
                                createChatMessage("Great question! Let me show you an example:", false),

                                // Interactive code example
                                A2UIComponent(
                                    type: "vstack",
                                    props: [
                                        "spacing": .double(12),
                                        "backgroundColor": .string("#F0F8FF"),
                                        "cornerRadius": .double(12),
                                        "padding": .double(16)
                                    ],
                                    children: [
                                        A2UIComponent(
                                            type: "text",
                                            props: [
                                                "text": .string("Custom Button Example"),
                                                "font": .string("headline")
                                            ]
                                        ),
                                        A2UIComponent(
                                            type: "button",
                                            props: [
                                                "title": .string("Custom Style Button"),
                                                "action": .string("try_custom_button"),
                                                "style": .string("primary"),
                                                "backgroundColor": .string("#FF6B35"),
                                                "cornerRadius": .double(20)
                                            ]
                                        )
                                    ]
                                )
                            ]
                        )
                    ]
                ),

                // Chat Input
                A2UIComponent(
                    type: "hstack",
                    props: ["spacing": .double(12)],
                    children: [
                        A2UIComponent(
                            type: "textfield",
                            props: [
                                "placeholder": .string("Type your question..."),
                                "backgroundColor": .string("#F8F9FA"),
                                "cornerRadius": .double(20),
                                "padding": .double(12)
                            ]
                        ),
                        A2UIComponent(
                            type: "button",
                            props: [
                                "title": .string("Send"),
                                "action": .string("send_message"),
                                "style": .string("primary")
                            ]
                        )
                    ]
                )
            ]
        )
    }

    private func createSettingsPanel() -> A2UIComponent {
        return A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(20),
                "padding": .double(16)
            ],
            children: [
                // Settings Header
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("Learning Preferences"),
                        "font": .string("title"),
                        "textAlign": .string("center")
                    ]
                ),

                // Learning Settings
                createSettingsSection("Learning", [
                    ("Dark Mode", "toggle", "dark_mode", true),
                    ("Auto-play Videos", "toggle", "autoplay", false),
                    ("Difficulty Level", "picker", "difficulty", nil)
                ]),

                // Notification Settings
                createSettingsSection("Notifications", [
                    ("Daily Reminders", "toggle", "reminders", true),
                    ("Achievement Alerts", "toggle", "achievements", true),
                    ("Course Updates", "toggle", "updates", false)
                ]),

                // Privacy Settings
                createSettingsSection("Privacy", [
                    ("Analytics", "toggle", "analytics", false),
                    ("Learning Progress Sync", "toggle", "sync", true)
                ]),

                // Action Buttons
                A2UIComponent(
                    type: "vstack",
                    props: ["spacing": .double(12)],
                    children: [
                        A2UIComponent(
                            type: "button",
                            props: [
                                "title": .string("Export Learning Data"),
                                "action": .string("export_data"),
                                "style": .string("outline"),
                                "fullWidth": .bool(true)
                            ]
                        ),
                        A2UIComponent(
                            type: "button",
                            props: [
                                "title": .string("Reset All Progress"),
                                "action": .string("reset_progress"),
                                "style": .string("danger"),
                                "fullWidth": .bool(true)
                            ]
                        )
                    ]
                )
            ]
        )
    }

    // MARK: - Helper Methods

    private func createStatsCard(_ value: String, _ title: String, _ icon: String, _ color: String) -> A2UIComponent {
        return A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(8),
                "padding": .double(16),
                "backgroundColor": .string("#F8F9FA"),
                "cornerRadius": .double(12),
                "align": .string("center")
            ],
            children: [
                A2UIComponent(
                    type: "image",
                    props: [
                        "systemName": .string(icon),
                        "font": .string("title2"),
                        "color": .string(color)
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

    private func createQuickActionButton(_ title: String, _ icon: String, _ action: String) -> A2UIComponent {
        return A2UIComponent(
            type: "button",
            props: [
                "action": .string(action),
                "style": .string("outline"),
                "cornerRadius": .double(12),
                "padding": .double(16)
            ],
            children: [
                A2UIComponent(
                    type: "hstack",
                    props: ["spacing": .double(8)],
                    children: [
                        A2UIComponent(
                            type: "image",
                            props: [
                                "systemName": .string(icon),
                                "color": .string("#007AFF")
                            ]
                        ),
                        A2UIComponent(
                            type: "text",
                            props: [
                                "text": .string(title),
                                "font": .string("subheadline")
                            ]
                        )
                    ]
                )
            ]
        )
    }

    private func createChatMessage(_ text: String, _ isUser: Bool) -> A2UIComponent {
        return A2UIComponent(
            type: "hstack",
            props: [
                "align": .string(isUser ? "trailing" : "leading")
            ],
            children: [
                isUser ? A2UIComponent(type: "spacer", props: [:]) : nil,
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string(text),
                        "font": .string("body"),
                        "padding": .double(12),
                        "backgroundColor": .string(isUser ? "#007AFF" : "#F0F0F0"),
                        "color": .string(isUser ? "#FFFFFF" : "#000000"),
                        "cornerRadius": .double(16),
                        "maxWidth": .string("280")
                    ]
                ),
                !isUser ? A2UIComponent(type: "spacer", props: [:]) : nil
            ].compactMap { $0 }
        )
    }

    private func createSettingsSection(_ title: String, _ items: [(String, String, String, Bool?)]) -> A2UIComponent {
        let sectionItems = items.map { (name, type, action, value) in
            A2UIComponent(
                type: "hstack",
                props: [
                    "spacing": .double(12),
                    "padding": .double(16),
                    "backgroundColor": .string("#FFFFFF"),
                    "cornerRadius": .double(8)
                ],
                children: [
                    A2UIComponent(
                        type: "text",
                        props: [
                            "text": .string(name),
                            "font": .string("body")
                        ]
                    ),
                    A2UIComponent(type: "spacer", props: [:]),
                    type == "toggle" ? A2UIComponent(
                        type: "toggle",
                        props: [
                            "value": .bool(value ?? false),
                            "action": .string(action)
                        ]
                    ) : A2UIComponent(
                        type: "picker",
                        props: [
                            "options": .array([
                                .string("Beginner"),
                                .string("Intermediate"),
                                .string("Advanced")
                            ]),
                            "selectedIndex": .int(1),
                            "action": .string(action)
                        ]
                    )
                ]
            )
        }

        return A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(8),
                "align": .string("leading")
            ],
            children: [
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string(title),
                        "font": .string("headline"),
                        "padding": .double(8)
                    ]
                )
            ] + sectionItems
        )
    }
}

#Preview {
    A2UIExamplesView()
}