# iOS Integration Guide - AI Classroom

## 🚀 Production URL
```
https://lyo-backend-production-830162750094.us-central1.run.app
```

## ⚡ Quick Start - Smart AI Service (Recommended)

The easiest integration is `SmartAIService.swift` - it auto-detects user intent:

```swift
// Just copy SmartAIService.swift to your project and use it:

// Auto-detects intent from message:
let result = try await SmartAIService.shared.chat(message: "Teach me Python")
// ^ Detects "teach me" → Uses COURSE_GENERATION → Returns full course!

let result = try await SmartAIService.shared.chat(message: "What is recursion?")  
// ^ Detects question → Uses EDUCATIONAL_EXPLANATION → Returns quick answer

// Or use convenience methods:
let course = try await SmartAIService.shared.createCourse(on: "Machine Learning")
let quiz = try await SmartAIService.shared.quiz(on: "Python basics")
```

### Intent Detection Patterns

| User Says | Detected Task | Result |
|-----------|--------------|--------|
| "Teach me X" | COURSE_GENERATION | Full structured course |
| "Create a course on X" | COURSE_GENERATION | Full structured course |
| "Learn about X" | COURSE_GENERATION | Full structured course |
| "What is X?" | EDUCATIONAL_EXPLANATION | Quick explanation |
| "Explain X" | EDUCATIONAL_EXPLANATION | Quick explanation |
| "Quiz me on X" | QUIZ_GENERATION | Practice questions |
| "Test my knowledge" | QUIZ_GENERATION | Practice questions |
| "Summarize X" | NOTE_SUMMARIZATION | Key points summary |

---

## 📁 Files to Copy

Copy all files from this folder to your iOS project:

| File | Destination | Purpose |
|------|-------------|---------|
| `AIClassroomService.swift` | `Lyo/Services/` | API client extension + models |
| `AIClassroomView.swift` | `Lyo/Views/AIClassroom/` | Main chat UI |
| `LyoAppAPIClient+Production.swift` | `Lyo/Services/` | Production URL configuration |
| `NavigationIntegration.swift` | `Lyo/Views/` | Navigation helpers |

## 🔧 Integration Steps

### Step 1: Add Files to Xcode
1. Open `LYO Da ONE.xcodeproj` in Xcode
2. Right-click on `Lyo/Services` → "Add Files to Lyo..."
3. Select `AIClassroomService.swift` and `LyoAppAPIClient+Production.swift`
4. Create folder `Lyo/Views/AIClassroom` 
5. Add `AIClassroomView.swift` and `NavigationIntegration.swift`

### Step 2: Update LyoAppAPIClient.swift

Change the base URL for production:

```swift
class LyoAppAPIClient: ObservableObject {
    static let shared = LyoAppAPIClient()
    
    // CHANGE THIS LINE:
    private let baseURL = "https://lyo-backend-production-830162750094.us-central1.run.app"
    private let apiPath = "/api/v1"
    
    // ... rest of the code
}
```

Or use the environment-based approach from `LyoAppAPIClient+Production.swift`.

### Step 3: Add to Navigation

Choose one of these options:

**Option A: Tab Bar**
```swift
TabView {
    // Existing tabs...
    
    NavigationStack {
        AIClassroomView()
    }
    .tabItem {
        Image(systemName: "sparkles")
        Text("AI Classroom")
    }
}
```

**Option B: Floating Button**
```swift
ZStack(alignment: .bottomTrailing) {
    // Your main content
    ContentView()
    
    AIClassroomFloatingButton()
        .padding()
}
```

**Option C: Home Card**
```swift
ScrollView {
    VStack {
        // Other content...
        AIClassroomCard()
            .padding(.horizontal)
    }
}
```

### Step 4: Configure App (Optional)

In your `App.swift`:

```swift
@main
struct LyoApp: App {
    init() {
        #if !DEBUG
        LyoAppAPIClient.configureForProduction()
        #endif
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
```

## 🎯 Available Features

### AI Classroom Chat
```swift
LyoAppAPIClient.shared.sendClassroomMessage(
    message: "Explain photosynthesis",
    enableTTS: true
)
.sink { response in
    print(response.response)
    print(response.intent.type) // .quickExplanation, .fullCourse, etc.
}
```

### Intent Detection
The AI automatically detects user intent:
- `quickExplanation` - Brief answer
- `fullCourse` - Generate complete course
- `quiz` - Create quiz
- `exercise` - Practice problems
- `codeHelp` - Programming assistance
- `studyPlan` - Learning schedule

### Text-to-Speech (6 Voices)
```swift
LyoAppAPIClient.shared.synthesizeSpeech(
    text: "Hello, welcome to your lesson",
    voiceId: "nova"  // alloy, echo, fable, onyx, nova, shimmer
)
```

### Image Generation
```swift
LyoAppAPIClient.shared.generateImage(
    prompt: "Diagram of the water cycle",
    style: .educational
)
```

## 📡 API Endpoints

| Feature | Endpoint | Method |
|---------|----------|--------|
| Chat | `/api/v1/classroom/chat` | POST |
| Stream | `/api/v1/classroom/chat/stream` | POST |
| Intent | `/api/v1/classroom/analyze-intent` | POST |
| TTS Synthesize | `/api/v1/tts/synthesize` | POST |
| TTS Voices | `/api/v1/tts/voices` | GET |
| Image Generate | `/api/v1/images/generate` | POST |
| Educational Image | `/api/v1/images/educational` | POST |

## ✅ Testing

Test the backend connection:
```bash
curl https://lyo-backend-production-830162750094.us-central1.run.app/api/v1/classroom/health
```

Expected:
```json
{"status": "healthy", "message": "AI Classroom is ready"}
```

## 🎨 UI Components

- `AIClassroomView` - Full chat interface
- `AIClassroomCard` - Promotional card for home screen
- `AIClassroomFloatingButton` - FAB for quick access
- `AIClassroomToolbarButton` - Toolbar button
- `VoiceSelectorView` - TTS voice picker
- `MessageBubbleView` - Chat bubble component

## 🔊 TTS Voice Options

| Voice | Style |
|-------|-------|
| `alloy` | Neutral, balanced |
| `echo` | Clear, professional |
| `fable` | Warm, storytelling |
| `onyx` | Deep, authoritative |
| `nova` | Friendly, energetic ⭐ |
| `shimmer` | Soft, calming |

## 📱 Requirements

- iOS 16.0+
- Swift 5.9+
- Xcode 15.0+
