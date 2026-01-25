import XCTest
import SwiftUI
import os.log

// MARK: - A2UI Stress Tests
@MainActor
class A2UIStressTest: XCTestCase {

    private var renderingManager: A2UIRenderingManager!
    private var actionHandler: A2UIActionHandler!
    private var networkManager: A2UINetworkManager!
    private let logger = Logger(subsystem: "com.lyo.a2ui", category: "stress-test")

    override func setUp() async throws {
        try await super.setUp()

        renderingManager = A2UIRenderingManager.shared
        actionHandler = A2UIActionHandler.shared
        networkManager = A2UINetworkManager.shared

        // Clear any existing state
        actionHandler.clearQueue()
    }

    override func tearDown() async throws {
        // Clean up after tests
        actionHandler.clearQueue()
        try await super.tearDown()
    }

    // MARK: - Component Tree Stress Tests

    func testExtremelyDeepComponentTree() throws {
        logger.info("Testing extremely deep component tree (200+ levels)")

        // Create a component tree with 200 nested levels
        let deepTree = createDeepNestedTree(depth: 200)

        let startTime = CFAbsoluteTimeGetCurrent()
        let validation = renderingManager.validateComponentTree(deepTree)
        let validationTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000

        logger.info("Deep tree validation took: \(validationTime)ms")

        switch validation {
        case .success:
            XCTFail("Deep tree should have been rejected due to depth limit")

        case .failure(let error):
            // Should fail due to depth limit
            switch error {
            case .depthLimitExceeded(let depth, _):
                XCTAssertLessThanOrEqual(depth, 50, "Should stop at max depth of 50")
                XCTAssertLessThan(validationTime, 100, "Validation should complete quickly even for deep trees")

            default:
                XCTFail("Expected depth limit exceeded error, got: \(error)")
            }
        }
    }

    func testMassiveComponentCount() throws {
        logger.info("Testing massive component count (5000+ components)")

        // Create a flat tree with 5000 components
        let massiveTree = createMassiveComponentTree(componentCount: 5000)

        let startTime = CFAbsoluteTimeGetCurrent()
        let validation = renderingManager.validateComponentTree(massiveTree)
        let validationTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000

        logger.info("Massive tree validation took: \(validationTime)ms")

        switch validation {
        case .success:
            XCTFail("Massive tree should have been rejected due to component limit")

        case .failure(let error):
            switch error {
            case .componentLimitExceeded(let count, _):
                XCTAssertLessThanOrEqual(count, 1000, "Should stop at max component count")
                XCTAssertLessThan(validationTime, 200, "Validation should be fast even for massive trees")

            default:
                XCTFail("Expected component limit exceeded error, got: \(error)")
            }
        }
    }

    func testCircularReferenceDetection() throws {
        logger.info("Testing circular reference detection")

        // Create component tree with circular references
        let circularTree = createCircularReferenceTree()

        let validation = renderingManager.validateComponentTree(circularTree)

        switch validation {
        case .success:
            XCTFail("Circular reference should have been detected")

        case .failure(let error):
            switch error {
            case .circularReference(let duplicates, _):
                XCTAssertFalse(duplicates.isEmpty, "Should detect circular reference")

            default:
                XCTFail("Expected circular reference error, got: \(error)")
            }
        }
    }

    func testOptimalComponentTreePerformance() throws {
        logger.info("Testing optimal component tree performance")

        // Create a reasonable component tree (within limits)
        let optimalTree = createOptimalComponentTree()

        let startTime = CFAbsoluteTimeGetCurrent()
        let validation = renderingManager.validateComponentTree(optimalTree)
        let validationTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000

        logger.info("Optimal tree validation took: \(validationTime)ms")

        switch validation {
        case .success(let metrics):
            XCTAssertLessThanOrEqual(metrics.maxDepth, 50)
            XCTAssertLessThanOrEqual(metrics.totalComponents, 1000)
            XCTAssertLessThan(validationTime, 50, "Optimal trees should validate very quickly")

            // Test actual rendering performance
            let renderStartTime = CFAbsoluteTimeGetCurrent()
            let renderer = renderingManager.createSafeRenderer(for: optimalTree)
            let renderTime = (CFAbsoluteTimeGetCurrent() - renderStartTime) * 1000

            logger.info("Optimal tree rendering took: \(renderTime)ms")
            XCTAssertLessThan(renderTime, 10, "Rendering should be under 10ms for optimal trees")

        case .failure(let error):
            XCTFail("Optimal tree should validate successfully: \(error)")
        }
    }

    // MARK: - Action Queue Stress Tests

    func testHighFrequencyActionBurst() async throws {
        logger.info("Testing high-frequency action burst (100 actions)")

        let startTime = CFAbsoluteTimeGetCurrent()

        // Fire 100 rapid UI interactions
        for i in 0..<100 {
            actionHandler.handleUIInteraction(
                componentId: "stress_button_\(i)",
                payload: ["action": "rapid_click", "index": i]
            )
        }

        // Wait for processing
        var attempts = 0
        while actionHandler.isProcessing && attempts < 50 {
            try await Task.sleep(nanoseconds: 100_000_000) // 0.1s
            attempts += 1
        }

        let totalTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000
        logger.info("100 rapid actions processed in: \(totalTime)ms")

        XCTAssertFalse(actionHandler.isProcessing, "All actions should be processed")
        XCTAssertLessThan(totalTime, 5000, "Should handle 100 actions in under 5 seconds")

        let diagnostics = actionHandler.getQueueDiagnostics()
        XCTAssertEqual(diagnostics.totalQueued, 0, "Queue should be empty after processing")
    }

    func testConcurrentActionTypes() async throws {
        logger.info("Testing concurrent action types")

        let startTime = CFAbsoluteTimeGetCurrent()

        // Mix of different priority actions
        await withTaskGroup(of: Void.self) { group in

            // High priority UI actions
            group.addTask {
                for i in 0..<20 {
                    self.actionHandler.handleUIInteraction(
                        componentId: "ui_\(i)",
                        payload: ["type": "ui"]
                    )
                }
            }

            // Normal priority navigation
            group.addTask {
                for i in 0..<10 {
                    self.actionHandler.handleNavigation(
                        to: "screen_\(i)",
                        payload: ["type": "nav"]
                    )
                }
            }

            // Low priority background tasks
            group.addTask {
                for i in 0..<30 {
                    self.actionHandler.handleBackgroundTask(
                        "analytics_\(i)",
                        payload: ["type": "background"]
                    )
                }
            }
        }

        // Wait for all processing to complete
        var attempts = 0
        while actionHandler.isProcessing && attempts < 100 {
            try await Task.sleep(nanoseconds: 100_000_000) // 0.1s
            attempts += 1
        }

        let totalTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000
        logger.info("60 concurrent mixed actions processed in: \(totalTime)ms")

        XCTAssertFalse(actionHandler.isProcessing, "All concurrent actions should be processed")
        XCTAssertLessThan(totalTime, 10000, "Should handle 60 concurrent actions in under 10 seconds")
    }

    func testActionQueueCapacityManagement() async throws {
        logger.info("Testing action queue capacity management")

        // Fill queue beyond capacity (50 items)
        for i in 0..<75 {
            actionHandler.handleBackgroundTask(
                "capacity_test_\(i)",
                payload: ["index": i, "priority": i < 25 ? "low" : "normal"]
            )
        }

        // Check that queue respects capacity limits
        let diagnostics = actionHandler.getQueueDiagnostics()
        XCTAssertLessThanOrEqual(diagnostics.totalQueued, 50, "Queue should not exceed capacity")

        logger.info("Queue managed capacity: \(diagnostics.totalQueued)/50")
    }

    // MARK: - Memory Stress Tests

    func testMemoryPressureSimulation() async throws {
        logger.info("Testing memory pressure response")

        // Create many component trees to simulate memory pressure
        var components: [A2UIComponent] = []
        for i in 0..<100 {
            components.append(createMediumComponentTree(id: "memory_test_\(i)"))
        }

        // Force memory pressure notification
        NotificationCenter.default.post(
            name: .a2uiMemoryPressure,
            object: nil,
            userInfo: ["level": MemoryPressureLevel.warning]
        )

        // Give system time to respond
        try await Task.sleep(nanoseconds: 500_000_000) // 0.5s

        // System should still be responsive
        let quickTree = createSimpleComponentTree()
        let validation = renderingManager.validateComponentTree(quickTree)

        switch validation {
        case .success:
            logger.info("System remained responsive under memory pressure")
        case .failure:
            XCTFail("System should remain functional under memory pressure")
        }

        // Clean up
        components.removeAll()
    }

    // MARK: - Network Stress Tests

    func testEndpointFailoverSpeed() async throws {
        logger.info("Testing endpoint failover speed")

        let startTime = CFAbsoluteTimeGetCurrent()

        // This will hit circuit breakers and fall back to mock data
        do {
            let component = try await networkManager.loadScreen("stress_test_screen")
            let totalTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000

            logger.info("Failover to mock data took: \(totalTime)ms")
            XCTAssertLessThan(totalTime, 5000, "Failover should complete in under 5 seconds")
            XCTAssertNotNil(component)

        } catch {
            XCTFail("Network manager should fall back to mock data: \(error)")
        }
    }

    // MARK: - Integration Stress Tests

    func testFullSystemStress() async throws {
        logger.info("Testing full system under stress")

        let startTime = CFAbsoluteTimeGetCurrent()

        // Concurrent operations across all systems
        await withTaskGroup(of: Void.self) { group in

            // Component validation stress
            group.addTask {
                for i in 0..<10 {
                    let tree = self.createMediumComponentTree(id: "stress_\(i)")
                    let _ = self.renderingManager.validateComponentTree(tree)
                }
            }

            // Action processing stress
            group.addTask {
                for i in 0..<50 {
                    self.actionHandler.handleAction(
                        type: .custom,
                        payload: ["stress_action": i],
                        priority: i % 3 == 0 ? .high : .normal
                    )
                }
            }

            // Network operations
            group.addTask {
                for _ in 0..<5 {
                    do {
                        let _ = try await self.networkManager.loadScreen("stress_test")
                    } catch {
                        // Expected to fail and fall back to mock
                    }
                }
            }
        }

        let totalTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000
        logger.info("Full system stress test completed in: \(totalTime)ms")

        // System should still be responsive
        XCTAssertLessThan(totalTime, 30000, "Full stress test should complete in under 30 seconds")

        // Get final diagnostics
        let renderingDiagnostics = renderingManager.getPerformanceDiagnostics()
        let actionDiagnostics = actionHandler.getQueueDiagnostics()

        logger.info("Final diagnostics - Rendering: \(renderingDiagnostics.averageRenderTime)ms avg, Actions: \(actionDiagnostics.totalQueued) queued")
    }

    // MARK: - Helper Methods

    private func createDeepNestedTree(depth: Int) -> A2UIComponent {
        var component = A2UIComponent(
            id: "deep_leaf",
            type: "text",
            props: ["text": .string("Deep nested content")]
        )

        for i in (0..<depth).reversed() {
            component = A2UIComponent(
                id: "deep_\(i)",
                type: "vstack",
                props: ["spacing": .double(8)],
                children: [component]
            )
        }

        return component
    }

    private func createMassiveComponentTree(componentCount: Int) -> A2UIComponent {
        let children = (0..<componentCount).map { i in
            A2UIComponent(
                id: "massive_\(i)",
                type: "text",
                props: ["text": .string("Item \(i)")]
            )
        }

        return A2UIComponent(
            id: "massive_root",
            type: "vstack",
            props: ["spacing": .double(4)],
            children: children
        )
    }

    private func createCircularReferenceTree() -> A2UIComponent {
        // Create a tree with duplicate IDs (simulating circular reference)
        let child1 = A2UIComponent(
            id: "circular_node",
            type: "text",
            props: ["text": .string("Child 1")]
        )

        let child2 = A2UIComponent(
            id: "circular_node", // Duplicate ID
            type: "text",
            props: ["text": .string("Child 2")]
        )

        return A2UIComponent(
            id: "circular_root",
            type: "vstack",
            children: [child1, child2]
        )
    }

    private func createOptimalComponentTree() -> A2UIComponent {
        // Create a reasonable tree: 4 levels deep, ~50 components
        let leafComponents = (0..<10).map { i in
            A2UIComponent(
                id: "leaf_\(i)",
                type: "text",
                props: ["text": .string("Leaf \(i)")]
            )
        }

        let level2Components = (0..<5).map { i in
            A2UIComponent(
                id: "level2_\(i)",
                type: "hstack",
                props: ["spacing": .double(8)],
                children: Array(leafComponents.prefix(2))
            )
        }

        let level1Components = (0..<3).map { i in
            A2UIComponent(
                id: "level1_\(i)",
                type: "vstack",
                props: ["spacing": .double(12)],
                children: Array(level2Components.prefix(2))
            )
        }

        return A2UIComponent(
            id: "optimal_root",
            type: "scroll",
            props: ["direction": .string("vertical")],
            children: level1Components
        )
    }

    private func createMediumComponentTree(id: String) -> A2UIComponent {
        let children = (0..<20).map { i in
            A2UIComponent(
                id: "\(id)_child_\(i)",
                type: "text",
                props: ["text": .string("Medium tree item \(i)")]
            )
        }

        return A2UIComponent(
            id: id,
            type: "vstack",
            props: ["spacing": .double(8)],
            children: children
        )
    }

    private func createSimpleComponentTree() -> A2UIComponent {
        return A2UIComponent(
            id: "simple_tree",
            type: "text",
            props: ["text": .string("Simple component")]
        )
    }
}

// MARK: - Performance Measurement Extension
extension A2UIStressTest {

    func testRenderingPerformanceBenchmark() throws {
        logger.info("Benchmarking rendering performance across different tree sizes")

        let treeSizes = [10, 50, 100, 200, 500]
        var results: [(size: Int, time: Double, success: Bool)] = []

        for size in treeSizes {
            let tree = createComponentTreeOfSize(size)

            let startTime = CFAbsoluteTimeGetCurrent()
            let validation = renderingManager.validateComponentTree(tree)
            let validationTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000

            let success = validation.isValid
            results.append((size: size, time: validationTime, success: success))

            logger.info("Tree size \(size): \(validationTime)ms, success: \(success)")
        }

        // Print benchmark results
        print("\n=== A2UI Rendering Performance Benchmark ===")
        print("Tree Size | Time (ms) | Success | Notes")
        print("----------|-----------|---------|-------")

        for result in results {
            let notes = result.success ? "✅" : "❌ (exceeded limits)"
            print(String(format: "%9d | %9.2f | %7s | %s",
                         result.size, result.time,
                         result.success ? "Yes" : "No", notes))
        }
        print("==========================================\n")

        // Assertions
        let validResults = results.filter { $0.success }
        XCTAssertFalse(validResults.isEmpty, "At least some tree sizes should be valid")

        // All valid results should be reasonably fast
        for result in validResults {
            XCTAssertLessThan(result.time, 100, "Validation for \(result.size) components should be under 100ms")
        }
    }

    private func createComponentTreeOfSize(_ size: Int) -> A2UIComponent {
        if size <= 50 {
            // Create flat tree (within limits)
            let children = (0..<size).map { i in
                A2UIComponent(
                    id: "benchmark_\(i)",
                    type: "text",
                    props: ["text": .string("Item \(i)")]
                )
            }

            return A2UIComponent(
                id: "benchmark_root",
                type: "vstack",
                children: children
            )
        } else {
            // Create nested tree (may exceed limits)
            return createNestedTreeOfSize(size)
        }
    }

    private func createNestedTreeOfSize(_ targetSize: Int) -> A2UIComponent {
        var currentSize = 1
        var component = A2UIComponent(
            id: "nested_leaf",
            type: "text",
            props: ["text": .string("Leaf")]
        )

        var level = 0
        while currentSize < targetSize {
            let childrenCount = min(10, targetSize - currentSize)
            let children = (0..<childrenCount).map { i in
                A2UIComponent(
                    id: "nested_\(level)_\(i)",
                    type: "text",
                    props: ["text": .string("Level \(level) Item \(i)")]
                )
            }

            component = A2UIComponent(
                id: "nested_container_\(level)",
                type: "vstack",
                children: children + [component]
            )

            currentSize += childrenCount + 1
            level += 1
        }

        return component
    }
}