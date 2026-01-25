import Foundation
import SwiftUI
import os.log

// MARK: - A2UI Rendering Manager
@MainActor
final class A2UIRenderingManager: ObservableObject {
    static let shared = A2UIRenderingManager()

    // Configuration constants
    private let maxRenderingDepth = 50
    private let maxComponentsPerTree = 1000
    private let memoryWarningThreshold = 50 * 1024 * 1024 // 50MB
    private let renderTimeWarningThreshold = 100.0 // milliseconds

    // Performance monitoring
    @Published var currentDepth = 0
    @Published var totalComponentsRendered = 0
    @Published var isMemoryPressureHigh = false
    @Published var averageRenderTime: Double = 0

    // Statistics tracking
    private var renderTimes: [Double] = []
    private var componentCounts: [Int] = []
    private let logger = Logger(subsystem: "com.lyo.a2ui", category: "rendering")

    private init() {
        setupMemoryPressureMonitoring()
    }

    // MARK: - Component Tree Validation

    func validateComponentTree(_ component: A2UIComponent) -> ComponentValidationResult {
        let startTime = CFAbsoluteTimeGetCurrent()

        let result = validateComponentRecursively(
            component,
            currentDepth: 0,
            componentCount: 0,
            path: [component.id]
        )

        let renderTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000

        // Track performance metrics
        recordRenderTime(renderTime)

        if renderTime > renderTimeWarningThreshold {
            logger.warning("Slow component validation: \(renderTime)ms for component tree")
        }

        return result
    }

    private func validateComponentRecursively(
        _ component: A2UIComponent,
        currentDepth: Int,
        componentCount: Int,
        path: [String]
    ) -> ComponentValidationResult {

        var currentCount = componentCount + 1

        // Check depth limit
        if currentDepth >= maxRenderingDepth {
            logger.error("Maximum rendering depth exceeded: \(currentDepth) >= \(maxRenderingDepth)")
            return .failure(.depthLimitExceeded(currentDepth, path))
        }

        // Check component count limit
        if currentCount >= maxComponentsPerTree {
            logger.error("Maximum component count exceeded: \(currentCount) >= \(maxComponentsPerTree)")
            return .failure(.componentLimitExceeded(currentCount, path))
        }

        // Check for circular references
        if path.count != Set(path).count {
            let duplicates = Set(path.filter { id in path.filter { $0 == id }.count > 1 })
            logger.error("Circular reference detected in path: \(duplicates)")
            return .failure(.circularReference(Array(duplicates), path))
        }

        // Validate children recursively
        if let children = component.children {
            for child in children {
                let childPath = path + [child.id]
                let childResult = validateComponentRecursively(
                    child,
                    currentDepth: currentDepth + 1,
                    componentCount: currentCount,
                    path: childPath
                )

                switch childResult {
                case .failure(let error):
                    return .failure(error)
                case .success(let metrics):
                    currentCount = metrics.totalComponents
                }
            }
        }

        let metrics = ComponentTreeMetrics(
            maxDepth: currentDepth + 1,
            totalComponents: currentCount,
            estimatedMemoryUsage: estimateMemoryUsage(componentCount: currentCount)
        )

        return .success(metrics)
    }

    // MARK: - Safe Rendering with Limits

    func createSafeRenderer(for component: A2UIComponent) -> AnyView {
        let validation = validateComponentTree(component)

        switch validation {
        case .success(let metrics):
            updateRenderingMetrics(metrics)
            return AnyView(SafeA2UIRenderer(component: component, renderingManager: self))

        case .failure(let error):
            logger.error("Component validation failed: \(error)")
            return AnyView(createErrorView(for: error))
        }
    }

    // MARK: - Memory Management

    private func setupMemoryPressureMonitoring() {
        let source = DispatchSource.makeMemoryPressureSource(eventMask: .all, queue: .main)

        source.setEventHandler { [weak self] in
            guard let self = self else { return }

            let event = source.mask
            if event.contains(.warning) || event.contains(.critical) {
                self.handleMemoryPressure(level: event.contains(.critical) ? .critical : .warning)
            }
        }

        source.resume()
    }

    private func handleMemoryPressure(level: MemoryPressureLevel) {
        logger.warning("Memory pressure detected: \(level)")

        DispatchQueue.main.async {
            self.isMemoryPressureHigh = (level == .critical)

            // Clear performance tracking arrays to save memory
            if level == .critical {
                self.renderTimes = Array(self.renderTimes.suffix(10)) // Keep only last 10
                self.componentCounts = Array(self.componentCounts.suffix(10))
            }
        }

        // Notify observers about memory pressure
        NotificationCenter.default.post(
            name: .a2uiMemoryPressure,
            object: nil,
            userInfo: ["level": level]
        )
    }

    private func estimateMemoryUsage(componentCount: Int) -> Int {
        // Rough estimation: 2KB per component on average
        return componentCount * 2048
    }

    // MARK: - Performance Tracking

    private func recordRenderTime(_ time: Double) {
        renderTimes.append(time)

        // Keep only last 100 measurements
        if renderTimes.count > 100 {
            renderTimes.removeFirst()
        }

        // Update average
        averageRenderTime = renderTimes.reduce(0, +) / Double(renderTimes.count)
    }

    private func updateRenderingMetrics(_ metrics: ComponentTreeMetrics) {
        currentDepth = metrics.maxDepth
        totalComponentsRendered = metrics.totalComponents
        componentCounts.append(metrics.totalComponents)

        // Keep only last 50 measurements
        if componentCounts.count > 50 {
            componentCounts.removeFirst()
        }
    }

    // MARK: - Error Views

    @ViewBuilder
    private func createErrorView(for error: ComponentValidationError) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.largeTitle)
                .foregroundColor(.red)

            Text("Component Rendering Error")
                .font(.headline)
                .foregroundColor(.primary)

            Text(error.localizedDescription)
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Button("Report Issue") {
                // In production, this would send error report
                self.logger.error("User reported rendering error: \(error)")
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(Color.blue.opacity(0.1))
            .foregroundColor(.blue)
            .cornerRadius(8)
        }
        .padding()
        .background(Color.red.opacity(0.1))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.red.opacity(0.3), lineWidth: 1)
        )
    }

    // MARK: - Performance Diagnostics

    func getPerformanceDiagnostics() -> A2UIPerformanceDiagnostics {
        return A2UIPerformanceDiagnostics(
            averageRenderTime: averageRenderTime,
            maxComponentsRendered: componentCounts.max() ?? 0,
            averageComponentCount: componentCounts.isEmpty ? 0 : componentCounts.reduce(0, +) / componentCounts.count,
            isMemoryPressureHigh: isMemoryPressureHigh,
            totalValidationsPerformed: renderTimes.count
        )
    }
}

// MARK: - Safe Renderer with Depth Tracking

struct SafeA2UIRenderer: View {
    let component: A2UIComponent
    let renderingManager: A2UIRenderingManager
    private let maxDepthPerView = 20

    @State private var currentDepth = 0

    var body: some View {
        Group {
            if currentDepth < maxDepthPerView {
                A2UIRenderer(component: component) { action in
                    // Handle actions through the action handler
                    A2UIActionHandler.shared.handleAction(
                        type: .ui_interaction,
                        payload: action.params ?? [:],
                        componentId: action.componentId
                    )
                }
                .onAppear {
                    currentDepth += 1
                }
                .onDisappear {
                    currentDepth = max(0, currentDepth - 1)
                }
            } else {
                // Depth limit reached - show truncated view
                VStack {
                    Text("Content truncated")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Button("Load More") {
                        // In production, this could trigger progressive loading
                        renderingManager.logger.info("User requested loading truncated content")
                    }
                    .font(.caption)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.blue.opacity(0.1))
                    .foregroundColor(.blue)
                    .cornerRadius(6)
                }
                .padding()
                .background(Color.gray.opacity(0.1))
                .cornerRadius(8)
            }
        }
    }
}

// MARK: - Supporting Types

enum ComponentValidationError: Error {
    case depthLimitExceeded(Int, [String])
    case componentLimitExceeded(Int, [String])
    case circularReference([String], [String])
    case memoryLimitExceeded(Int)

    var localizedDescription: String {
        switch self {
        case .depthLimitExceeded(let depth, _):
            return "Component tree too deep (\(depth) levels). This could cause performance issues."
        case .componentLimitExceeded(let count, _):
            return "Too many components (\(count)). This could cause memory issues."
        case .circularReference(let ids, _):
            return "Circular reference detected in components: \(ids.joined(separator: ", "))"
        case .memoryLimitExceeded(let usage):
            return "Estimated memory usage too high: \(usage / 1024 / 1024)MB"
        }
    }
}

enum ComponentValidationResult {
    case success(ComponentTreeMetrics)
    case failure(ComponentValidationError)
}

struct ComponentTreeMetrics {
    let maxDepth: Int
    let totalComponents: Int
    let estimatedMemoryUsage: Int
}

enum MemoryPressureLevel {
    case normal
    case warning
    case critical
}

struct A2UIPerformanceDiagnostics {
    let averageRenderTime: Double
    let maxComponentsRendered: Int
    let averageComponentCount: Int
    let isMemoryPressureHigh: Bool
    let totalValidationsPerformed: Int
}

// MARK: - Notification Extensions
extension NSNotification.Name {
    static let a2uiMemoryPressure = NSNotification.Name("A2UIMemoryPressure")
}