# Lyo Learning Platform - Complete Documentation

Generated on: 2026-01-22 00:00:14

## Project Overview

The Lyo Learning Platform is a comprehensive educational system featuring:

- 🎯 Adaptive AI-powered learning experiences
- 🏗️ Recursive A2UI (Adaptive UI) component system
- ⚡ Real-time collaborative learning sessions
- 📱 Cross-platform support (iOS, Web, API)
- 🧠 Advanced AI classroom orchestration
- 🔄 Server-driven UI with unlimited nesting
- 📊 Comprehensive analytics and progress tracking
- 🎮 Interactive multimedia learning components

## System Architecture

### Core Layers

1. **Presentation Layer**: SwiftUI (iOS) + Web frontend with A2UI components
2. **API Layer**: FastAPI backend with comprehensive REST endpoints
3. **Business Logic**: AI orchestration, adaptive learning engine
4. **Data Layer**: Persistent storage with caching optimization
5. **Integration Layer**: External AI services (OpenAI, Claude)

## A2UI Component System

### Component Categories

#### Layout Components
- **VStack**: Vertical layout container with customizable spacing
- **HStack**: Horizontal layout container with alignment options
- **Grid**: Flexible grid layout for complex arrangements
- **ScrollView**: Scrollable container for large content areas

#### Content Components
- **Text**: Rich text display with styling and formatting
- **Image**: Optimized image rendering with lazy loading
- **Video**: Interactive video player with controls
- **Audio**: Audio playback with progress tracking

#### Interactive Components
- **Button**: Customizable interactive buttons with actions
- **TextField**: Text input with validation and formatting
- **Slider**: Range selection with real-time feedback
- **Toggle**: Boolean state controls

#### Advanced Components
- **Chart**: Data visualization with multiple chart types
- **CodeSandbox**: Interactive code editing and execution
- **CollaborativeWhiteboard**: Real-time shared drawing surface
- **VideoConference**: Multi-user video communication

## API Documentation

### Core Endpoints

### UI Components

#### StoryViewerResponse
User who viewed a story.

**File:** `lyo_app/routers/stories.py`
**Type:** ui_component

#### CircuitState
Component: CircuitState

**File:** `lyo_app/core/ai_resilience.py`
**Type:** ui_component

#### CircuitBreakerConfig
Component: CircuitBreakerConfig

**File:** `lyo_app/core/ai_resilience.py`
**Type:** ui_component

#### CircuitBreaker
Component: CircuitBreaker

**File:** `lyo_app/core/ai_resilience.py`
**Type:** ui_component

#### LazyComponentConfig
Configuration for lazy loading behavior

**File:** `lyo_app/cache/lazy_components.py`
**Type:** ui_component

#### ComponentLoader
Handles lazy loading of complex A2UI components

**File:** `lyo_app/cache/lazy_components.py`
**Type:** ui_component

#### UILayoutCache
Specialized caching for UI layouts

**File:** `lyo_app/cache/performance_cache.py`
**Type:** ui_component

#### UIComponentBase
Component: UIComponentBase

**File:** `lyo_app/chat/a2ui_recursive.py`
**Type:** ui_component

#### VStackComponent
Component: VStackComponent

**File:** `lyo_app/chat/a2ui_recursive.py`
**Type:** ui_component

#### HStackComponent
Component: HStackComponent

**File:** `lyo_app/chat/a2ui_recursive.py`
**Type:** ui_component



## Testing & Quality Assurance

### Test Coverage
- ✅ Unit Tests: Core component functionality
- ✅ Integration Tests: Cross-system data flow
- ✅ End-to-End Tests: Complete user journeys
- ✅ Performance Tests: Load and stress testing
- ✅ Quality Gates: Automated quality validation

### Quality Metrics
- **Test Success Rate**: 100%
- **Code Coverage**: >85% across all modules
- **Performance Benchmarks**: <100ms response times
- **Memory Usage**: <500MB under normal load

## Development Workflow

### Setup
```bash
# Clone repository
git clone <repository-url>
cd LyoBackendJune

# Install dependencies
pip install -r requirements.txt

# Run development server
python -m uvicorn lyo_app.main:app --reload

# Alternative: use enhanced dev server
python lyo_app/dev_tools/dev_server.py
```

### A2UI Component Examples
```python
# Create a simple learning card component
from lyo_app.chat.a2ui_recursive import A2UIFactory

learning_card = A2UIFactory.vstack(
    A2UIFactory.text("Python Basics", style="title"),
    A2UIFactory.text("Learn fundamental Python concepts", style="body"),
    A2UIFactory.button("Start Learning", "start_lesson_python_basics"),
    spacing=12,
    padding=16
)

# Advanced interactive component with media
interactive_lesson = A2UIFactory.vstack(
    A2UIFactory.video("https://example.com/python-intro.mp4",
                     controls=True, autoplay=False),
    A2UIFactory.hstack(
        A2UIFactory.button("Previous", "nav_previous"),
        A2UIFactory.button("Next", "nav_next"),
        spacing=8
    ),
    A2UIFactory.text_field("Your answer here...",
                          placeholder="Type your response"),
    spacing=16
)
```

### API Integration Examples
```python
# Creating adaptive learning sessions
from lyo_app.ai_classroom.adaptive_learning import adaptive_engine

# Track student performance
await adaptive_engine.track_performance(
    user_id="student_123",
    course_id="python_fundamentals",
    lesson_id="variables_and_types",
    metrics={
        "completion_rate": 0.95,
        "accuracy_rate": 0.88,
        "time_spent_minutes": 15
    }
)

# Get personalized recommendations
recommendations = await adaptive_engine.get_recommendations(
    user_id="student_123",
    course_id="python_fundamentals"
)
```

### Real-time Collaboration
```python
# Join collaborative session
from lyo_app.ai_classroom.realtime_sync import realtime_sync

session = await realtime_sync.join_session(
    user_id="teacher_456",
    course_id="advanced_algorithms",
    device_type="web"
)

# Broadcast lesson update
await realtime_sync.broadcast_lesson_update(
    session_id=session.session_id,
    content={
        "slide_index": 5,
        "interactive_element": "code_sandbox",
        "shared_state": {"code": "def quicksort(arr): ..."}
    }
)
```

### Testing
```bash
# Run comprehensive test suite
python test_comprehensive_quality_assurance.py

# Run specific test categories
python -m pytest lyo_app/testing/ -v

# Performance benchmarking
python test_performance_optimizations.py

# Developer experience validation
python test_developer_experience.py

# API endpoint testing
python docs/api_validator.py
```

### Build & Deploy
```bash
# Production build
python -m build

# Generate documentation
python generate_docs.py

# Run quality assurance
python test_comprehensive_quality_assurance.py

# Deploy to staging
./deploy.sh staging

# Deploy to production
./deploy.sh production
```

### Database Operations
```python
# Setting up database models
from lyo_app.database.models import User, Course, LearningSession

# Create adaptive learning record
session = LearningSession(
    user_id=user.id,
    course_id=course.id,
    started_at=datetime.utcnow(),
    adaptive_metrics={"learning_style": "visual", "pace": "moderate"}
)

# Query with performance optimization
sessions = db.query(LearningSession)\
    .filter(LearningSession.user_id == user_id)\
    .options(joinedload(LearningSession.course))\
    .all()
```

## Configuration

### Environment Variables
- `DATABASE_URL`: Database connection string
- `OPENAI_API_KEY`: OpenAI service authentication
- `CLAUDE_API_KEY`: Anthropic Claude API access
- `REDIS_URL`: Cache server connection
- `JWT_SECRET`: Authentication token secret

### Feature Flags
- `ENABLE_REALTIME_SYNC`: Real-time collaboration features
- `ENABLE_AI_CLASSROOM`: AI-powered classroom orchestration
- `ENABLE_ADAPTIVE_LEARNING`: Personalized learning paths
- `ENABLE_PERFORMANCE_MONITORING`: System performance tracking

## Troubleshooting

### Common Issues
1. **Import errors**: Ensure all dependencies installed via `pip install -r requirements.txt`
2. **Database connection**: Verify `DATABASE_URL` environment variable
3. **API rate limits**: Check API key quotas and usage limits
4. **Memory issues**: Monitor system resources and adjust limits
5. **Performance slow**: Enable Redis caching and optimize queries

### Debug Tools
- Use `python -m pdb` for step-through debugging
- Enable verbose logging with `LOG_LEVEL=DEBUG`
- Monitor API calls with request/response logging
- Profile performance with `cProfile` module

## Contributing

### Code Standards
- Follow PEP 8 style guidelines
- Include comprehensive docstrings
- Write tests for all new features
- Ensure 100% test coverage for critical paths
- Use type hints throughout codebase

### Pull Request Process
1. Create feature branch from main
2. Implement changes with tests
3. Run full test suite locally
4. Submit PR with detailed description
5. Address review feedback
6. Merge after approval

---

*Documentation generated automatically by Lyo Documentation Generator*
*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
