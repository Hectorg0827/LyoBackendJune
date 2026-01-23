import SwiftUI

// MARK: - Dynamic Main View with A2UI Integration
struct DynamicMainView: View {
    @StateObject private var a2uiService = A2UIBackendService()
    @State private var isLoading = true
    @State private var currentScreen = "dashboard"
    @State private var error: String?

    var body: some View {
        NavigationView {
            Group {
                if isLoading {
                    LoadingView()
                } else if let error = error {
                    ErrorView(error: error) {
                        loadCurrentScreen()
                    }
                } else if let component = a2uiService.currentComponent {
                    A2UIRenderer(
                        component: component,
                        onAction: handleAction
                    )
                    .padding()
                } else {
                    EmptyStateView()
                }
            }
            .navigationTitle("Lyo")
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    // Screen navigation menu
                    Menu {
                        ForEach(a2uiService.availableScreens, id: \.self) { screen in
                            Button(screen.capitalized) {
                                navigateToScreen(screen)
                            }
                        }
                    } label: {
                        Image(systemName: "square.grid.3x3")
                    }

                    // Refresh button
                    Button {
                        loadCurrentScreen()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
        }
        .onAppear {
            loadCurrentScreen()
        }
        .refreshable {
            loadCurrentScreen()
        }
    }

    private func loadCurrentScreen() {
        isLoading = true
        error = nil

        Task {
            do {
                try await a2uiService.loadScreen(currentScreen)
                await MainActor.run {
                    isLoading = false
                }
            } catch {
                await MainActor.run {
                    self.error = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }

    private func navigateToScreen(_ screen: String) {
        currentScreen = screen
        loadCurrentScreen()
    }

    private func handleAction(_ action: A2UIAction) {
        Task {
            await a2uiService.handleAction(action)
        }
    }
}

// MARK: - Supporting Views

struct LoadingView: View {
    var body: some View {
        VStack(spacing: 20) {
            ProgressView()
                .scaleEffect(1.5)

            Text("Loading...")
                .font(.headline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct EmptyStateView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "questionmark.square.dashed")
                .font(.system(size: 60))
                .foregroundColor(.secondary)

            Text("No Content Available")
                .font(.headline)

            Text("Please try refreshing or selecting a different screen.")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    DynamicMainView()
}