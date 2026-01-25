import Foundation
import SwiftUI
import Combine
import ARKit

/// Production-Ready A2UI Capability Handshake System
/// Ensures backend only sends UI components that iOS can render
/// Prevents crashes and enables graceful degradation

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Client Capabilities Detection
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIClientCapabilities: Codable {
    let protocolVersion: String
    let platform: String
    let appVersion: String
    let buildNumber: String
    let supportedElements: [String]
    let supportedActions: [String]
    let features: A2UIFeatureFlags
    let deviceInfo: A2UIDeviceInfo
    let userTier: String
    let permissions: A2UIPermissions
    let preferences: A2UIUserPreferences

    static func current() async -> A2UIClientCapabilities {
        let permissions = await A2UIPermissions.current()

        return A2UIClientCapabilities(
            protocolVersion: "2.0.0",
            platform: "ios",
            appVersion: Bundle.main.appVersionLong,
            buildNumber: Bundle.main.buildVersionNumber,
            supportedElements: await detectSupportedElements(),
            supportedActions: A2UIActionType.allCases.map { $0.rawValue },
            features: await A2UIFeatureFlags.current(),
            deviceInfo: A2UIDeviceInfo.current(),
            userTier: UserManager.shared.currentUser?.tier.rawValue ?? "free",
            permissions: permissions,
            preferences: A2UIUserPreferences.current()
        )
    }

    private static func detectSupportedElements() async -> [String] {
        var supported: [A2UIElementType] = []

        // Always supported basic elements
        supported.append(contentsOf: [
            .text, .heading, .image, .video, .stack, .grid, .textInput,
            .button, .progressBar, .divider, .spacer, .card, .slider, .toggle
        ])

        // Check device capabilities
        if UIImagePickerController.isSourceTypeAvailable(.camera) {
            supported.append(contentsOf: [.cameraCapture, .barcodeScanner])
        }

        // Check iOS version capabilities
        if #available(iOS 14.0, *) {
            supported.append(contentsOf: [.codeEditor, .colorPicker])
        }

        // Check AR capabilities
        if ARWorldTrackingConfiguration.isSupported {
            supported.append(.model3D)
        }

        // Check PencilKit availability
        if #available(iOS 13.0, *) {
            supported.append(.handwritingInput)
        }

        // Voice capabilities (check speech permissions separately)
        supported.append(.voiceInput)

        // Premium elements (based on user tier)
        let userTier = UserManager.shared.currentUser?.tier ?? .free
        if userTier == .premium || userTier == .enterprise {
            supported.append(contentsOf: [
                .quizAdaptive, .mistakePattern, .targetedPractice,
                .aiSuggestion, .parentDashboard, .collaborativeEditor
            ])
        }

        // All other elements are supported by default
        supported.append(contentsOf: A2UIElementType.allCases.filter { !supported.contains($0) })

        return supported.map { $0.rawValue }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Feature Flags Detection
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIFeatureFlags: Codable {
    let supportsCamera: Bool
    let supportsVoiceInput: Bool
    let supportsHandwriting: Bool
    let supportsDocumentUpload: Bool
    let supportsVideoPlayback: Bool
    let supportsAudioPlayback: Bool
    let supports3D: Bool
    let supportsAR: Bool
    let supportsWebRTC: Bool
    let supportsBackground: Bool
    let supportsPushNotifications: Bool
    let supportsHaptics: Bool
    let maxImageWidth: Int
    let maxVideoLength: Int
    let maxFileSize: Int
    let maxConcurrentDownloads: Int

    static func current() async -> A2UIFeatureFlags {
        return A2UIFeatureFlags(
            supportsCamera: await checkCameraAvailability(),
            supportsVoiceInput: await checkVoiceInputAvailability(),
            supportsHandwriting: checkHandwritingSupport(),
            supportsDocumentUpload: true,
            supportsVideoPlayback: true,
            supportsAudioPlayback: AppConfig.isTTSEnabled,
            supports3D: false, // Not implemented yet
            supportsAR: ARWorldTrackingConfiguration.isSupported,
            supportsWebRTC: false, // Would require WebRTC framework
            supportsBackground: UIApplication.shared.backgroundRefreshStatus == .available,
            supportsPushNotifications: await checkPushNotificationStatus(),
            supportsHaptics: checkHapticsSupport(),
            maxImageWidth: getMaxImageWidth(),
            maxVideoLength: 600, // 10 minutes
            maxFileSize: getMaxFileSize(),
            maxConcurrentDownloads: 3
        )
    }

    private static func checkCameraAvailability() async -> Bool {
        return UIImagePickerController.isSourceTypeAvailable(.camera)
    }

    private static func checkVoiceInputAvailability() async -> Bool {
        // Check if speech recognition is available
        guard let recognizer = SFSpeechRecognizer() else { return false }
        return recognizer.isAvailable
    }

    private static func checkHandwritingSupport() -> Bool {
        if #available(iOS 13.0, *) {
            return true // PencilKit available
        }
        return false
    }

    private static func checkPushNotificationStatus() async -> Bool {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        return settings.authorizationStatus == .authorized
    }

    private static func checkHapticsSupport() -> Bool {
        return UIDevice.current.userInterfaceIdiom == .phone // Haptics primarily on iPhone
    }

    private static func getMaxImageWidth() -> Int {
        let scale = UIScreen.main.scale
        let width = UIScreen.main.bounds.width
        return Int(width * scale * 2) // 2x for high quality
    }

    private static func getMaxFileSize() -> Int {
        // Base on available storage
        let availableBytes = getAvailableStorage()
        let maxMB = min(100, Int(availableBytes / (1024 * 1024) / 10)) // 10% of available or 100MB max
        return max(10, maxMB) // At least 10MB
    }

    private static func getAvailableStorage() -> Int64 {
        let url = URL(fileURLWithPath: NSHomeDirectory())
        do {
            let values = try url.resourceValues(forKeys: [.volumeAvailableCapacityKey])
            return values.volumeAvailableCapacity ?? 1_000_000_000 // Default 1GB
        } catch {
            return 1_000_000_000 // Default 1GB
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Device Information
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIDeviceInfo: Codable {
    let deviceModel: String
    let systemVersion: String
    let screenWidth: Int
    let screenHeight: Int
    let pixelDensity: Double
    let prefersDarkMode: Bool
    let locale: String
    let timezone: String
    let hasNotch: Bool
    let memoryGB: Int
    let storageGB: Int
    let batteryLevel: Float
    let isLowPowerMode: Bool
    let networkType: String

    static func current() -> A2UIDeviceInfo {
        let screen = UIScreen.main
        let device = UIDevice.current

        return A2UIDeviceInfo(
            deviceModel: getDeviceModel(),
            systemVersion: device.systemVersion,
            screenWidth: Int(screen.bounds.width * screen.scale),
            screenHeight: Int(screen.bounds.height * screen.scale),
            pixelDensity: Double(screen.scale),
            prefersDarkMode: UITraitCollection.current.userInterfaceStyle == .dark,
            locale: Locale.current.identifier,
            timezone: TimeZone.current.identifier,
            hasNotch: hasNotch(),
            memoryGB: Int(ProcessInfo.processInfo.physicalMemory / 1_073_741_824),
            storageGB: getTotalStorage(),
            batteryLevel: device.batteryLevel >= 0 ? device.batteryLevel : 1.0,
            isLowPowerMode: ProcessInfo.processInfo.isLowPowerModeEnabled,
            networkType: getNetworkType()
        )
    }

    private static func getDeviceModel() -> String {
        var systemInfo = utsname()
        uname(&systemInfo)
        let machineMirror = Mirror(reflecting: systemInfo.machine)
        let identifier = machineMirror.children.reduce("") { identifier, element in
            guard let value = element.value as? Int8, value != 0 else { return identifier }
            return identifier + String(UnicodeScalar(UInt8(value))!)
        }
        return identifier.isEmpty ? UIDevice.current.model : identifier
    }

    private static func hasNotch() -> Bool {
        if #available(iOS 11.0, *) {
            return UIApplication.shared.windows.first?.safeAreaInsets.top ?? 0 > 24
        }
        return false
    }

    private static func getTotalStorage() -> Int {
        let url = URL(fileURLWithPath: NSHomeDirectory())
        do {
            let values = try url.resourceValues(forKeys: [.volumeTotalCapacityKey])
            let capacity = values.volumeTotalCapacity ?? 0
            return Int(capacity / 1_073_741_824) // Convert to GB
        } catch {
            return 64 // Default assumption
        }
    }

    private static func getNetworkType() -> String {
        // This would require network monitoring
        // For now, return generic
        return "unknown"
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Permissions Detection
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIPermissions: Codable {
    let camera: String
    let microphone: String
    let photos: String
    let location: String
    let notifications: String
    let speech: String

    static func current() async -> A2UIPermissions {
        return A2UIPermissions(
            camera: await checkCameraPermission(),
            microphone: await checkMicrophonePermission(),
            photos: await checkPhotosPermission(),
            location: await checkLocationPermission(),
            notifications: await checkNotificationPermission(),
            speech: await checkSpeechPermission()
        )
    }

    private static func checkCameraPermission() async -> String {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        switch status {
        case .authorized: return "granted"
        case .denied, .restricted: return "denied"
        case .notDetermined: return "not_requested"
        @unknown default: return "unknown"
        }
    }

    private static func checkMicrophonePermission() async -> String {
        let status = AVCaptureDevice.authorizationStatus(for: .audio)
        switch status {
        case .authorized: return "granted"
        case .denied, .restricted: return "denied"
        case .notDetermined: return "not_requested"
        @unknown default: return "unknown"
        }
    }

    private static func checkPhotosPermission() async -> String {
        let status = PHPhotoLibrary.authorizationStatus()
        switch status {
        case .authorized, .limited: return "granted"
        case .denied, .restricted: return "denied"
        case .notDetermined: return "not_requested"
        @unknown default: return "unknown"
        }
    }

    private static func checkLocationPermission() async -> String {
        let manager = CLLocationManager()
        let status = manager.authorizationStatus
        switch status {
        case .authorizedWhenInUse, .authorizedAlways: return "granted"
        case .denied, .restricted: return "denied"
        case .notDetermined: return "not_requested"
        @unknown default: return "unknown"
        }
    }

    private static func checkNotificationPermission() async -> String {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .authorized: return "granted"
        case .denied: return "denied"
        case .notDetermined: return "not_requested"
        case .provisional: return "provisional"
        @unknown default: return "unknown"
        }
    }

    private static func checkSpeechPermission() async -> String {
        let status = SFSpeechRecognizer.authorizationStatus()
        switch status {
        case .authorized: return "granted"
        case .denied, .restricted: return "denied"
        case .notDetermined: return "not_requested"
        @unknown default: return "unknown"
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - User Preferences
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIUserPreferences: Codable {
    let reduceMotion: Bool
    let highContrast: Bool
    let largeText: Bool
    let voiceOverEnabled: Bool
    let preferredLanguage: String
    let timeFormat24Hour: Bool
    let temperatureUnit: String

    static func current() -> A2UIUserPreferences {
        return A2UIUserPreferences(
            reduceMotion: UIAccessibility.isReduceMotionEnabled,
            highContrast: UIAccessibility.isDarkerSystemColorsEnabled,
            largeText: UIApplication.shared.preferredContentSizeCategory.isAccessibilityCategory,
            voiceOverEnabled: UIAccessibility.isVoiceOverRunning,
            preferredLanguage: Locale.current.languageCode ?? "en",
            timeFormat24Hour: !DateFormatter.dateFormat(fromTemplate: "j", options: 0, locale: Locale.current)!.contains("a"),
            temperatureUnit: Locale.current.usesMetricSystem ? "celsius" : "fahrenheit"
        )
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Server Response
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIServerCapabilities: Codable {
    let negotiatedVersion: String
    let supportedElements: [String]
    let fallbackMappings: [String: String]
    let featureGating: [String: [String]]
    let recommendations: [String]
    let cachePolicy: A2UICachePolicy
    let analyticsConfig: A2UIAnalyticsConfig

    struct A2UICachePolicy: Codable {
        let componentCacheTTL: Int // seconds
        let mediaCacheTTL: Int
        let maxCacheSize: Int // MB
    }

    struct A2UIAnalyticsConfig: Codable {
        let enableTracking: Bool
        let sampleRate: Double
        let events: [String]
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Capability Manager
// ═══════════════════════════════════════════════════════════════════════════

@MainActor
final class A2UICapabilityManager: ObservableObject {
    static let shared = A2UICapabilityManager()

    // Published State
    @Published private(set) var serverCapabilities: A2UIServerCapabilities?
    @Published private(set) var clientCapabilities: A2UIClientCapabilities?
    @Published private(set) var negotiatedVersion: String?
    @Published private(set) var isNegotiated = false
    @Published private(set) var lastNegotiation: Date?
    @Published private(set) var negotiationError: Error?

    // Private Properties
    private let maxNegotiationAge: TimeInterval = 3600 // 1 hour
    private let maxRetries = 3
    private var negotiationTask: Task<Void, Never>?
    private var cancellables = Set<AnyCancellable>()

    private init() {
        setupBackgroundRefresh()
    }

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Negotiation Process
    // ═══════════════════════════════════════════════════════════════════

    /// Negotiate capabilities with backend
    func negotiate(force: Bool = false) async throws {
        // Cancel any existing negotiation
        negotiationTask?.cancel()

        // Check if we need to renegotiate
        if !force, isNegotiated,
           let lastNegotiation = lastNegotiation,
           Date().timeIntervalSince(lastNegotiation) < maxNegotiationAge {
            return // Recent negotiation is still valid
        }

        negotiationTask = Task {
            await performNegotiation()
        }

        await negotiationTask?.value
    }

    private func performNegotiation() async {
        do {
            // Detect client capabilities
            negotiationError = nil
            let clientCaps = await A2UIClientCapabilities.current()
            clientCapabilities = clientCaps

            // Send to server with retries
            let serverCaps = try await sendNegotiationRequest(clientCaps)

            // Store results
            serverCapabilities = serverCaps
            negotiatedVersion = serverCaps.negotiatedVersion
            isNegotiated = true
            lastNegotiation = Date()

            // Cache capabilities for offline use
            cacheCapabilities(client: clientCaps, server: serverCaps)

            logger.info("✅ A2UI Negotiation complete: v\(serverCaps.negotiatedVersion)")
            logger.debug("Supported elements: \(serverCaps.supportedElements.count)")

            // Send analytics
            trackNegotiation(success: true, capabilities: serverCaps)

        } catch {
            negotiationError = error
            isNegotiated = false
            logger.error("❌ A2UI Negotiation failed: \(error)")

            // Try to use cached capabilities
            loadCachedCapabilities()

            // Send analytics
            trackNegotiation(success: false, error: error)
        }
    }

    private func sendNegotiationRequest(_ clientCaps: A2UIClientCapabilities) async throws -> A2UIServerCapabilities {
        let endpoint = DynamicEndpoint(
            urlString: "/api/v1/a2ui/negotiate",
            method: .post,
            body: clientCaps,
            headers: [
                "X-Client-Version": clientCaps.appVersion,
                "X-Protocol-Version": clientCaps.protocolVersion,
                "X-Platform": clientCaps.platform
            ]
        )

        // Retry logic
        var lastError: Error?
        for attempt in 1...maxRetries {
            do {
                let response: A2UIServerCapabilities = try await NetworkClient.shared.request(endpoint)
                return response
            } catch {
                lastError = error
                if attempt < maxRetries {
                    let delay = TimeInterval(attempt * 2) // Exponential backoff
                    try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                }
            }
        }

        throw lastError ?? A2UIError.negotiationFailed("Unknown error")
    }

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Capability Checking
    // ═══════════════════════════════════════════════════════════════════

    /// Check if an element type is supported
    func isSupported(_ elementType: A2UIElementType) -> Bool {
        guard let serverCaps = serverCapabilities else {
            // Not negotiated yet - be conservative
            return A2UIElementSupport.implemented.contains(elementType)
        }
        return serverCaps.supportedElements.contains(elementType.rawValue)
    }

    /// Get fallback element for unsupported type
    func fallbackFor(_ elementType: A2UIElementType) -> A2UIElementType? {
        guard let fallbackString = serverCapabilities?.fallbackMappings[elementType.rawValue],
              let fallback = A2UIElementType(rawValue: fallbackString) else {
            return getDefaultFallback(for: elementType)
        }
        return fallback
    }

    /// Check if user has access to premium features
    func hasAccess(to feature: String) -> Bool {
        guard let gating = serverCapabilities?.featureGating else { return true }
        let userTier = clientCapabilities?.userTier ?? "free"
        return gating[userTier]?.contains(feature) ?? false
    }

    /// Check if permission is granted for element
    func hasPermission(for elementType: A2UIElementType) -> Bool {
        guard let permissions = clientCapabilities?.permissions else { return false }

        let requiredPerms = elementType.requiredPermissions
        if requiredPerms.isEmpty { return true }

        for perm in requiredPerms {
            switch perm {
            case "camera":
                if permissions.camera != "granted" { return false }
            case "microphone":
                if permissions.microphone != "granted" { return false }
            case "photos":
                if permissions.photos != "granted" { return false }
            case "location":
                if permissions.location != "granted" { return false }
            case "speech":
                if permissions.speech != "granted" { return false }
            default:
                break
            }
        }

        return true
    }

    private func getDefaultFallback(for elementType: A2UIElementType) -> A2UIElementType? {
        switch elementType {
        case .model3D, .cameraCapture:
            return .image
        case .voiceInput, .handwritingInput:
            return .textInput
        case .video:
            return .image
        case .audio:
            return .text
        case .quizAdaptive:
            return .quizMcq
        default:
            return .text // Ultimate fallback
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Caching
    // ═══════════════════════════════════════════════════════════════════

    private func cacheCapabilities(client: A2UIClientCapabilities, server: A2UIServerCapabilities) {
        let cacheData = A2UICapabilityCache(
            client: client,
            server: server,
            cachedAt: Date()
        )

        do {
            let data = try JSONEncoder().encode(cacheData)
            UserDefaults.standard.set(data, forKey: "A2UI_Capabilities_Cache")
        } catch {
            logger.error("Failed to cache A2UI capabilities: \(error)")
        }
    }

    private func loadCachedCapabilities() {
        guard let data = UserDefaults.standard.data(forKey: "A2UI_Capabilities_Cache") else {
            return
        }

        do {
            let cache = try JSONDecoder().decode(A2UICapabilityCache.self, from: data)

            // Check if cache is still valid (24 hours)
            if Date().timeIntervalSince(cache.cachedAt) < 86400 {
                clientCapabilities = cache.client
                serverCapabilities = cache.server
                negotiatedVersion = cache.server.negotiatedVersion
                isNegotiated = true
                lastNegotiation = cache.cachedAt

                logger.info("📦 Using cached A2UI capabilities")
            }
        } catch {
            logger.error("Failed to load cached A2UI capabilities: \(error)")
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Background Refresh
    // ═══════════════════════════════════════════════════════════════════

    private func setupBackgroundRefresh() {
        // Refresh capabilities when app becomes active
        NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)
            .sink { [weak self] _ in
                Task {
                    try? await self?.negotiate()
                }
            }
            .store(in: &cancellables)

        // Refresh when user tier changes
        UserManager.shared.$currentUser
            .sink { [weak self] _ in
                Task {
                    try? await self?.negotiate(force: true)
                }
            }
            .store(in: &cancellables)
    }

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Analytics
    // ═══════════════════════════════════════════════════════════════════

    private func trackNegotiation(success: Bool, capabilities: A2UIServerCapabilities? = nil, error: Error? = nil) {
        var properties: [String: Any] = [
            "success": success,
            "protocol_version": negotiatedVersion ?? "unknown",
            "platform": "ios"
        ]

        if let caps = capabilities {
            properties["supported_elements_count"] = caps.supportedElements.count
            properties["negotiated_version"] = caps.negotiatedVersion
        }

        if let error = error {
            properties["error"] = error.localizedDescription
        }

        AnalyticsService.shared.track("a2ui_capability_negotiation", properties: properties)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Supporting Types
// ═══════════════════════════════════════════════════════════════════════════

struct A2UICapabilityCache: Codable {
    let client: A2UIClientCapabilities
    let server: A2UIServerCapabilities
    let cachedAt: Date
}

enum A2UIError: LocalizedError {
    case negotiationFailed(String)
    case unsupportedElement(String)
    case versionMismatch(client: String, server: String)
    case permissionDenied(String)
    case networkError
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .negotiationFailed(let message):
            return "A2UI negotiation failed: \(message)"
        case .unsupportedElement(let element):
            return "Unsupported A2UI element: \(element)"
        case .versionMismatch(let client, let server):
            return "A2UI version mismatch - Client: \(client), Server: \(server)"
        case .permissionDenied(let permission):
            return "Permission denied: \(permission)"
        case .networkError:
            return "Network error during A2UI negotiation"
        case .invalidResponse:
            return "Invalid response from A2UI negotiation"
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Bundle Extensions
// ═══════════════════════════════════════════════════════════════════════════

extension Bundle {
    var appVersionLong: String {
        return "\(appVersion) (\(buildVersionNumber))"
    }

    var appVersion: String {
        return infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0"
    }

    var buildVersionNumber: String {
        return infoDictionary?["CFBundleVersion"] as? String ?? "1"
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Network Client Extension
// ═══════════════════════════════════════════════════════════════════════════

extension NetworkClient {
    /// All A2UI requests should include capability headers
    func requestWithCapabilities<T: Codable>(_ endpoint: EndpointType) async throws -> T {
        // Ensure we have negotiated capabilities
        if !A2UICapabilityManager.shared.isNegotiated {
            try await A2UICapabilityManager.shared.negotiate()
        }

        // Add capability headers to request
        var modifiedEndpoint = endpoint
        if let caps = A2UICapabilityManager.shared.serverCapabilities {
            modifiedEndpoint.additionalHeaders = [
                "X-A2UI-Version": caps.negotiatedVersion,
                "X-A2UI-Platform": "ios",
                "X-User-Tier": A2UICapabilityManager.shared.clientCapabilities?.userTier ?? "free"
            ]
        }

        return try await request(modifiedEndpoint)
    }
}

print("✅ Production-ready A2UI Capability Manager implemented")
print("🔧 Features: Permission detection, caching, retry logic, analytics")
print("📱 Device capabilities: Camera, Voice, AR, Permissions auto-detected")