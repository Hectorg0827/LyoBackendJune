import Foundation
import Network
import Combine
import os.log

// MARK: - A2UI Network Manager with Circuit Breaker
@MainActor
final class A2UINetworkManager: ObservableObject {
    static let shared = A2UINetworkManager()

    // Endpoint configuration
    private let endpoints = [
        A2UIEndpoint(
            id: "local",
            baseURL: "http://127.0.0.1:8001",
            priority: 1,
            timeout: 3.0 // Faster timeout for local
        ),
        A2UIEndpoint(
            id: "production",
            baseURL: "https://lyo-backend-production-830162750094.us-central1.run.app",
            priority: 2,
            timeout: 5.0
        )
    ]

    // Circuit breaker states per endpoint
    private var circuitBreakers: [String: CircuitBreaker] = [:]

    // Health monitoring
    @Published var endpointHealth: [String: EndpointHealthStatus] = [:]
    @Published var isOnline = true
    @Published var fastestEndpoint: String?

    private let networkMonitor = NWPathMonitor()
    private let logger = Logger(subsystem: "com.lyo.a2ui", category: "network")
    private var cancellables = Set<AnyCancellable>()

    private init() {
        setupNetworkMonitoring()
        initializeCircuitBreakers()
        startHealthChecking()
    }

    // MARK: - Smart Endpoint Selection

    func loadScreen(_ screenId: String) async throws -> A2UIComponent {
        logger.info("Loading screen: \(screenId)")

        // Get healthy endpoints sorted by priority and performance
        let healthyEndpoints = getHealthyEndpoints()

        if healthyEndpoints.isEmpty {
            logger.warning("No healthy endpoints available, using mock data")
            return try await createMockComponent(for: screenId)
        }

        // Try endpoints concurrently with staggered delays
        return try await loadFromEndpointsWithFallback(
            screenId: screenId,
            endpoints: healthyEndpoints
        )
    }

    private func loadFromEndpointsWithFallback(
        screenId: String,
        endpoints: [A2UIEndpoint]
    ) async throws -> A2UIComponent {

        // Try fastest endpoint first
        if let fastest = endpoints.first {
            do {
                let result = try await loadFromEndpoint(fastest, screenId: screenId)
                updateEndpointSuccess(fastest.id)
                return result
            } catch {
                logger.warning("Fastest endpoint failed: \(error)")
                recordEndpointFailure(fastest.id, error: error)
            }
        }

        // If primary fails, try remaining endpoints concurrently
        let remainingEndpoints = Array(endpoints.dropFirst())

        return try await withThrowingTaskGroup(of: A2UIComponent.self) { group in
            var errors: [Error] = []

            // Start concurrent requests with staggered delays
            for (index, endpoint) in remainingEndpoints.enumerated() {
                group.addTask {
                    // Stagger requests by 100ms to avoid overwhelming
                    if index > 0 {
                        try await Task.sleep(nanoseconds: UInt64(index * 100_000_000))
                    }

                    do {
                        let result = try await self.loadFromEndpoint(endpoint, screenId: screenId)
                        await MainActor.run {
                            self.updateEndpointSuccess(endpoint.id)
                        }
                        return result
                    } catch {
                        await MainActor.run {
                            self.recordEndpointFailure(endpoint.id, error: error)
                        }
                        throw error
                    }
                }
            }

            // Return first successful result
            for try await result in group {
                group.cancelAll()
                return result
            }

            // All endpoints failed
            throw A2UINetworkError.allEndpointsFailed(errors)
        }
    }

    private func loadFromEndpoint(
        _ endpoint: A2UIEndpoint,
        screenId: String
    ) async throws -> A2UIComponent {

        // Check circuit breaker
        let breaker = circuitBreakers[endpoint.id]!
        try breaker.checkState()

        let url = URL(string: "\(endpoint.baseURL)/a2ui/screen/\(screenId)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = endpoint.timeout

        let requestBody = [
            "screen_id": screenId,
            "user_id": "ios_user_123",
            "context": [
                "platform": "ios",
                "version": "1.0",
                "capabilities": await A2UICapabilityManager().getSupportedCapabilities()
            ]
        ] as [String: Any]

        request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)

        let startTime = CFAbsoluteTimeGetCurrent()

        do {
            let (data, response) = try await URLSession.shared.data(for: request)

            let responseTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000

            guard let httpResponse = response as? HTTPURLResponse else {
                throw A2UINetworkError.invalidResponse
            }

            guard httpResponse.statusCode == 200 else {
                throw A2UINetworkError.httpError(httpResponse.statusCode)
            }

            // Validate response before decoding
            let validator = A2UIResponseValidator()
            let validationResult = validator.validateBackendResponse(data)

            switch validationResult {
            case .success(let componentValidation):
                let apiResponse = try JSONDecoder().decode(A2UIScreenResponse.self, from: data)

                // Log validation warnings
                for warning in componentValidation.warnings {
                    logger.warning("Component validation warning: \(warning.fullMessage)")
                }

                // Check for critical validation errors
                if !componentValidation.errors.isEmpty {
                    let errorMessages = componentValidation.errors.map { $0.fullMessage }
                    throw A2UINetworkError.validationError(errorMessages.joined(separator: "; "))
                }

                // Record successful request
                breaker.recordSuccess(responseTime: responseTime)
                updateEndpointPerformance(endpoint.id, responseTime: responseTime)

                logger.info("Successfully loaded and validated screen from \(endpoint.id) in \(responseTime)ms")

                return apiResponse.component

            case .failure(let validationError):
                logger.error("Response validation failed: \(validationError.localizedDescription)")
                throw A2UINetworkError.validationError(validationError.localizedDescription)
            }

        } catch {
            breaker.recordFailure()
            throw error
        }
    }

    // MARK: - Circuit Breaker Management

    private func initializeCircuitBreakers() {
        for endpoint in endpoints {
            circuitBreakers[endpoint.id] = CircuitBreaker(
                failureThreshold: 3,
                timeout: 30.0,
                endpointId: endpoint.id
            )
        }
    }

    private func getHealthyEndpoints() -> [A2UIEndpoint] {
        return endpoints
            .filter { endpoint in
                let breaker = circuitBreakers[endpoint.id]!
                return breaker.state != .open && isOnline
            }
            .sorted { endpoint1, endpoint2 in
                let health1 = endpointHealth[endpoint1.id] ?? .unknown
                let health2 = endpointHealth[endpoint2.id] ?? .unknown

                // Primary sort by health status
                if health1.priority != health2.priority {
                    return health1.priority < health2.priority
                }

                // Secondary sort by response time
                return health1.averageResponseTime < health2.averageResponseTime
            }
    }

    // MARK: - Health Monitoring

    private func setupNetworkMonitoring() {
        networkMonitor.pathUpdateHandler = { [weak self] path in
            DispatchQueue.main.async {
                self?.isOnline = path.status == .satisfied
                self?.logger.info("Network status changed: \(path.status)")

                if path.status == .satisfied {
                    // Network came back online - reset circuit breakers
                    self?.resetAllCircuitBreakers()
                }
            }
        }

        let queue = DispatchQueue(label: "NetworkMonitor")
        networkMonitor.start(queue: queue)
    }

    private func startHealthChecking() {
        // Perform health checks every 30 seconds
        Timer.publish(every: 30, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                Task {
                    await self?.performHealthChecks()
                }
            }
            .store(in: &cancellables)

        // Initial health check
        Task {
            await performHealthChecks()
        }
    }

    private func performHealthChecks() async {
        logger.debug("Performing endpoint health checks")

        await withTaskGroup(of: Void.self) { group in
            for endpoint in endpoints {
                group.addTask {
                    await self.checkEndpointHealth(endpoint)
                }
            }
        }

        // Update fastest endpoint
        updateFastestEndpoint()
    }

    private func checkEndpointHealth(_ endpoint: A2UIEndpoint) async {
        let url = URL(string: "\(endpoint.baseURL)/health")!
        var request = URLRequest(url: url)
        request.timeoutInterval = 2.0 // Quick health check

        let startTime = CFAbsoluteTimeGetCurrent()

        do {
            let (_, response) = try await URLSession.shared.data(for: request)

            if let httpResponse = response as? HTTPURLResponse,
               httpResponse.statusCode == 200 {

                let responseTime = (CFAbsoluteTimeGetCurrent() - startTime) * 1000

                await MainActor.run {
                    self.updateEndpointHealth(
                        endpoint.id,
                        status: .healthy,
                        responseTime: responseTime
                    )
                }
            } else {
                await MainActor.run {
                    self.updateEndpointHealth(endpoint.id, status: .unhealthy)
                }
            }

        } catch {
            await MainActor.run {
                self.updateEndpointHealth(endpoint.id, status: .unhealthy)
            }
        }
    }

    // MARK: - Performance Tracking

    private func updateEndpointSuccess(_ endpointId: String) {
        if var health = endpointHealth[endpointId] {
            health.successfulRequests += 1
            endpointHealth[endpointId] = health
        }
    }

    private func recordEndpointFailure(_ endpointId: String, error: Error) {
        if var health = endpointHealth[endpointId] {
            health.failedRequests += 1
            endpointHealth[endpointId] = health
        }

        logger.warning("Endpoint \(endpointId) failed: \(error)")
    }

    private func updateEndpointPerformance(_ endpointId: String, responseTime: Double) {
        if var health = endpointHealth[endpointId] {
            // Update rolling average response time
            let alpha = 0.3 // Smoothing factor
            health.averageResponseTime = health.averageResponseTime * (1 - alpha) + responseTime * alpha
            endpointHealth[endpointId] = health
        }
    }

    private func updateEndpointHealth(
        _ endpointId: String,
        status: EndpointHealthStatus.Status,
        responseTime: Double? = nil
    ) {
        var health = endpointHealth[endpointId] ?? EndpointHealthStatus(endpointId: endpointId)
        health.status = status
        health.lastChecked = Date()

        if let responseTime = responseTime {
            let alpha = 0.3
            health.averageResponseTime = health.averageResponseTime * (1 - alpha) + responseTime * alpha
        }

        endpointHealth[endpointId] = health
    }

    private func updateFastestEndpoint() {
        let healthyEndpoints = endpointHealth.values
            .filter { $0.status == .healthy }
            .sorted { $0.averageResponseTime < $1.averageResponseTime }

        fastestEndpoint = healthyEndpoints.first?.endpointId
    }

    private func resetAllCircuitBreakers() {
        for breaker in circuitBreakers.values {
            breaker.reset()
        }
        logger.info("All circuit breakers reset due to network recovery")
    }

    // MARK: - Mock Data Fallback

    private func createMockComponent(for screenId: String) async throws -> A2UIComponent {
        logger.info("Creating mock component for screen: \(screenId)")

        // Simulate minimal network delay
        try await Task.sleep(nanoseconds: 200_000_000) // 0.2s

        // Use existing mock logic from A2UIBackendService
        let mockService = MockA2UIBackendService()
        await mockService.loadScreen(screenId)

        guard let component = mockService.currentComponent else {
            throw A2UINetworkError.mockDataFailed
        }

        return component
    }
}

// MARK: - Circuit Breaker Implementation

class CircuitBreaker {
    enum State {
        case closed    // Normal operation
        case open      // Failing, reject requests
        case halfOpen  // Testing if service recovered
    }

    private(set) var state: State = .closed
    private let failureThreshold: Int
    private let timeout: TimeInterval
    private let endpointId: String

    private var failureCount = 0
    private var lastFailureTime: Date?
    private var responseTime: Double = 0
    private let logger = Logger(subsystem: "com.lyo.a2ui", category: "circuit-breaker")

    init(failureThreshold: Int, timeout: TimeInterval, endpointId: String) {
        self.failureThreshold = failureThreshold
        self.timeout = timeout
        self.endpointId = endpointId
    }

    func checkState() throws {
        switch state {
        case .closed:
            break // Allow request

        case .open:
            // Check if timeout period has passed
            if let lastFailure = lastFailureTime,
               Date().timeIntervalSince(lastFailure) > timeout {
                state = .halfOpen
                logger.info("Circuit breaker for \(endpointId) moved to half-open")
            } else {
                throw A2UINetworkError.circuitBreakerOpen(endpointId)
            }

        case .halfOpen:
            break // Allow one test request
        }
    }

    func recordSuccess(responseTime: Double) {
        self.responseTime = responseTime

        if state == .halfOpen {
            state = .closed
            logger.info("Circuit breaker for \(endpointId) closed after successful test")
        }

        failureCount = 0
        lastFailureTime = nil
    }

    func recordFailure() {
        failureCount += 1
        lastFailureTime = Date()

        if failureCount >= failureThreshold {
            state = .open
            logger.warning("Circuit breaker for \(endpointId) opened after \(failureCount) failures")
        }
    }

    func reset() {
        state = .closed
        failureCount = 0
        lastFailureTime = nil
    }
}

// MARK: - Supporting Types

struct A2UIEndpoint {
    let id: String
    let baseURL: String
    let priority: Int
    let timeout: TimeInterval
}

struct EndpointHealthStatus {
    enum Status {
        case healthy
        case unhealthy
        case unknown

        var priority: Int {
            switch self {
            case .healthy: return 1
            case .unknown: return 2
            case .unhealthy: return 3
            }
        }
    }

    let endpointId: String
    var status: Status = .unknown
    var averageResponseTime: Double = 1000.0 // Start with 1s default
    var successfulRequests: Int = 0
    var failedRequests: Int = 0
    var lastChecked: Date?

    init(endpointId: String) {
        self.endpointId = endpointId
    }
}

enum A2UINetworkError: Error, LocalizedError {
    case allEndpointsFailed([Error])
    case circuitBreakerOpen(String)
    case invalidResponse
    case httpError(Int)
    case mockDataFailed
    case validationError(String)

    var errorDescription: String? {
        switch self {
        case .allEndpointsFailed:
            return "All backend endpoints are currently unavailable"
        case .circuitBreakerOpen(let endpoint):
            return "Endpoint \(endpoint) is temporarily unavailable"
        case .invalidResponse:
            return "Invalid server response"
        case .httpError(let code):
            return "Server error: \(code)"
        case .mockDataFailed:
            return "Mock data fallback failed"
        case .validationError(let message):
            return "Response validation failed: \(message)"
        }
    }
}

// Mock service for network manager
@MainActor
private class MockA2UIBackendService: ObservableObject {
    @Published var currentComponent: A2UIComponent?

    func loadScreen(_ screenId: String) async {
        currentComponent = A2UIComponent(
            type: "vstack",
            props: [
                "spacing": .double(16),
                "padding": .double(20)
            ],
            children: [
                A2UIComponent(
                    type: "text",
                    props: [
                        "text": .string("Mock: \(screenId)"),
                        "font": .string("title")
                    ]
                )
            ]
        )
    }
}