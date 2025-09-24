# LyoBackend Development Reference

**Quick reference for agents building the LyoBackend system**

## 🎯 Core Principles

### NO MOCK DATA POLICY
- ❌ **NEVER** return hardcoded responses like "Sample question 1"
- ❌ **NEVER** use fallback mock data
- ✅ **ALWAYS** use real AI APIs (Gemini, OpenAI)
- ✅ **ALWAYS** query real database data
- ✅ **FAIL GRACEFULLY** if real services unavailable

### Production-First Architecture
- Real PostgreSQL database (no SQLite in production)
- Real Redis caching
- Real JWT authentication
- Real AI integration with proper error handling

---

## 🚀 Quick Setup Commands

```bash
# Environment setup
export GEMINI_API_KEY="your-real-api-key"
export DATABASE_URL="postgresql://..."
export REDIS_URL="redis://..."
export JWT_SECRET_KEY="secure-256-bit-key"

# Start development server
/Users/republicalatuya/Desktop/LyoBackendJune/.venv/bin/python production_cloud_main.py

# Test endpoints
curl http://localhost:8081/health
curl http://localhost:8081/api/v1/ai/study-session -X POST -H "Content-Type: application/json" -d '{"resourceId": "test", "userInput": "hello"}'
```

---

## 📋 Essential API Endpoints

### Authentication
```http
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
GET  /api/v1/auth/profile
```

### AI Study Features
```http
POST /api/v1/ai/study-session     # Socratic tutoring
POST /api/v1/ai/generate-quiz     # Quiz generation  
POST /api/v1/ai/analyze-answer    # Answer feedback
POST /api/v1/ai/generate-course   # Course creation
```

### Social Features
```http
GET  /api/v1/feeds/personalized   # User feed
GET  /api/v1/feeds/trending       # Trending content
POST /api/v1/posts                # Create post
GET  /api/v1/posts/{id}/comments  # Post comments
```

### Gamification
```http
GET  /api/v1/gamification/profile # User XP/achievements
POST /api/v1/gamification/award-xp # Award points
GET  /api/v1/gamification/leaderboard # Rankings
```

---

## 🗄️ Database Models

### Core Tables
```sql
users              -- User accounts and auth
user_profiles      -- Extended user info and preferences
courses            -- Course definitions and metadata
modules            -- Course modules/chapters
lessons            -- Individual lessons
progress           -- User learning progress
posts              -- Social media posts
comments           -- Post comments
achievements       -- Gamification achievements
user_achievements  -- User's earned achievements
```

### Key Relationships
```
User -> UserProfile (1:1)
User -> Progress (1:N) 
User -> Posts (1:N)
Course -> Modules (1:N)
Module -> Lessons (1:N)
User <-> Courses (N:N via enrollments)
```

---

## 🤖 AI Integration Rules

### Gemini API Usage
```python
# Primary model
model = genai.GenerativeModel('models/gemini-1.5-flash')

# For complex tasks
model = genai.GenerativeModel('models/gemini-1.5-pro')

# Always include error handling
try:
    response = model.generate_content(prompt)
    return response.text
except Exception as e:
    logger.error(f"AI generation failed: {e}")
    raise HTTPException(status_code=503, detail="AI service unavailable")
```

### AI Response Standards
- **Quiz Generation**: Must return valid JSON array
- **Study Sessions**: Socratic method, ask probing questions
- **Course Generation**: Structured modules with clear objectives
- **Content Quality**: Educational, age-appropriate, factually correct

---

## 🔐 Authentication Flow

### JWT Token Structure
```json
{
  "sub": "user_id", 
  "email": "user@example.com",
  "user_type": "student|teacher|admin",
  "exp": 1694366400,
  "iat": 1694364600
}
```

### Protected Route Pattern
```python
from lyo_app.auth.dependencies import get_current_user

@router.post("/protected-endpoint")
async def protected_endpoint(
    current_user: User = Depends(get_current_user)
):
    # Route implementation
    pass
```

---

## ⚡ Performance Requirements

### Response Time Targets
- **Static content**: < 100ms
- **Database queries**: < 200ms  
- **AI generation**: < 3s
- **File operations**: < 1s

### Caching Strategy
```python
# Redis cache keys
session_cache = f"session:{user_id}"          # 30min TTL
ai_response = f"ai:{hash(prompt)}"           # 1hr TTL  
user_prefs = f"user_prefs:{user_id}"        # 24hr TTL
```

---

## 🛠️ Common Code Patterns

### Service Layer Pattern
```python
class AIStudyService:
    def __init__(self, ai_client, db_session):
        self.ai_client = ai_client
        self.db_session = db_session
    
    async def generate_quiz(self, content: str) -> Quiz:
        # Business logic here
        pass
```

### Repository Pattern  
```python
class UserRepository:
    def __init__(self, db_session):
        self.db_session = db_session
    
    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db_session.execute(
            select(User).where(User.email == email)
        )
        return result.scalars().first()
```

### Error Handling Pattern
```python
try:
    result = await dangerous_operation()
    return {"success": True, "data": result}
except ValidationError as e:
    raise HTTPException(status_code=400, detail=str(e))
except ServiceError as e:
    logger.error(f"Service error: {e}")
    raise HTTPException(status_code=503, detail="Service temporarily unavailable")
```

---

## 🧪 Testing Checklist

### Before Deploying
- [ ] All endpoints return real data (no mocks)
- [ ] AI integration working with actual API keys
- [ ] Database queries use real tables
- [ ] Authentication flow complete
- [ ] Error handling implemented
- [ ] Rate limiting configured
- [ ] Logging properly structured

### Test Commands
```bash
# Health check
curl http://localhost:8081/health | jq

# AI functionality test  
curl http://localhost:8081/api/v1/test-real | jq

# Database connectivity test
python -c "from lyo_app.core.database import engine; print('DB OK')"
```

---

## 🚨 Common Pitfalls to Avoid

### ❌ Don't Do This
```python
# Mock responses
return {"questions": [{"question": "Sample question 1"}]}

# Hardcoded data
trending_items = [f"Trending Item {i}" for i in range(10)]

# Missing error handling
response = ai_client.generate(prompt)  # No try/catch

# Insecure database queries
query = f"SELECT * FROM users WHERE id = {user_id}"  # SQL injection risk
```

### ✅ Do This Instead  
```python
# Real AI responses
response = await ai_client.generate_content(prompt)
return parse_quiz_response(response.text)

# Real database queries
trending = await get_trending_posts_from_db(time_window="24h")

# Proper error handling
try:
    response = await ai_client.generate_content(prompt)
except Exception as e:
    logger.error(f"AI failed: {e}")
    raise HTTPException(status_code=503, detail="AI service unavailable")

# Parameterized queries
result = await session.execute(
    select(User).where(User.id == user_id)
)
```

---

## 📁 File Structure Reference

```
lyo_app/
├── core/
│   ├── config.py           # Settings and environment
│   ├── database.py         # DB connection and models
│   ├── security.py         # JWT and auth utilities
│   └── ai_resilience.py    # AI service management
├── api/v1/
│   ├── auth.py            # Authentication endpoints
│   ├── ai_study.py        # AI tutoring endpoints
│   ├── courses.py         # Course management
│   ├── feeds.py           # Social content feeds
│   └── gamification.py    # Points and achievements
├── models/
│   ├── user.py            # User data models
│   ├── course.py          # Course data models
│   └── social.py          # Social feature models
└── services/
    ├── ai_service.py      # AI business logic
    ├── user_service.py    # User operations
    └── content_service.py # Content management
```

---

## 🔄 Development Workflow

1. **Read specification**: Understand requirements fully
2. **Check existing code**: Avoid duplicate functionality  
3. **Write tests first**: TDD approach recommended
4. **Implement with real services**: No mocks allowed
5. **Test thoroughly**: Verify with actual API calls
6. **Document changes**: Update this reference if needed

---

**Remember**: Every line of code should contribute to a production-ready, scalable educational platform. No shortcuts, no mock data, no placeholder responses. Build it right the first time.
