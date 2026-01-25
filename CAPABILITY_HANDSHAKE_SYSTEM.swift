import Foundation

/// A2UI Capability Handshake System
/// Ensures backend only sends UI components that iOS can render

// ═══════════════════════════════════════════════════════════════════
// MARK: - Client Capabilities
// ═══════════════════════════════════════════════════════════════════

struct A2UIClientCapabilities: Codable {
    let protocolVersion: String
    let platform: String
    let appVersion: String
    let supportedElements: [String]
    let supportedActions: [String]
    let features: A2UIFeatureFlags
    let deviceInfo: A2UIDeviceInfo
    let userTier: String                    // "free", "premium", "enterprise"

    static func current() -> A2UIClientCapabilities {
        return A2UIClientCapabilities(
            protocolVersion: "2.0.0",
            platform: "ios",
            appVersion: Bundle.main.appVersionLong,
            supportedElements: A2UIElementSupport.implemented.map { $0.rawValue },
            supportedActions: A2UIActionType.allCases.map { $0.rawValue },
            features: A2UIFeatureFlags.current(),
            deviceInfo: A2UIDeviceInfo.current(),
            userTier: UserManager.shared.currentUser?.tier.rawValue ?? "free"
        )
    }

    enum CodingKeys: String, CodingKey {
        case protocolVersion = "protocol_version"
        case platform
        case appVersion = "app_version"
        case supportedElements = "supported_elements"
        case supportedActions = "supported_actions"
        case features
        case deviceInfo = "device_info"
        case userTier = "user_tier"
    }
}

struct A2UIFeatureFlags: Codable {
    let supportsCamera: Bool
    let supportsVoiceInput: Bool
    let supportsHandwriting: Bool
    let supportsDocumentUpload: Bool
    let supportsVideoPlayback: Bool
    let supportsAudioPlayback: Bool
    let supports3D: Bool
    let supportsAR: Bool
    let maxImageWidth: Int
    let maxVideoLength: Int          // seconds
    let maxFileSize: Int             // MB

    static func current() -> A2UIFeatureFlags {
        return A2UIFeatureFlags(
            supportsCamera: UIImagePickerController.isSourceTypeAvailable(.camera),
            supportsVoiceInput: true, // We have this
            supportsHandwriting: true, // PencilKit available
            supportsDocumentUpload: true,
            supportsVideoPlayback: true,
            supportsAudioPlayback: AppConfig.isTTSEnabled,
            supports3D: false,        // Not implemented yet
            supportsAR: ARWorldTrackingConfiguration.isSupported,
            maxImageWidth: 2048,
            maxVideoLength: 600,      // 10 minutes
            maxFileSize: 100          // 100MB
        )
    }

    enum CodingKeys: String, CodingKey {
        case supportsCamera = "supports_camera"
        case supportsVoiceInput = "supports_voice_input"
        case supportsHandwriting = "supports_handwriting"
        case supportsDocumentUpload = "supports_document_upload"
        case supportsVideoPlayback = "supports_video_playback"
        case supportsAudioPlayback = "supports_audio_playback"
        case supports3D = "supports_3d"
        case supportsAR = "supports_ar"
        case maxImageWidth = "max_image_width"
        case maxVideoLength = "max_video_length"
        case maxFileSize = "max_file_size"
    }
}

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

    static func current() -> A2UIDeviceInfo {
        let screen = UIScreen.main
        return A2UIDeviceInfo(
            deviceModel: UIDevice.current.model,
            systemVersion: UIDevice.current.systemVersion,
            screenWidth: Int(screen.bounds.width),
            screenHeight: Int(screen.bounds.height),
            pixelDensity: Double(screen.scale),
            prefersDarkMode: UITraitCollection.current.userInterfaceStyle == .dark,
            locale: Locale.current.identifier,
            timezone: TimeZone.current.identifier,
            hasNotch: screen.bounds.height >= 812, // iPhone X+ detection
            memoryGB: ProcessInfo.processInfo.physicalMemory / 1_073_741_824 // Rough estimate
        )
    }

    enum CodingKeys: String, CodingKey {
        case deviceModel = "device_model"
        case systemVersion = "system_version"
        case screenWidth = "screen_width"
        case screenHeight = "screen_height"
        case pixelDensity = "pixel_density"
        case prefersDarkMode = "prefers_dark_mode"
        case locale, timezone
        case hasNotch = "has_notch"
        case memoryGB = "memory_gb"
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - Server Response
// ═══════════════════════════════════════════════════════════════════

struct A2UIServerCapabilities: Codable {
    let negotiatedVersion: String
    let supportedElements: [String]
    let fallbackMappings: [String: String]  // "model_3d" -> "image"
    let featureGating: [String: [String]]   // "premium" -> ["advanced_quiz", "ar_view"]
    let recommendations: [String]           // Suggested features to enable

    enum CodingKeys: String, CodingKey {
        case negotiatedVersion = "negotiated_version"
        case supportedElements = "supported_elements"
        case fallbackMappings = "fallback_mappings"
        case featureGating = "feature_gating"
        case recommendations
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - Capability Negotiator
// ═══════════════════════════════════════════════════════════════════

@MainActor
final class A2UICapabilityNegotiator: ObservableObject {
    static let shared = A2UICapabilityNegotiator()

    @Published private(set) var serverCapabilities: A2UIServerCapabilities?
    @Published private(set) var negotiatedVersion: String?
    @Published private(set) var isNegotiated = false
    @Published private(set) var lastNegotiation: Date?

    private let maxNegotiationAge: TimeInterval = 3600 // 1 hour

    private init() {}

    /// Negotiate capabilities with backend
    func negotiate(force: Bool = false) async throws {
        // Check if we need to renegotiate
        if !force, isNegotiated,
           let lastNegotiation = lastNegotiation,
           Date().timeIntervalSince(lastNegotiation) < maxNegotiationAge {
            return // Recent negotiation is still valid
        }

        let clientCaps = A2UIClientCapabilities.current()

        let endpoint = DynamicEndpoint(
            urlString: "/api/v1/a2ui/negotiate",
            method: .post,
            body: clientCaps
        )

        do {
            let response: A2UIServerCapabilities = try await NetworkClient.shared.request(endpoint)

            await MainActor.run {
                self.serverCapabilities = response
                self.negotiatedVersion = response.negotiatedVersion
                self.isNegotiated = true
                self.lastNegotiation = Date()
            }

            logger.info("✅ A2UI Negotiation complete: v\(response.negotiatedVersion)")
            logger.debug("Supported elements: \(response.supportedElements.count)")

        } catch {
            logger.error("❌ A2UI Negotiation failed: \(error)")
            throw A2UIError.negotiationFailed(error)
        }
    }

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
            return nil
        }
        return fallback
    }

    /// Check if user has access to premium features
    func hasAccess(to feature: String) -> Bool {
        guard let gating = serverCapabilities?.featureGating else { return true }
        let userTier = UserManager.shared.currentUser?.tier.rawValue ?? "free"
        return gating[userTier]?.contains(feature) ?? false
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - Integration with Network Client
// ═══════════════════════════════════════════════════════════════════

extension NetworkClient {
    /// All A2UI requests should include capability headers
    func requestWithCapabilities<T: Codable>(_ endpoint: EndpointType) async throws -> T {
        // Ensure we have negotiated capabilities
        if !A2UICapabilityNegotiator.shared.isNegotiated {
            try await A2UICapabilityNegotiator.shared.negotiate()
        }

        // Add capability headers to request
        var modifiedEndpoint = endpoint
        if let caps = A2UICapabilityNegotiator.shared.serverCapabilities {
            modifiedEndpoint.additionalHeaders = [
                "X-A2UI-Version": caps.negotiatedVersion,
                "X-A2UI-Platform": "ios",
                "X-User-Tier": UserManager.shared.currentUser?.tier.rawValue ?? "free"
            ]
        }

        return try await request(modifiedEndpoint)
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - Error Types
// ═══════════════════════════════════════════════════════════════════

enum A2UIError: LocalizedError {
    case negotiationFailed(Error)
    case unsupportedElement(String)
    case versionMismatch(client: String, server: String)

    var errorDescription: String? {
        switch self {
        case .negotiationFailed(let error):
            return "A2UI negotiation failed: \(error.localizedDescription)"
        case .unsupportedElement(let element):
            return "Unsupported A2UI element: \(element)"
        case .versionMismatch(let client, let server):
            return "A2UI version mismatch - Client: \(client), Server: \(server)"
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
// MARK: - Backend Integration (Python Side)
// ═══════════════════════════════════════════════════════════════════

/*
Python backend needs this endpoint:

@router.post("/a2ui/negotiate")
async def negotiate_a2ui_capabilities(
    capabilities: A2UIClientCapabilities,
    user: User = Depends(get_current_user)
) -> A2UIServerCapabilities:
    """Negotiate A2UI capabilities with client"""

    # Determine what elements to support based on:
    # - Client capabilities
    # - User tier (free/premium)
    # - Platform (iOS/Android)
    # - App version

    supported_elements = determine_supported_elements(
        client_elements=capabilities.supported_elements,
        user_tier=user.tier,
        platform=capabilities.platform
    )

    fallback_mappings = {
        # Premium -> Free fallbacks
        "advanced_quiz": "quiz_mcq",
        "ar_view": "image",
        "voice_input": "text_input",  # If voice disabled

        # Unsupported -> Basic fallbacks
        "model_3d": "image",
        "handwriting_input": "text_input",
        "camera_capture": "document_upload"
    }

    feature_gating = {
        "free": [
            "text", "image", "quiz_mcq", "course_card",
            "study_plan_basic", "homework_card"
        ],
        "premium": [
            "voice_input", "camera_capture", "advanced_quiz",
            "mistake_tracker", "ai_tutor", "unlimited_courses"
        ],
        "enterprise": [
            "all_features", "custom_branding", "analytics_dashboard"
        ]
    }

    return A2UIServerCapabilities(
        negotiated_version="2.0.0",
        supported_elements=supported_elements,
        fallback_mappings=fallback_mappings,
        feature_gating=feature_gating,
        recommendations=get_recommendations(capabilities, user)
    )
*/