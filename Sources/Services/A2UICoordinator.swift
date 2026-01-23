import SwiftUI
import Combine

// MARK: - A2UI Coordinator
// Manages A2UI state across the entire app

@MainActor
class A2UICoordinator: ObservableObject {
    @Published var isA2UIEnabled = true
    @Published var currentScreen: String = "dashboard"
    @Published var globalComponent: A2UIComponent?
    @Published var isLoading = false
    @Published var error: String?

    private let backendService = A2UIBackendService()
    private var cancellables = Set<AnyCancellable>()

    init() {
        setupBindings()
    }

    private func setupBindings() {
        // Bind backend service to coordinator
        backendService.$currentComponent
            .receive(on: DispatchQueue.main)
            .assign(to: \.globalComponent, on: self)
            .store(in: &cancellables)
    }

    // MARK: - Public Methods

    func loadScreen(_ screenId: String) {
        guard isA2UIEnabled else { return }

        currentScreen = screenId
        isLoading = true
        error = nil

        Task {
            do {
                try await backendService.loadScreen(screenId)
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

    func handleAction(_ action: A2UIAction) {
        guard isA2UIEnabled else { return }

        Task {
            await backendService.handleAction(action)
        }
    }

    func enableA2UI(_ enabled: Bool) {
        isA2UIEnabled = enabled
        if !enabled {
            globalComponent = nil
        }
    }

    func refresh() {
        loadScreen(currentScreen)
    }
}

// MARK: - A2UI Environment Key
struct A2UICoordinatorKey: EnvironmentKey {
    static let defaultValue = A2UICoordinator()
}

extension EnvironmentValues {
    var a2uiCoordinator: A2UICoordinator {
        get { self[A2UICoordinatorKey.self] }
        set { self[A2UICoordinatorKey.self] = newValue }
    }
}

// MARK: - A2UI View Modifier
struct A2UIEnabledModifier: ViewModifier {
    @StateObject private var coordinator = A2UICoordinator()

    func body(content: Content) -> some View {
        content
            .environmentObject(coordinator)
            .environment(\.a2uiCoordinator, coordinator)
    }
}

extension View {
    func withA2UI() -> some View {
        modifier(A2UIEnabledModifier())
    }
}

// MARK: - A2UI Wrapper View
// Use this to wrap existing views with A2UI capabilities
struct A2UIWrapperView<Content: View>: View {
    let content: Content
    let screenId: String

    @EnvironmentObject private var coordinator: A2UICoordinator
    @State private var showFallback = false

    init(screenId: String, @ViewBuilder content: () -> Content) {
        self.screenId = screenId
        self.content = content()
    }

    var body: some View {
        Group {
            if coordinator.isA2UIEnabled && !showFallback {
                a2uiContent
            } else {
                fallbackContent
            }
        }
        .onAppear {
            coordinator.loadScreen(screenId)
        }
    }

    @ViewBuilder
    private var a2uiContent: some View {
        if coordinator.isLoading {
            LoadingView()
        } else if let error = coordinator.error {
            ErrorView(error: error) {
                coordinator.refresh()
            } fallback: {
                showFallback = true
            }
        } else if let component = coordinator.globalComponent {
            A2UIRenderer(
                component: component,
                onAction: coordinator.handleAction
            )
        } else {
            content
        }
    }

    private var fallbackContent: some View {
        VStack {
            // Fallback indicator
            if coordinator.isA2UIEnabled {
                HStack {
                    Image(systemName: "antenna.radiowaves.left.and.right.slash")
                        .foregroundColor(.orange)
                    Text("Using offline mode")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Spacer()
                    Button("Retry") {
                        showFallback = false
                        coordinator.refresh()
                    }
                    .font(.caption)
                    .foregroundColor(.blue)
                }
                .padding(.horizontal)
            }

            content
        }
    }
}

// MARK: - Enhanced Error View
extension ErrorView {
    init(error: String, onRetry: @escaping () -> Void, fallback: @escaping () -> Void) {
        self.init(error: error) {
            onRetry()
        }
        // Note: Would need to modify ErrorView to support fallback action
    }
}