# 📱 iOS Frontend Connection Guide

## 🎯 **AUTOMATED BACKEND-FRONTEND CONNECTION COMPLETE**

Your LyoApp backend is now **100% ready** for iOS frontend integration! Here's everything you need to connect your iOS app.

## 🚀 **Quick Start**

### **1. Backend URL**
```
http://localhost:8000
```
*For production, replace with your domain (e.g., https://api.yourdomain.com)*

### **2. API Documentation**
```
http://localhost:8000/docs
```
*Interactive Swagger UI with all endpoints*

### **3. Health Check**
```
http://localhost:8000/health
```
*Verify backend is running*

## 🔗 **iOS Integration Steps**

### **Step 1: Configure Base URL in iOS**
```swift
class APIService {
    static let baseURL = "http://localhost:8000"
    // For production: "https://api.yourdomain.com"
}
```

### **Step 2: Implement Authentication**
```swift
struct LoginRequest: Codable {
    let username: String
    let password: String
}

struct AuthResponse: Codable {
    let access_token: String
    let token_type: String
}

func login(username: String, password: String) async -> AuthResponse? {
    let url = URL(string: "\(APIService.baseURL)/api/v1/auth/login")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
    
    let body = "username=\(username)&password=\(password)"
    request.httpBody = body.data(using: .utf8)
    
    do {
        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(AuthResponse.self, from: data)
    } catch {
        print("Login error: \(error)")
        return nil
    }
}
```

### **Step 3: User Registration**
```swift
struct RegisterRequest: Codable {
    let email: String
    let username: String
    let password: String
    let full_name: String
}

func register(email: String, username: String, password: String, fullName: String) async -> Bool {
    let url = URL(string: "\(APIService.baseURL)/api/v1/auth/register")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    
    let registerData = RegisterRequest(email: email, username: username, password: password, full_name: fullName)
    request.httpBody = try? JSONEncoder().encode(registerData)
    
    do {
        let (_, response) = try await URLSession.shared.data(for: request)
        return (response as? HTTPURLResponse)?.statusCode == 201
    } catch {
        return false
    }
}
```

### **Step 4: Authenticated Requests**
```swift
func makeAuthenticatedRequest(endpoint: String, token: String) async -> Data? {
    let url = URL(string: "\(APIService.baseURL)\(endpoint)")!
    var request = URLRequest(url: url)
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    
    do {
        let (data, _) = try await URLSession.shared.data(for: request)
        return data
    } catch {
        print("Request error: \(error)")
        return nil
    }
}
```

## 📋 **Key API Endpoints for iOS**

### **Authentication**
- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/login` - User login (form data)
- `GET /api/v1/auth/me` - Get current user info
- `POST /api/v1/auth/refresh` - Refresh token

### **Stories (Social Feature)**
- `GET /api/v1/social/stories` - Get active stories
- `POST /api/v1/social/stories` - Create new story
- `POST /api/v1/social/stories/{id}/view` - Mark story as viewed
- `DELETE /api/v1/social/stories/{id}` - Delete story

### **Messenger (Chat Feature)**
- `GET /api/v1/social/conversations` - Get user conversations
- `POST /api/v1/social/conversations` - Create new conversation
- `GET /api/v1/social/conversations/{id}/messages` - Get messages
- `POST /api/v1/social/conversations/{id}/messages` - Send message

### **Social Feeds**
- `GET /api/v1/feeds/` - Get personalized feed
- `POST /api/v1/feeds/posts` - Create new post
- `POST /api/v1/feeds/posts/{id}/like` - Like a post
- `POST /api/v1/feeds/posts/{id}/comment` - Comment on post

### **Learning System**
- `GET /api/v1/learning/courses` - Get available courses
- `POST /api/v1/learning/enroll` - Enroll in course
- `GET /api/v1/learning/progress` - Get learning progress
- `POST /api/v1/learning/complete` - Mark lesson complete

### **AI Integration**
- `POST /api/v1/ai/chat` - Chat with AI
- `GET /api/v1/ai/agents` - Get available AI agents

### **Gamification**
- `GET /api/v1/gamification/profile` - Get user XP and level
- `GET /api/v1/gamification/achievements` - Get achievements
- `GET /api/v1/gamification/leaderboard` - Get leaderboard

### **File Management**
- `POST /files/upload` - Upload file (multipart/form-data)
- `GET /files/{file_id}` - Download file
- `DELETE /files/{file_id}` - Delete file

## 🔄 **Real-time Features (WebSocket)**

### **WebSocket Connections**
```swift
class WebSocketManager: ObservableObject {
    private var webSocketTask: URLSessionWebSocketTask?
    
    func connect(userID: String, token: String) {
        let url = URL(string: "ws://localhost:8000/api/v1/social/ws/\(userID)?token=\(token)")!
        webSocketTask = URLSession.shared.webSocketTask(with: url)
        webSocketTask?.resume()
        receiveMessage()
    }
    
    func sendMessage(content: String, conversationID: String) {
        let message = [
            "type": "send_message",
            "conversation_id": conversationID,
            "content": content
        ]
        
        if let data = try? JSONSerialization.data(withJSONObject: message),
           let jsonString = String(data: data, encoding: .utf8) {
            webSocketTask?.send(.string(jsonString)) { error in
                if let error = error {
                    print("WebSocket send error: \(error)")
                }
            }
        }
    }
    
    private func receiveMessage() {
        webSocketTask?.receive { result in
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    // Handle received message
                    print("Received: \(text)")
                case .data(let data):
                    // Handle binary data
                    break
                @unknown default:
                    break
                }
                self.receiveMessage() // Continue listening
            case .failure(let error):
                print("WebSocket receive error: \(error)")
            }
        }
    }
}
```

### **Available WebSocket Endpoints**
- `ws://localhost:8000/api/v1/social/ws/{user_id}` - Real-time messaging
- `ws://localhost:8000/api/v1/ai/ws/{user_id}` - Real-time AI chat

## 📁 **File Upload Example**
```swift
func uploadFile(fileData: Data, fileName: String, token: String) async -> Bool {
    let url = URL(string: "\(APIService.baseURL)/files/upload")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    
    let boundary = UUID().uuidString
    request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
    
    var body = Data()
    body.append("--\(boundary)\r\n".data(using: .utf8)!)
    body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
    body.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
    body.append(fileData)
    body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
    
    request.httpBody = body
    
    do {
        let (_, response) = try await URLSession.shared.data(for: request)
        return (response as? HTTPURLResponse)?.statusCode == 200
    } catch {
        return false
    }
}
```

## 🔒 **Security Best Practices**

### **Token Storage**
```swift
import Security

class KeychainManager {
    static func store(token: String) {
        let data = token.data(using: .utf8)!
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "auth_token",
            kSecValueData as String: data
        ]
        
        SecItemDelete(query as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }
    
    static func retrieve() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "auth_token",
            kSecReturnData as String: true
        ]
        
        var result: AnyObject?
        if SecItemCopyMatching(query as CFDictionary, &result) == noErr,
           let data = result as? Data {
            return String(data: data, encoding: .utf8)
        }
        return nil
    }
}
```

## 🧪 **Testing Your Connection**

### **Test Backend Connectivity**
```swift
func testBackendConnection() async -> Bool {
    guard let url = URL(string: "\(APIService.baseURL)/health") else { return false }
    
    do {
        let (data, response) = try await URLSession.shared.data(from: url)
        if let httpResponse = response as? HTTPURLResponse,
           httpResponse.statusCode == 200 {
            print("✅ Backend connection successful")
            return true
        }
    } catch {
        print("❌ Backend connection failed: \(error)")
    }
    return false
}
```

## 🎯 **Complete Example: iOS App Structure**

```swift
import SwiftUI

@main
struct LyoApp: App {
    @StateObject private var authManager = AuthManager()
    @StateObject private var webSocketManager = WebSocketManager()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authManager)
                .environmentObject(webSocketManager)
        }
    }
}

class AuthManager: ObservableObject {
    @Published var isAuthenticated = false
    @Published var currentUser: User?
    private var authToken: String?
    
    func login(username: String, password: String) async {
        // Use the login function from above
        if let authResponse = await login(username: username, password: password) {
            self.authToken = authResponse.access_token
            KeychainManager.store(token: authResponse.access_token)
            await fetchCurrentUser()
            DispatchQueue.main.async {
                self.isAuthenticated = true
            }
        }
    }
    
    func fetchCurrentUser() async {
        guard let token = authToken,
              let data = await makeAuthenticatedRequest(endpoint: "/api/v1/auth/me", token: token) else { return }
        
        if let user = try? JSONDecoder().decode(User.self, from: data) {
            DispatchQueue.main.async {
                self.currentUser = user
            }
        }
    }
}
```

## 🎉 **You're Ready to Go!**

Your backend is now fully configured and ready for iOS frontend integration. All endpoints are documented, authentication is working, and real-time features are available via WebSocket.

### **Start Building Your iOS App With:**
1. ✅ Complete authentication system
2. ✅ Real-time messaging and stories
3. ✅ Social feeds and content
4. ✅ Learning management system
5. ✅ AI chat integration
6. ✅ File upload/download
7. ✅ Gamification features
8. ✅ WebSocket real-time updates

**Happy coding! 🚀📱**
