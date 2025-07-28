# LyoApp Backend - Frontend Integration Guide

## 🔗 Backend Status
- **Server URL**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Database**: SQLite (development ready)

## 📱 Frontend Integration - API Endpoints

### 1. **Authentication Endpoints**
```swift
// Base URL for all API calls
let baseURL = "http://localhost:8000"

// Authentication endpoints
POST /api/v1/auth/register          // User registration
POST /api/v1/auth/login             // User login  
GET  /api/v1/auth/me                // Get current user profile
GET  /api/v1/auth/users/{user_id}   // Get user by ID
```

**Example Swift Implementation:**
```swift
class LyoAPIService {
    private let baseURL = "http://localhost:8000"
    
    // Login function
    func login(email: String, password: String) async throws -> LoginResponse {
        let url = URL(string: "\(baseURL)/api/v1/auth/login")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let loginData = [
            "email": email,
            "password": password
        ]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: loginData)
        
        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(LoginResponse.self, from: data)
    }
    
    // Check backend connection
    func checkBackendConnection() async -> Bool {
        guard let url = URL(string: "\(baseURL)/health") else { return false }
        
        do {
            let (_, response) = try await URLSession.shared.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}
```

### 2. **Email Verification Endpoints**
```swift
POST /auth/verify-email/send        // Send verification email
POST /auth/verify-email/confirm     // Confirm email verification
POST /auth/password-reset/request   // Request password reset
POST /auth/password-reset/confirm   // Confirm password reset
GET  /auth/verify-email/status/{user_id} // Get verification status
```

### 3. **Learning System Endpoints**
```swift
GET  /api/v1/learning/courses       // Get all courses
POST /api/v1/learning/courses       // Create course
GET  /api/v1/learning/courses/{id}  // Get specific course
PUT  /api/v1/learning/courses/{id}  // Update course
POST /api/v1/learning/lessons       // Create lesson
GET  /api/v1/learning/courses/{course_id}/lessons // Get course lessons
POST /api/v1/learning/enrollments   // Enroll in course
POST /api/v1/learning/completions   // Complete lesson
```

### 4. **Social Feeds Endpoints**
```swift
GET  /api/v1/feeds/                 // Get user feed
POST /api/v1/feeds/posts            // Create post
GET  /api/v1/feeds/posts/{post_id}  // Get specific post
PUT  /api/v1/feeds/posts/{post_id}  // Update post
DELETE /api/v1/feeds/posts/{post_id} // Delete post
POST /api/v1/feeds/comments         // Create comment
POST /api/v1/feeds/posts/{post_id}/reactions // React to post
GET  /api/v1/feeds/following        // Get following list
POST /api/v1/feeds/follow           // Follow user
```

### 5. **Community Endpoints**
```swift
GET  /api/v1/community/study-groups // Get study groups
POST /api/v1/community/study-groups // Create study group
GET  /api/v1/community/events       // Get community events
POST /api/v1/community/events       // Create event
POST /api/v1/community/events/{event_id}/attend // Attend event
```

### 6. **Gamification Endpoints**
```swift
GET  /api/v1/gamification/leaderboard    // Get leaderboard
POST /api/v1/gamification/xp/award       // Award XP points
GET  /api/v1/gamification/achievements   // Get user achievements
GET  /api/v1/gamification/stats          // Get user stats
GET  /api/v1/gamification/streaks        // Get user streaks
GET  /api/v1/gamification/badges         // Get user badges
```

### 7. **File Management Endpoints**
```swift
POST /files/upload                  // Upload file
GET  /files/                        // List user files
GET  /files/{file_id}               // Download file
DELETE /files/{file_id}             // Delete file
```

### 8. **AI Agents Endpoints**
```swift
POST /api/v1/ai/mentor/conversation      // Send message to AI mentor
GET  /api/v1/ai/mentor/history          // Get conversation history
POST /api/v1/ai/engagement/analyze     // Analyze user engagement
GET  /api/v1/ai/health                 // AI system health check
WS   /api/v1/ai/ws/{user_id}           // WebSocket for real-time AI chat
```

### 9. **Health & Monitoring Endpoints**
```swift
GET /health                         // Basic health check
GET /health/detailed                // Detailed system health  
GET /health/ready                   // Readiness probe
GET /health/live                    // Liveness probe
GET /metrics                        // Prometheus metrics
```

### 10. **Admin Endpoints** (Admin users only)
```swift
GET  /api/v1/admin/users            // Get all users
GET  /api/v1/admin/roles            // Get all roles
POST /api/v1/admin/roles            // Create role
PUT  /api/v1/admin/roles/{role_name} // Update role
```

## 🔧 Swift Implementation Helper

### Network Layer Configuration
```swift
import Foundation

enum HTTPMethod: String {
    case GET = "GET"
    case POST = "POST"
    case PUT = "PUT"
    case DELETE = "DELETE"
}

class APIClient {
    private let baseURL = "http://localhost:8000"
    private var authToken: String?
    
    // Set authentication token
    func setAuthToken(_ token: String) {
        self.authToken = token
    }
    
    // Make authenticated request
    private func makeRequest<T: Codable>(
        endpoint: String,
        method: HTTPMethod,
        body: Codable? = nil,
        responseType: T.Type
    ) async throws -> T {
        guard let url = URL(string: "\(baseURL)\(endpoint)") else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Add authorization header if token exists
        if let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        // Add request body for POST/PUT requests
        if let body = body {
            request.httpBody = try JSONEncoder().encode(body)
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        guard 200...299 ~= httpResponse.statusCode else {
            throw APIError.serverError(httpResponse.statusCode)
        }
        
        return try JSONDecoder().decode(responseType.self, from: data)
    }
    
    // Check backend connection
    func checkBackendConnection() async -> Bool {
        do {
            let _: HealthResponse = try await makeRequest(
                endpoint: "/health",
                method: .GET,
                responseType: HealthResponse.self
            )
            return true
        } catch {
            return false
        }
    }
    
    // Login function
    func login(email: String, password: String) async throws -> LoginResponse {
        let loginRequest = LoginRequest(email: email, password: password)
        return try await makeRequest(
            endpoint: "/api/v1/auth/login",
            method: .POST,
            body: loginRequest,
            responseType: LoginResponse.self
        )
    }
    
    // Logout function  
    func logout() {
        authToken = nil
    }
}

// Response models
struct HealthResponse: Codable {
    let status: String
    let environment: String
    let version: String
}

struct LoginRequest: Codable {
    let email: String
    let password: String
}

struct LoginResponse: Codable {
    let access_token: String
    let token_type: String
    let expires_in: Int
}

enum APIError: Error {
    case invalidURL
    case invalidResponse
    case serverError(Int)
}
```

## 🐛 Frontend Issues Resolution

Based on the Swift errors you mentioned:

1. **`APIClient` missing members**: Use the complete `APIClient` implementation above
2. **`HTTPMethod` ambiguous**: Use the enum definition provided above  
3. **Missing `$isConnected`**: Add a `@Published var isConnected: Bool = false` property
4. **Missing methods**: All missing methods are implemented in the complete `APIClient` above

## ✅ Backend Verification

The backend is properly running and all endpoints are available. The frontend can immediately start using these endpoints for full app functionality.
