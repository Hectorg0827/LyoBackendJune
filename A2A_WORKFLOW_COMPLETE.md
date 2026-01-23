# Complete A2A → A2UI Translation Workflow

## Quick Reference

**What**: Translation layer between backend A2A (Agent-to-Agent) protocol and iOS A2UI (Agent-to-UI) protocol  
**Why**: Enable structured UI components instead of raw JSON text  
**Status**: ✅ Complete, Tested, Production Ready  

---

## Complete Request/Response Flow

### 1. User Request (iOS → Backend)

**iOS Code** (`UnifiedChatService.sendMessage()`):
```swift
let result = try await BackendAIService.shared.studySession(
    message: "Create a course on Python",
    resourceId: nil,
    mode: "focus",
    history: conversationHistory
)
```

**HTTP Request**:
```http
POST /api/v1/ai/chat
Content-Type: application/json

{
    "message": "Create a course on Python",
    "conversation_history": [...],
    "context": "mode=focus,topic=general_learning"
}
```

---

### 2. Backend Processing

**Step 1: Intent Detection** (`chat.py` line ~204):
```python
course_intent = detect_course_creation_intent(request.message)
# Returns: {'topic': 'python', 'intent': 'course_creation'}
```

**Step 2: Invoke A2A Orchestrator** (`chat.py` line ~208-220):
```python
orchestrator = A2AOrchestrator()
course_request = A2ACourseRequest(
    topic=course_intent['topic'],
    user_id=str(current_user.id),
    level="beginner",
    duration_minutes=30
)

a2a_response = await orchestrator.generate_course(course_request)
```

**Step 3: Multi-Agent Pipeline Executes**:
```
Orchestrator
    ├─> PedagogyAgent        (designs curriculum)
    ├─> CinematicDirectorAgent (creates narrative)
    ├─> VisualDirectorAgent   (generates visual prompts)
    ├─> VoiceAgent            (creates narration)
    └─> QACheckerAgent        (validates quality)
           ↓
    Output: Artifacts (A2A Protocol)
```

**Step 4: Extract Artifacts** (`chat.py` line ~223):
```python
artifacts = a2a_response.output_artifacts
# List[Artifact] where each has:
#   - type: ArtifactType (CURRICULUM_STRUCTURE, ASSESSMENT, etc.)
#   - data: Dict[str, Any] (structured content)
#   - name: str
#   - quality_score: float
```

**Step 5: Translate to A2UI** (`chat.py` line ~225-230):
```python
ui_components = []
for artifact in artifacts:
    translated = translate_artifact_to_ui_component(artifact)
    if translated:
        ui_components.append(translated)
```

**Step 6: Return Response** (`chat.py` line ~237-243):
```python
return ChatResponse(
    response="I've created a course on Python! Let's dive in. 🚀",
    model_used="A2A Multi-Agent Pipeline",
    success=True,
    ui_component=ui_components  # List[Dict[str, Any]]
)
```

---

### 3. Backend Response Structure

**HTTP Response**:
```json
{
    "response": "I've created a course on Python! Let's dive in. 🚀",
    "model_used": "A2A Multi-Agent Pipeline",
    "success": true,
    "ui_component": [
        {
            "type": "course_roadmap",
            "course_roadmap": {
                "title": "Introduction to Python",
                "topic": "Python Programming",
                "level": "beginner",
                "modules": [
                    {
                        "title": "Getting Started",
                        "description": "Learn Python basics",
                        "lessons": [
                            {
                                "title": "What is Python?",
                                "duration": "10 min"
                            },
                            {
                                "title": "Installing Python",
                                "duration": "15 min"
                            }
                        ]
                    },
                    {
                        "title": "Variables and Data Types",
                        "description": "Core Python concepts",
                        "lessons": [
                            {
                                "title": "Variables",
                                "duration": "12 min"
                            },
                            {
                                "title": "Data Types",
                                "duration": "18 min"
                            }
                        ]
                    }
                ]
            }
        }
    ]
}
```

---

### 4. iOS Processing

**Step 1: Decode Response** (`BackendAIService.swift` line ~164-210):
```swift
struct BackendAIChatResponse: Codable {
    let response: String?
    let contentTypes: [A2UIContent]?  // Maps from "ui_component"
    
    enum CodingKeys: String, CodingKey {
        case response
        case contentTypes = "ui_component"  // ✅ Backend field mapping
    }
}
```

**Step 2: Parse A2UI Content** (`UnifiedChatService.parseResponse()` line ~348-450):
```swift
for item in a2uiContent {
    switch item.type {
    case .courseRoadmap:
        if let roadmap = item.courseRoadmap {
            // Create CourseCreationData
            let modules = roadmap.modules.map { mod in
                CourseModuleData(
                    id: UUID().uuidString,
                    title: mod.title,
                    description: mod.description ?? "",
                    lessons: (mod.lessons ?? []).map { les in
                        CourseLessonData(
                            id: UUID().uuidString,
                            title: les.title,
                            duration: les.duration ?? "10 min"
                        )
                    }
                )
            }
            
            courseData = CourseCreationData(
                id: "course_\(UUID().uuidString.prefix(8))",
                title: roadmap.title,
                topic: roadmap.topic,
                level: roadmap.level,
                modules: modules
            )
            
            // Add to Stack automatically
            stackStore.upsertCourse(...)
        }
    
    case .quiz:
        // Handle quiz rendering
        
    case .topicSelection:
        // Handle topic picker
    }
}
```

**Step 3: Create LyoMessage** (`UnifiedChatService.sendMessage()` line ~176-192):
```swift
let aiMessage = LyoMessage(
    id: UUID().uuidString,
    content: parsedContent,
    isFromUser: false,
    timestamp: Date(),
    contentTypes: a2uiElements,  // List[MessageContentType]
    // ...
)

messages.append(aiMessage)
```

**Step 4: Render UI** (`A2UIContentViews.swift`):
```swift
// CourseRoadmapCardView renders the interactive course card
CourseRoadmapCardView(
    title: roadmap.title,
    modules: modules,
    totalModules: modules.count,
    completedModules: 0,
    onStart: {
        // Navigate to Classroom
    }
)
```

---

## Translation Mappings

| A2A Artifact Type | A2UI Component Type | iOS Swift Type |
|-------------------|---------------------|----------------|
| `CURRICULUM_STRUCTURE` | `course_roadmap` | `CourseCreationData` |
| `ASSESSMENT` | `quiz` | `QuizData` |
| `VISUAL_PROMPT` | (skipped) | N/A |

---

## Code Locations

### Backend
- **Main Endpoint**: `/lyo_app/api/v1/chat.py`
- **Intent Detection**: Line ~20-48
- **Translation Layer**: Line ~58-125
- **Orchestrator Integration**: Line ~204-243
- **Response Model**: Line ~165-176

### iOS
- **Service Layer**: `Sources/Services/BackendAIService.swift`
  - Response decoding: Line ~164-210
  - CodingKeys mapping: Line ~189-207
  
- **Chat Logic**: `Sources/Services/UnifiedChatService.swift`
  - Message sending: Line ~95-200
  - Response parsing: Line ~348-500
  
- **UI Rendering**: `Sources/Views/Chat/A2UIContentViews.swift`
  - Course roadmap: Line ~79-150
  - Quiz cards: Line ~200-300

---

## Testing

### Run Backend Tests
```bash
cd /Users/hectorgarcia/Desktop/LyoBackendJune
python3 test_a2a_translation_e2e.py
```

**Expected Output**:
```
✅ ALL TESTS PASSED
Translation Layer is ready for production!
```

### Test in iOS Simulator
1. Build and run app
2. Go to Chat tab
3. Type: "Create a course on Python"
4. Verify:
   - Course roadmap card appears
   - Modules and lessons are listed
   - "Start Learning" button works
   - Course added to Stack

---

## Key Design Decisions

### 1. Why List Instead of Single Object?
**Backend returns**: `ui_component: List[Dict]`  
**iOS expects**: `contentTypes: [A2UIContent]`

Multiple agents can produce multiple artifacts, so we support returning multiple UI components in a single response.

### 2. Why Flat Structure in A2UIContent?
```swift
struct A2UIContent {
    let type: A2UIContentType
    let courseRoadmap: A2UICourseRoadmap?  // Optional fields
    let quiz: A2UIQuiz?
    let topics: [A2UITopicOption]?
}
```

This allows type-safe optional unwrapping in Swift while maintaining clean JSON structure.

### 3. Why Snake_Case → CamelCase Mapping?
Backend Python uses `snake_case` (PEP 8), iOS Swift uses `camelCase` (Swift conventions). CodingKeys handle the mapping automatically.

---

## Troubleshooting

### Issue: iOS not receiving ui_component
**Check**: Backend CodingKeys mapping
```swift
case contentTypes = "ui_component"  // Must match backend field name
```

### Issue: Decoding error in iOS
**Check**: Backend structure matches iOS model
```python
# Backend must return:
{
    "type": "course_roadmap",
    "course_roadmap": {...}  # Not "props"!
}
```

### Issue: Intent not detected
**Check**: Regex patterns in `detect_course_creation_intent()`
```python
patterns = [
    r"create (?:a |an )?course (?:on|about|for) (.+)",
    r"make (?:a |an )?course (?:on|about|for) (.+)",
]
```

---

## Summary

✅ **Complete**: Backend → iOS translation layer fully implemented  
✅ **Tested**: All unit tests passing  
✅ **Production Ready**: Can handle course creation requests end-to-end  
✅ **Extensible**: Easy to add new artifact types and UI components  

The system successfully bridges internal A2A protocol (agent communication) with external A2UI protocol (UI instructions), enabling rich, structured responses in the iOS chat interface.
