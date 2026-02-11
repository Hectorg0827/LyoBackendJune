import Foundation

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Lyo API Endpoints
// ═══════════════════════════════════════════════════════════════════════════

/// Centralized endpoint configuration for Lyo backend communication
/// Replaces all hardcoded URL strings throughout the codebase
enum Endpoints {
    
    // MARK: - Environment URLs
    
    /// Development server (local)
    static let development = URL(string: "http://localhost:8000")!
    
    /// Staging server
    static let staging = URL(string: "https://staging-lyobackend3-668039192373.us-central1.run.app")!
    
    /// Production server
    static let production = URL(string: "https://lyobackend3-668039192373.us-central1.run.app")!
    
    // MARK: - Current Environment
    
    /// Returns the base URL for the current build configuration
    static var current: URL {
        #if DEBUG
        // In debug, check for environment override
        if let override = ProcessInfo.processInfo.environment["LYO_API_BASE_URL"],
           let url = URL(string: override) {
            return url
        }
        // Default to local development in debug
        return development
        #else
        return production
        #endif
    }
    
    // MARK: - API Versions
    
    enum Version: String {
        case v1 = "api/v1"
        case v2 = "api/v2"
    }
    
    // MARK: - API Endpoints
    
    enum API {
        // MARK: - Authentication
        case login
        case register
        case refreshToken
        case logout
        case verifyToken
        
        // MARK: - Chat & AI
        case chat
        case chatStream
        case chatHistory
        
        // MARK: - A2UI
        case a2uiNegotiate
        case a2uiWebSocket(userId: String)
        case a2uiComponents
        
        // MARK: - Course Generation
        case courseGenerate
        case courseStatus(jobId: String)
        case courseComplete(jobId: String)
        case courseFetch(courseId: String)
        
        // MARK: - User
        case userProfile
        case userPreferences
        case userProgress
        
        // MARK: - Study Planning
        case studyPlans
        case studyPlanDetail(planId: String)
        case studySessions
        
        // MARK: - Health
        case health
        case healthDetailed
        
        /// Returns the path for this endpoint
        var path: String {
            switch self {
            // Auth
            case .login: return "auth/login"
            case .register: return "auth/register"
            case .refreshToken: return "auth/refresh"
            case .logout: return "auth/logout"
            case .verifyToken: return "auth/verify"
                
            // Chat
            case .chat: return "chat"
            case .chatStream: return "chat/stream"
            case .chatHistory: return "chat/history"
                
            // A2UI
            case .a2uiNegotiate: return "a2ui/negotiate"
            case .a2uiWebSocket(let userId): return "ws/a2ui/\(userId)"
            case .a2uiComponents: return "a2ui/components"
                
            // Courses
            case .courseGenerate: return "courses/generate"
            case .courseStatus(let jobId): return "courses/status/\(jobId)"
            case .courseComplete(let jobId): return "courses/complete/\(jobId)"
            case .courseFetch(let courseId): return "courses/\(courseId)"
                
            // User
            case .userProfile: return "user/profile"
            case .userPreferences: return "user/preferences"
            case .userProgress: return "user/progress"
                
            // Study
            case .studyPlans: return "study/plans"
            case .studyPlanDetail(let planId): return "study/plans/\(planId)"
            case .studySessions: return "study/sessions"
                
            // Health
            case .health: return "health"
            case .healthDetailed: return "health/detailed"
            }
        }
        
        /// Returns the HTTP method for this endpoint
        var method: HTTPMethod {
            switch self {
            case .login, .register, .refreshToken, .logout,
                 .chat, .chatStream, .courseGenerate, .courseComplete:
                return .post
            case .verifyToken, .chatHistory, .a2uiNegotiate, .a2uiComponents,
                 .courseStatus, .courseFetch, .userProfile, .userPreferences,
                 .userProgress, .studyPlans, .studyPlanDetail, .studySessions,
                 .health, .healthDetailed, .a2uiWebSocket:
                return .get
            }
        }
        
        /// Whether this endpoint requires authentication
        var requiresAuth: Bool {
            switch self {
            case .login, .register, .health, .healthDetailed:
                return false
            default:
                return true
            }
        }
        
        /// Build the full URL for this endpoint
        func url(version: Version = .v1, base: URL = Endpoints.current) -> URL {
            base.appendingPathComponent(version.rawValue)
                .appendingPathComponent(path)
        }
        
        /// Build a WebSocket URL for this endpoint
        func webSocketURL(base: URL = Endpoints.current) -> URL? {
            guard case .a2uiWebSocket = self else { return nil }
            
            var components = URLComponents(url: base, resolvingAgainstBaseURL: false)
            components?.scheme = base.scheme == "https" ? "wss" : "ws"
            return components?.url?.appendingPathComponent(path)
        }
    }
    
    // MARK: - HTTP Methods
    
    enum HTTPMethod: String {
        case get = "GET"
        case post = "POST"
        case put = "PUT"
        case patch = "PATCH"
        case delete = "DELETE"
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - URL Builder Extensions
// ═══════════════════════════════════════════════════════════════════════════

extension Endpoints.API {
    
    /// Build a URLRequest for this endpoint
    func request(
        version: Endpoints.Version = .v1,
        base: URL = Endpoints.current,
        body: Data? = nil,
        headers: [String: String] = [:]
    ) -> URLRequest {
        var request = URLRequest(url: url(version: version, base: base))
        request.httpMethod = method.rawValue
        request.httpBody = body
        
        // Default headers
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        
        // Custom headers
        for (key, value) in headers {
            request.setValue(value, forHTTPHeaderField: key)
        }
        
        return request
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Environment Configuration
// ═══════════════════════════════════════════════════════════════════════════

/// Runtime environment configuration
struct EndpointConfiguration {
    static var shared = EndpointConfiguration()
    
    /// Override base URL (useful for testing)
    var baseURLOverride: URL?
    
    /// Whether to use staging instead of production
    var useStaging: Bool = false
    
    /// Current effective base URL
    var effectiveBaseURL: URL {
        if let override = baseURLOverride {
            return override
        }
        
        #if DEBUG
        return Endpoints.development
        #else
        return useStaging ? Endpoints.staging : Endpoints.production
        #endif
    }
}
