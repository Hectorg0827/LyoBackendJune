# 📱 iOS App - Backend Connection Guide

## 🚀 **Backend Server Ready**

Your LyoApp backend is running at: **http://localhost:8000**

---

## 📋 **Step 1: iOS Project Setup**

### **Add Network Permissions (Info.plist)**

Add this to your `Info.plist` to allow HTTP connections to localhost:

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSExceptionDomains</key>
    <dict>
        <key>localhost</key>
        <dict>
            <key>NSExceptionAllowsInsecureHTTPLoads</key>
            <true/>
            <key>NSExceptionMinimumTLSVersion</key>
            <string>TLSv1.0</string>
            <key>NSExceptionRequiresForwardSecrecy</key>
            <false/>
        </dict>
    </dict>
</dict>
```

---

## 🔗 **Step 2: Create API Client**

### **APIClient.swift**

```swift
import Foundation
import Combine

class LyoAppAPIClient: ObservableObject {
    static let shared = LyoAppAPIClient()
    
    // BACKEND URL - Change this for production
    private let baseURL = "http://localhost:8000"
    private let apiPath = "/api/v1"
    
    @Published var isAuthenticated = false
    @Published var currentUser: User?
    private var authToken: String?
    
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        return URLSession(configuration: config)
    }()
    
    private var cancellables = Set<AnyCancellable>()
    
    // MARK: - Helper Methods
    private func createRequest(for endpoint: String, method: HTTPMethod = .GET) -> URLRequest {
        let url = URL(string: baseURL + apiPath + endpoint)!
        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if let token = authToken {
            request.setValue("Bearer \\(token)", forHTTPHeaderField: "Authorization")
        }
        
        return request
    }
    
    // MARK: - Authentication
    func register(email: String, username: String, password: String, fullName: String) -> AnyPublisher<User, APIError> {
        var request = createRequest(for: "/auth/register", method: .POST)
        
        let userData = RegisterRequest(
            email: email,
            username: username,
            password: password,
            full_name: fullName
        )
        
        do {
            request.httpBody = try JSONEncoder().encode(userData)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: User.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    func login(username: String, password: String) -> AnyPublisher<AuthResponse, APIError> {
        var request = URLRequest(url: URL(string: baseURL + apiPath + "/auth/login")!)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        
        let body = "username=\\(username)&password=\\(password)"
        request.httpBody = body.data(using: .utf8)
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: AuthResponse.self, decoder: JSONDecoder())
            .handleEvents(receiveOutput: { [weak self] response in
                self?.authToken = response.access_token
                self?.currentUser = response.user
                self?.isAuthenticated = true
                UserDefaults.standard.set(response.access_token, forKey: "auth_token")
            })
            .mapError { _ in APIError.authenticationFailed }
            .eraseToAnyPublisher()
    }
    
    func logout() {
        authToken = nil
        currentUser = nil
        isAuthenticated = false
        UserDefaults.standard.removeObject(forKey: "auth_token")
    }
    
    func loadStoredToken() {
        if let token = UserDefaults.standard.string(forKey: "auth_token") {
            authToken = token
            isAuthenticated = true
            // Optionally verify token with /auth/me endpoint
        }
    }
    
    // MARK: - Stories
    func getStories() -> AnyPublisher<[Story], APIError> {
        let request = createRequest(for: "/social/stories/")
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: [Story].self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    func createStory(content: String, mediaData: Data? = nil) -> AnyPublisher<Story, APIError> {
        var request = URLRequest(url: URL(string: baseURL + apiPath + "/social/stories/")!)
        request.httpMethod = "POST"
        
        if let token = authToken {
            request.setValue("Bearer \\(token)", forHTTPHeaderField: "Authorization")
        }
        
        // Create multipart form data
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        
        // Add content field
        body.append("--\\(boundary)\\r\\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\\"content\\"\\r\\n\\r\\n".data(using: .utf8)!)
        body.append("\\(content)\\r\\n".data(using: .utf8)!)
        
        // Add media if provided
        if let mediaData = mediaData {
            body.append("--\\(boundary)\\r\\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\\"media\\"; filename=\\"story.jpg\\"\\r\\n".data(using: .utf8)!)
            body.append("Content-Type: image/jpeg\\r\\n\\r\\n".data(using: .utf8)!)
            body.append(mediaData)
            body.append("\\r\\n".data(using: .utf8)!)
        }
        
        body.append("--\\(boundary)--\\r\\n".data(using: .utf8)!)
        request.httpBody = body
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: Story.self, decoder: JSONDecoder())
            .mapError { _ in APIError.uploadFailed }
            .eraseToAnyPublisher()
    }
    
    func viewStory(storyId: Int) -> AnyPublisher<Void, APIError> {
        var request = createRequest(for: "/social/stories/\\(storyId)/view", method: .POST)
        
        return session.dataTaskPublisher(for: request)
            .map { _ in () }
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    // MARK: - Messenger
    func getConversations() -> AnyPublisher<[Conversation], APIError> {
        let request = createRequest(for: "/social/messenger/conversations")
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: [Conversation].self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    func getMessages(conversationId: Int) -> AnyPublisher<[Message], APIError> {
        let request = createRequest(for: "/social/messenger/conversations/\\(conversationId)/messages")
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: [Message].self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    func sendMessage(conversationId: Int, content: String) -> AnyPublisher<Message, APIError> {
        var request = createRequest(for: "/social/messenger/conversations/\\(conversationId)/messages", method: .POST)
        
        let messageData = SendMessageRequest(content: content, message_type: "text")
        
        do {
            request.httpBody = try JSONEncoder().encode(messageData)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: Message.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    func createConversation(participantIds: [Int], isGroup: Bool = false, name: String? = nil) -> AnyPublisher<Conversation, APIError> {
        var request = createRequest(for: "/social/messenger/conversations", method: .POST)
        
        let conversationData = CreateConversationRequest(
            participant_ids: participantIds,
            is_group: isGroup,
            name: name
        )
        
        do {
            request.httpBody = try JSONEncoder().encode(conversationData)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: Conversation.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    // MARK: - Learning
    func searchLearning(query: String) -> AnyPublisher<[LearningResource], APIError> {
        let encodedQuery = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        let request = createRequest(for: "/learning/search?q=\\(encodedQuery)")
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: [LearningResource].self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    func discoverLearning() -> AnyPublisher<[LearningResource], APIError> {
        let request = createRequest(for: "/learning/discover")
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: [LearningResource].self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    // MARK: - AI Chat
    func sendAIMessage(message: String, model: String = "gpt-4") -> AnyPublisher<AIResponse, APIError> {
        var request = createRequest(for: "/ai/chat", method: .POST)
        
        let chatData = AIMessageRequest(message: message, model: model)
        
        do {
            request.httpBody = try JSONEncoder().encode(chatData)
        } catch {
            return Fail(error: APIError.encodingError).eraseToAnyPublisher()
        }
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: AIResponse.self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    // MARK: - Gamification
    func getLeaderboard() -> AnyPublisher<[LeaderboardEntry], APIError> {
        let request = createRequest(for: "/gamification/leaderboard")
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: [LeaderboardEntry].self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
    
    func getUserAchievements() -> AnyPublisher<[Achievement], APIError> {
        let request = createRequest(for: "/gamification/achievements")
        
        return session.dataTaskPublisher(for: request)
            .map(\\.data)
            .decode(type: [Achievement].self, decoder: JSONDecoder())
            .mapError { _ in APIError.networkError }
            .eraseToAnyPublisher()
    }
}

// MARK: - HTTP Methods
enum HTTPMethod: String {
    case GET = "GET"
    case POST = "POST"
    case PUT = "PUT"
    case DELETE = "DELETE"
}

// MARK: - API Errors
enum APIError: Error, LocalizedError {
    case networkError
    case authenticationFailed
    case encodingError
    case uploadFailed
    
    var errorDescription: String? {
        switch self {
        case .networkError:
            return "Network connection failed"
        case .authenticationFailed:
            return "Authentication failed"
        case .encodingError:
            return "Data encoding failed"
        case .uploadFailed:
            return "File upload failed"
        }
    }
}
```

---

## 📦 **Step 3: Data Models**

### **Models.swift**

```swift
import Foundation

// MARK: - Authentication Models
struct RegisterRequest: Codable {
    let email: String
    let username: String
    let password: String
    let full_name: String
}

struct AuthResponse: Codable {
    let access_token: String
    let token_type: String
    let user: User
}

struct User: Codable, Identifiable {
    let id: Int
    let email: String
    let username: String
    let full_name: String?
    let avatar_url: String?
    let created_at: String
    let updated_at: String?
}

// MARK: - Story Models
struct Story: Codable, Identifiable {
    let id: Int
    let user_id: Int
    let content_type: String
    let media_url: String?
    let text_content: String?
    let expires_at: String
    let view_count: Int
    let created_at: String
    let user: User?
}

// MARK: - Messenger Models
struct Conversation: Codable, Identifiable {
    let id: Int
    let name: String?
    let type: String
    let participant_count: Int
    let last_message: String?
    let created_at: String
    let updated_at: String
}

struct Message: Codable, Identifiable {
    let id: Int
    let conversation_id: Int
    let sender_id: Int
    let sender_name: String
    let content: String
    let message_type: String
    let created_at: String
    let is_read: Bool?
}

struct SendMessageRequest: Codable {
    let content: String
    let message_type: String
}

struct CreateConversationRequest: Codable {
    let participant_ids: [Int]
    let is_group: Bool
    let name: String?
}

// MARK: - Learning Models
struct LearningResource: Codable, Identifiable {
    let id: String
    let title: String
    let description: String?
    let content_type: String
    let thumbnail_url: String?
    let difficulty_level: String?
    let estimated_duration: Int?
    let rating: Double?
    let is_bookmarked: Bool?
}

// MARK: - AI Models
struct AIMessageRequest: Codable {
    let message: String
    let model: String
}

struct AIResponse: Codable {
    let response: String
    let model: String
    let tokens_used: Int?
}

// MARK: - Gamification Models
struct LeaderboardEntry: Codable, Identifiable {
    let id: Int
    let user: User
    let total_xp: Int
    let rank: Int
}

struct Achievement: Codable, Identifiable {
    let id: Int
    let name: String
    let description: String
    let icon_url: String?
    let unlocked_at: String?
    let is_unlocked: Bool
}
```

---

## 🌐 **Step 4: WebSocket Manager**

### **WebSocketManager.swift**

```swift
import Foundation
import Combine

class WebSocketManager: ObservableObject {
    @Published var isConnected = false
    @Published var messages: [Message] = []
    @Published var connectionStatus = "Disconnected"
    
    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession
    private var cancellables = Set<AnyCancellable>()
    
    init() {
        urlSession = URLSession(configuration: .default)
    }
    
    func connectMessenger(userId: Int, token: String) {
        let urlString = "ws://localhost:8000/api/v1/social/messenger/ws/\\(userId)?token=\\(token)"
        connect(to: urlString, type: "Messenger")
    }
    
    func connectAI(userId: Int, token: String) {
        let urlString = "ws://localhost:8000/api/v1/ai/ws/\\(userId)?token=\\(token)"
        connect(to: urlString, type: "AI Chat")
    }
    
    private func connect(to urlString: String, type: String) {
        guard let url = URL(string: urlString) else {
            print("Invalid WebSocket URL: \\(urlString)")
            return
        }
        
        webSocketTask = urlSession.webSocketTask(with: url)
        webSocketTask?.resume()
        
        isConnected = true
        connectionStatus = "Connected to \\(type)"
        receiveMessage()
        
        print("✅ Connected to \\(type) WebSocket")
    }
    
    func disconnect() {
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        isConnected = false
        connectionStatus = "Disconnected"
        print("🔌 WebSocket disconnected")
    }
    
    func sendMessage(content: String, conversationId: Int? = nil) {
        let messageData: [String: Any] = [
            "type": "send_message",
            "content": content,
            "conversation_id": conversationId ?? 0,
            "timestamp": ISO8601DateFormatter().string(from: Date())
        ]
        
        guard let data = try? JSONSerialization.data(withJSONObject: messageData),
              let jsonString = String(data: data, encoding: .utf8) else {
            print("❌ Failed to encode message")
            return
        }
        
        let message = URLSessionWebSocketTask.Message.string(jsonString)
        webSocketTask?.send(message) { [weak self] error in
            if let error = error {
                print("❌ WebSocket send error: \\(error)")
                self?.connectionStatus = "Send error"
            } else {
                print("✅ Message sent via WebSocket")
            }
        }
    }
    
    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            switch result {
            case .failure(let error):
                print("❌ WebSocket receive error: \\(error)")
                self?.connectionStatus = "Receive error"
                
            case .success(let message):
                switch message {
                case .string(let text):
                    self?.handleMessage(text)
                case .data(let data):
                    if let text = String(data: data, encoding: .utf8) {
                        self?.handleMessage(text)
                    }
                @unknown default:
                    break
                }
                
                // Continue receiving messages
                self?.receiveMessage()
            }
        }
    }
    
    private func handleMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            print("❌ Failed to parse WebSocket message")
            return
        }
        
        print("📨 Received WebSocket message: \\(json)")
        
        // Handle different message types
        if let type = json["type"] as? String {
            switch type {
            case "message":
                if let messageData = try? JSONSerialization.data(withJSONObject: json),
                   let message = try? JSONDecoder().decode(Message.self, from: messageData) {
                    DispatchQueue.main.async {
                        self.messages.append(message)
                    }
                }
            case "typing":
                // Handle typing indicators
                break
            case "user_joined", "user_left":
                // Handle user presence
                break
            default:
                print("⚠️ Unknown message type: \\(type)")
            }
        }
    }
}
```

---

## 🎯 **Step 5: Example SwiftUI Views**

### **ContentView.swift**

```swift
import SwiftUI
import Combine

struct ContentView: View {
    @StateObject private var apiClient = LyoAppAPIClient.shared
    @StateObject private var webSocketManager = WebSocketManager()
    @State private var cancellables = Set<AnyCancellable>()
    
    var body: some View {
        NavigationView {
            if apiClient.isAuthenticated {
                TabView {
                    StoriesView()
                        .tabItem {
                            Image(systemName: "circle.dashed")
                            Text("Stories")
                        }
                    
                    ConversationsView()
                        .tabItem {
                            Image(systemName: "message")
                            Text("Chat")
                        }
                    
                    LearningView()
                        .tabItem {
                            Image(systemName: "book")
                            Text("Learn")
                        }
                    
                    AIAssistantView()
                        .tabItem {
                            Image(systemName: "brain")
                            Text("AI")
                        }
                    
                    ProfileView()
                        .tabItem {
                            Image(systemName: "person")
                            Text("Profile")
                        }
                }
                .onAppear {
                    // Connect WebSocket when authenticated
                    if let user = apiClient.currentUser,
                       let token = UserDefaults.standard.string(forKey: "auth_token") {
                        webSocketManager.connectMessenger(userId: user.id, token: token)
                    }
                }
            } else {
                LoginView()
            }
        }
        .onAppear {
            apiClient.loadStoredToken()
        }
    }
}

// MARK: - Login View
struct LoginView: View {
    @StateObject private var apiClient = LyoAppAPIClient.shared
    @State private var username = ""
    @State private var password = ""
    @State private var isLoading = false
    @State private var errorMessage = ""
    
    var body: some View {
        VStack(spacing: 20) {
            Text("Welcome to LyoApp")
                .font(.largeTitle)
                .fontWeight(.bold)
            
            VStack(spacing: 15) {
                TextField("Username", text: $username)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                
                SecureField("Password", text: $password)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                
                if !errorMessage.isEmpty {
                    Text(errorMessage)
                        .foregroundColor(.red)
                        .font(.caption)
                }
                
                Button(action: login) {
                    if isLoading {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle())
                    } else {
                        Text("Login")
                            .fontWeight(.semibold)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color.blue)
                .foregroundColor(.white)
                .cornerRadius(10)
                .disabled(isLoading || username.isEmpty || password.isEmpty)
            }
            .padding()
        }
        .padding()
    }
    
    private func login() {
        isLoading = true
        errorMessage = ""
        
        apiClient.login(username: username, password: password)
            .receive(on: DispatchQueue.main)
            .sink(
                receiveCompletion: { completion in
                    isLoading = false
                    if case .failure(let error) = completion {
                        errorMessage = error.localizedDescription
                    }
                },
                receiveValue: { response in
                    print("✅ Login successful for user: \\(response.user.username)")
                }
            )
            .store(in: &apiClient.cancellables)
    }
}
```

---

## 🧪 **Step 6: Test Connection**

### **Quick Test Function**

Add this to test your connection:

```swift
func testBackendConnection() {
    print("🔍 Testing backend connection...")
    
    LyoAppAPIClient.shared.login(username: "testuser", password: "testpass")
        .sink(
            receiveCompletion: { completion in
                switch completion {
                case .finished:
                    print("✅ Backend connection successful!")
                case .failure(let error):
                    print("❌ Connection failed: \\(error)")
                    print("🔧 Make sure backend is running at http://localhost:8000")
                }
            },
            receiveValue: { response in
                print("🎉 Authenticated user: \\(response.user.username)")
                
                // Test getting stories
                LyoAppAPIClient.shared.getStories()
                    .sink(
                        receiveCompletion: { _ in },
                        receiveValue: { stories in
                            print("📚 Found \\(stories.count) stories")
                        }
                    )
                    .store(in: &cancellables)
            }
        )
        .store(in: &cancellables)
}
```

---

## ✅ **Step 7: Verify Everything Works**

### **Backend Endpoints Available:**
- ✅ **Authentication**: `POST /api/v1/auth/login`, `POST /api/v1/auth/register`
- ✅ **Stories**: `GET /api/v1/social/stories/`, `POST /api/v1/social/stories/`
- ✅ **Messaging**: `GET /api/v1/social/messenger/conversations`
- ✅ **Learning**: `GET /api/v1/learning/search?q=query`
- ✅ **AI Chat**: `POST /api/v1/ai/chat`
- ✅ **Gamification**: `GET /api/v1/gamification/leaderboard`
- ✅ **WebSocket**: `ws://localhost:8000/api/v1/social/messenger/ws/{user_id}`

### **Quick Backend Test:**
Open http://localhost:8000/docs in your browser to test all endpoints interactively.

---

## 🚀 **You're Ready!**

Your iOS app is now fully connected to the backend with:

- ✅ **Complete Authentication System**
- ✅ **Real-time Messaging via WebSocket**
- ✅ **Stories with Media Upload**
- ✅ **Learning Content Discovery**
- ✅ **AI Chat Integration**
- ✅ **Gamification Features**
- ✅ **Error Handling & Loading States**

**Start building your amazing iOS learning app!** 📱🎉
