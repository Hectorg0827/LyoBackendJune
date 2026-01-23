import SwiftUI

@main
struct LyoApp: App {
    @StateObject private var a2uiCoordinator = A2UICoordinator()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(a2uiCoordinator)
                .environment(\.a2uiCoordinator, a2uiCoordinator)
                .onAppear {
                    // Initialize A2UI system
                    a2uiCoordinator.loadScreen("dashboard")
                }
        }
    }
}

struct ContentView: View {
    @EnvironmentObject private var a2uiCoordinator: A2UICoordinator
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            // Main Dashboard - A2UI enabled
            A2UIWrapperView(screenId: "dashboard") {
                StaticDashboardView()
            }
            .tabItem {
                Image(systemName: "house.fill")
                Text("Home")
            }
            .tag(0)

            // Learning - A2UI enabled courses
            A2UIWrapperView(screenId: "course") {
                StaticLearningView()
            }
            .tabItem {
                Image(systemName: "book.fill")
                Text("Learn")
            }
            .tag(1)

            // Chat - Full A2UI integration
            NavigationView {
                DynamicChatView()
            }
            .tabItem {
                Image(systemName: "bubble.left.and.bubble.right.fill")
                Text("Chat")
            }
            .tag(2)

            // Practice - A2UI enabled quizzes
            A2UIWrapperView(screenId: "quiz") {
                StaticPracticeView()
            }
            .tabItem {
                Image(systemName: "questionmark.circle.fill")
                Text("Practice")
            }
            .tag(3)

            // Profile - Settings with A2UI
            A2UIWrapperView(screenId: "settings") {
                StaticProfileView()
            }
            .tabItem {
                Image(systemName: "person.fill")
                Text("Profile")
            }
            .tag(4)
        }
        .onChange(of: selectedTab) { tab in
            // Update A2UI screen when tab changes
            let screenMap = [
                0: "dashboard",
                1: "course",
                2: "chat",
                3: "quiz",
                4: "settings"
            ]

            if let screenId = screenMap[tab] {
                a2uiCoordinator.loadScreen(screenId)
            }
        }
    }
}

// MARK: - Fallback Static Views
// These are shown when A2UI is disabled or fails to load

struct StaticDashboardView: View {
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    // Header
                    VStack {
                        Text("👋 Welcome back!")
                            .font(.title)
                            .fontWeight(.bold)

                        Text("Ready to continue learning?")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    .padding()

                    // Stats
                    HStack(spacing: 20) {
                        StatCard(title: "Courses", value: "12", icon: "book.fill")
                        StatCard(title: "Progress", value: "87%", icon: "chart.bar.fill")
                        StatCard(title: "Streak", value: "5 days", icon: "flame.fill")
                    }

                    // Continue Learning
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Continue Learning")
                            .font(.headline)
                            .padding(.horizontal)

                        CourseCard(
                            title: "iOS Development",
                            description: "Build your first iOS app",
                            progress: 0.68
                        )

                        CourseCard(
                            title: "Machine Learning",
                            description: "AI fundamentals",
                            progress: 0.25
                        )
                    }
                }
                .padding()
            }
            .navigationTitle("Dashboard")
        }
    }
}

struct StaticLearningView: View {
    var body: some View {
        NavigationView {
            List {
                Section("Current Courses") {
                    CourseRow(title: "iOS Development", progress: 0.68)
                    CourseRow(title: "Machine Learning", progress: 0.25)
                    CourseRow(title: "SwiftUI Advanced", progress: 0.15)
                }

                Section("Recommended") {
                    CourseRow(title: "Python Basics", progress: 0.0)
                    CourseRow(title: "Data Science", progress: 0.0)
                }
            }
            .navigationTitle("Learning")
        }
    }
}

struct StaticPracticeView: View {
    var body: some View {
        NavigationView {
            VStack(spacing: 20) {
                Text("📝 Practice Mode")
                    .font(.title2)
                    .fontWeight(.bold)

                Text("Test your knowledge with interactive quizzes")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)

                VStack(spacing: 16) {
                    Button("Swift Fundamentals Quiz") {
                        // Start quiz
                    }
                    .buttonStyle(.borderedProminent)

                    Button("iOS Development Quiz") {
                        // Start quiz
                    }
                    .buttonStyle(.borderedProminent)

                    Button("Random Practice") {
                        // Random quiz
                    }
                    .buttonStyle(.bordered)
                }
                .padding()

                Spacer()
            }
            .padding()
            .navigationTitle("Practice")
        }
    }
}

struct StaticProfileView: View {
    var body: some View {
        NavigationView {
            Form {
                Section("Account") {
                    HStack {
                        Image(systemName: "person.circle.fill")
                            .font(.title)
                        VStack(alignment: .leading) {
                            Text("Learning Enthusiast")
                                .font(.headline)
                            Text("learner@example.com")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                Section("Preferences") {
                    Toggle("Dark Mode", isOn: .constant(false))
                    Toggle("Notifications", isOn: .constant(true))
                    Toggle("Auto-play Videos", isOn: .constant(false))
                }

                Section("Learning") {
                    HStack {
                        Text("Difficulty Level")
                        Spacer()
                        Text("Intermediate")
                            .foregroundColor(.secondary)
                    }

                    HStack {
                        Text("Daily Goal")
                        Spacer()
                        Text("30 minutes")
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("Profile")
        }
    }
}

// MARK: - Supporting Views

struct StatCard: View {
    let title: String
    let value: String
    let icon: String

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundColor(.blue)

            Text(value)
                .font(.title2)
                .fontWeight(.bold)

            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

struct CourseCard: View {
    let title: String
    let description: String
    let progress: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.headline)

                Text(description)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            ProgressView(value: progress)
                .progressViewStyle(.linear)

            Text("\(Int(progress * 100))% Complete")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

struct CourseRow: View {
    let title: String
    let progress: Double

    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(title)
                    .font(.headline)

                ProgressView(value: progress)
                    .progressViewStyle(.linear)
            }

            Spacer()

            Text("\(Int(progress * 100))%")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

#Preview {
    ContentView()
        .withA2UI()
}