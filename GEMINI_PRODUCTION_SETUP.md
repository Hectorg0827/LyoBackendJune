# Production Configuration Guide for Gemini Enhancements

## Environment Variables

Add to your `.env` file:

```bash
# Redis Configuration (for curriculum caching)
REDIS_URL=redis://localhost:6379/0
# Or for production:
# REDIS_URL=redis://username:password@your-redis-host:6379/0

# Google Gemini API Key (already configured)
GOOGLE_API_KEY=your_gemini_api_key_here

# Optional: Feature flags
ENABLE_CURRICULUM_CACHING=true
ENABLE_STREAMING_GENERATION=true
ENABLE_ANALYTICS_TRACKING=true
ENABLE_SMART_ROUTING=true
```

## Redis Setup

### Local Development (macOS)
```bash
# Install Redis
brew install redis

# Start Redis
brew services start redis

# Verify it's running
redis-cli ping
# Should return: PONG
```

### Production (Docker)
```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

volumes:
  redis-data:
```

### Production (Cloud)
- **Google Cloud**: Cloud Memorystore for Redis
- **AWS**: ElastiCache for Redis  
- **Azure**: Azure Cache for Redis
- **Heroku**: Heroku Redis add-on

## Database Migrations

```bash
# Create migration for analytics tables (when implementing database storage)
alembic revision --autogenerate -m "Add course generation analytics tables"

# Apply migration
alembic upgrade head
```

## Testing Endpoints

```bash
# Base URL
BASE_URL="http://localhost:8000"

# 1. Test cost estimation
curl -X POST "$BASE_URL/api/v2/courses/estimate-cost" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Python Programming for Beginners",
    "quality_tier": "balanced",
    "enable_code_examples": true,
    "enable_practice_exercises": true,
    "enable_final_quiz": true
  }'

# 2. Test course generation (non-streaming)
curl -X POST "$BASE_URL/api/v2/courses/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Create a Python course for beginners",
    "quality_tier": "fast",
    "enable_code_examples": true,
    "max_budget_usd": 0.10
  }'

# 3. Test streaming generation
curl -X POST "$BASE_URL/api/v2/courses/generate/stream" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "request": "Quick course on JavaScript basics",
    "quality_tier": "fast"
  }'

# 4. Test analytics (replace USER_ID)
curl "$BASE_URL/api/v2/courses/analytics/user/USER_ID?days=30"

# 5. Test system analytics
curl "$BASE_URL/api/v2/courses/analytics/system?days=7"
```

## Performance Tuning

### Redis Caching
```python
# Warm popular topics on startup
from lyo_app.ai_agents.multi_agent_v2.caching import get_curriculum_cache

cache = get_curriculum_cache()
popular_topics = [
    {"topic": "Python Programming", "level": "beginner", "lessons": 8},
    {"topic": "JavaScript Basics", "level": "beginner", "lessons": 6},
    {"topic": "Data Science Fundamentals", "level": "intermediate", "lessons": 10},
    # Add more popular topics
]
await cache.warm_cache(popular_topics)
```

### Rate Limiting
```python
# Add to enhanced_main.py startup
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to cost estimation endpoint
@limiter.limit("10/minute")
@router.post("/estimate-cost")
async def estimate_cost(...):
    ...
```

## Monitoring

### Prometheus Metrics
```python
# Add custom metrics
from prometheus_client import Counter, Histogram

course_generations = Counter(
    'course_generations_total',
    'Total course generations',
    ['quality_tier', 'status']
)

generation_duration = Histogram(
    'course_generation_duration_seconds',
    'Course generation duration',
    ['quality_tier']
)
```

### Logging
```python
# Structured logging for analytics
import structlog

logger = structlog.get_logger()

logger.info(
    "course_generated",
    course_id=course_id,
    quality_tier=tier,
    cost_usd=cost,
    duration_sec=duration,
    user_id=user_id
)
```

## Cost Management

### Budget Alerts
```python
# Set up alert thresholds
DAILY_BUDGET_LIMIT_USD = 10.0
ALERT_THRESHOLD = 0.80  # 80%

# Monitor in analytics endpoint
if daily_cost >= DAILY_BUDGET_LIMIT_USD * ALERT_THRESHOLD:
    send_alert(f"Approaching daily budget: ${daily_cost:.2f} / ${DAILY_BUDGET_LIMIT_USD}")
```

### Cost Tracking
```python
# Log all API calls
async def track_api_usage(
    user_id: str,
    model: str,
    tokens: int,
    cost: float
):
    # Store in database
    await db.execute(
        "INSERT INTO api_usage (user_id, model, tokens, cost, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, model, tokens, cost, datetime.utcnow())
    )
```

## Security

### API Key Rotation
```python
# Rotate Gemini API key periodically
# Store in secrets manager (GCP Secret Manager, AWS Secrets Manager, etc.)

import google.cloud.secretmanager as secretmanager

def get_gemini_api_key():
    client = secretmanager.SecretManagerServiceClient()
    name = "projects/PROJECT_ID/secrets/GEMINI_API_KEY/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
```

### Rate Limiting by User
```python
# Per-user quotas
USER_DAILY_COURSE_LIMIT = 10

async def check_user_quota(user_id: str) -> bool:
    today_count = await get_user_generation_count_today(user_id)
    return today_count < USER_DAILY_COURSE_LIMIT
```

## Deployment Checklist

- [ ] Redis deployed and accessible
- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] Monitoring/alerting configured
- [ ] Rate limits configured
- [ ] Budget alerts configured
- [ ] API keys rotated and secured
- [ ] Health check endpoints verified
- [ ] Load testing completed
- [ ] Documentation updated

## Scaling Considerations

### Horizontal Scaling
- Use Redis for shared cache across instances
- Store analytics in centralized database
- Use message queue for background generation jobs

### Vertical Scaling
- Increase `parallel_lesson_batch_size` for more concurrent lesson generation
- Tune Redis memory limits
- Optimize database queries with indexes

## Troubleshooting

### Redis Connection Issues
```bash
# Check Redis is running
redis-cli ping

# Check connection from Python
python3 -c "import redis; r = redis.from_url('redis://localhost:6379'); print(r.ping())"
```

### Slow Generation
- Enable curriculum caching
- Use FAST quality tier for testing
- Check Gemini API rate limits
- Monitor token usage

### High Costs
- Review quality tier selection
- Enable feature toggles (disable unnecessary features)
- Implement per-user budgets
- Use smart routing for simple queries

## Support

- Check logs: `lyo_app/logs/`
- Monitor metrics: `/metrics` endpoint (if Prometheus enabled)
- View analytics: `/api/v2/courses/analytics/system`
