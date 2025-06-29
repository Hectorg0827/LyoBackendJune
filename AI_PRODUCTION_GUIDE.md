# LyoApp AI Backend - Production-Ready Gemma 4 Integration

## Overview

This document outlines the production-ready AI system for LyoApp, featuring Gemma 4 as the primary LLM with comprehensive multi-language support, robust error handling, and enterprise-scale monitoring.

## 🎯 Key Features Implemented

### 1. Advanced AI Orchestration
- **Multi-Model Support**: Gemma 4 (on-device + cloud), GPT-4, Claude 3.5 Sonnet
- **Intelligent Routing**: Automatic model selection based on task complexity
- **Circuit Breaker Pattern**: Fault tolerance with exponential backoff
- **Cost Optimization**: Daily cost limits and intelligent routing
- **Performance Monitoring**: Real-time metrics and health checks

### 2. Production-Grade Gemma 4 Client
- **Hybrid Deployment**: On-device for privacy + cloud for complex tasks
- **Multi-Language Support**: 12 languages with native prompting
- **Content Safety**: Built-in safety filtering and content moderation
- **Response Caching**: Intelligent caching with MD5 key generation
- **Auto-Fallback**: Seamless fallback between deployment modes

### 3. Enhanced Agent Capabilities
- **Curriculum Agent**: AI-driven course creation with learning path optimization
- **Curation Agent**: Content quality assessment and recommendation
- **Mentor Agent**: Adaptive conversation management with engagement tracking
- **Feed Agent**: Intelligent content ranking and personalization
- **Sentiment Agent**: Real-time sentiment analysis and intervention triggers

### 4. Production Infrastructure
- **Security**: CORS, rate limiting, request size limits, security headers
- **Monitoring**: Prometheus metrics, health checks, error tracking
- **Scalability**: Async processing, connection pooling, circuit breakers
- **Deployment**: Docker support, systemd services, gunicorn configuration

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                     │
├─────────────────────────────────────────────────────────────┤
│                   AI Orchestrator                          │
│  ┌─────────────────┐  ┌──────────────────────────────────┐ │
│  │  Gemma 4 Client │  │     Cloud LLM Client             │ │
│  │  - On-device    │  │  - OpenAI GPT-4                  │ │
│  │  - Cloud API    │  │  - Anthropic Claude              │ │
│  │  - Multi-lang   │  │  - Rate limiting                 │ │
│  └─────────────────┘  └──────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    AI Agents Layer                         │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐ │
│  │  Curriculum  │ │   Curation   │ │      Mentor         │ │
│  │    Agent     │ │    Agent     │ │      Agent          │ │
│  └──────────────┘ └──────────────┘ └─────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                 Production Services                         │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐ │
│  │   Database   │ │    Redis     │ │     Celery          │ │
│  │ (PostgreSQL) │ │   (Cache)    │ │ (Background Jobs)   │ │
│  └──────────────┘ └──────────────┘ └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Automated Deployment
```bash
# Run the automated deployment script
./deploy_production.sh
```

### 2. Manual Setup
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.production .env
# Edit .env with your production values

# Run database migrations
alembic upgrade head

# Start the application
gunicorn lyo_app.main:app -c gunicorn.conf.py
```

## 🔧 Configuration

### Environment Variables

#### Core Settings
```bash
# Application
DEBUG=false
ENVIRONMENT=production
SECRET_KEY=your-super-secret-key

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/lyo_db

# Redis
REDIS_URL=redis://localhost:6379/0
```

#### AI Configuration
```bash
# Gemma 4
GEMMA_4_MODEL_PATH=/app/models/gemma-4-9b
GEMMA_4_CLOUD_ENDPOINT=https://api.gemma.ai/v1
GEMMA_4_API_KEY=your-gemma-4-key

# OpenAI
OPENAI_API_KEY=your-openai-key
OPENAI_MODEL_DEFAULT=gpt-4o-mini

# Anthropic
ANTHROPIC_API_KEY=your-anthropic-key

# AI Features
AI_DAILY_COST_LIMIT=50.0
AI_ENABLE_MULTI_LANGUAGE=true
AI_DEFAULT_LANGUAGE=en
```

### Supported Languages
- English (en) - Primary
- Spanish (es)
- French (fr)
- German (de)
- Italian (it)
- Portuguese (pt)
- Russian (ru)
- Chinese (zh)
- Japanese (ja)
- Korean (ko)
- Arabic (ar)
- Hindi (hi)

## 📡 API Endpoints

### AI Agent Endpoints
```
POST /api/v1/ai/mentor/chat                 # Chat with AI mentor
GET  /api/v1/ai/mentor/conversation/{id}    # Get conversation history
POST /api/v1/ai/mentor/rate                 # Rate interaction

POST /api/v1/ai/curriculum/course-outline   # Generate course outline
POST /api/v1/ai/curriculum/lesson-content   # Generate lesson content

POST /api/v1/ai/curation/evaluate           # Evaluate content quality
POST /api/v1/ai/curation/tag               # Tag and categorize content
POST /api/v1/ai/curation/gaps              # Identify content gaps

GET  /api/v1/ai/analytics/user/{id}         # User analytics
POST /api/v1/ai/analytics/batch            # Batch analysis
```

### Monitoring Endpoints
```
GET  /api/v1/ai/health                      # AI system health check
GET  /api/v1/ai/performance/stats           # Performance statistics
GET  /api/v1/ai/metrics/real-time          # Real-time metrics
POST /api/v1/ai/analyze/model-recommendation # Model recommendations

# Admin endpoints
POST /api/v1/ai/admin/circuit-breaker/reset # Reset circuit breaker
POST /api/v1/ai/maintenance/cleanup         # System cleanup
```

### WebSocket Endpoints
```
WS   /api/v1/ai/ws/{user_id}                # Real-time AI chat
```

## 🔍 Monitoring & Observability

### Health Checks
```bash
# Application health
curl http://localhost:8000/health

# AI system health
curl http://localhost:8000/api/v1/ai/health

# Detailed performance stats
curl -H "Authorization: Bearer <token>" \
     http://localhost:8000/api/v1/ai/performance/stats
```

### Metrics
The application exposes Prometheus metrics at `/metrics`:
- Request counts and durations
- AI model usage statistics
- Error rates and circuit breaker status
- Resource utilization

### Logging
Structured logging with:
- Request correlation IDs
- AI model performance tracking
- Error tracing and debugging
- User interaction analytics

## 🛡️ Security Features

### Authentication & Authorization
- JWT-based authentication
- Role-based access control (RBAC)
- Admin-only endpoints for sensitive operations

### Rate Limiting
- Global rate limiting per IP
- User-specific rate limits
- Endpoint-specific limits for AI operations

### Input Validation
- Request size limits
- Content safety filtering
- Input sanitization
- SQL injection prevention

### Security Headers
- CORS configuration
- Security headers middleware
- Content-Type validation

## 🔧 Production Optimizations

### Performance
- **Connection Pooling**: Async database connections
- **Caching**: Redis-based response caching
- **Background Jobs**: Celery for long-running tasks
- **Load Balancing**: Multi-worker gunicorn setup

### Scalability
- **Horizontal Scaling**: Stateless design
- **Circuit Breakers**: Prevent cascade failures
- **Auto-Retry**: Exponential backoff for transient failures
- **Resource Management**: Memory-efficient model loading

### Cost Optimization
- **Daily Limits**: Configurable cost caps
- **Smart Routing**: Route simple tasks to on-device models
- **Caching Strategy**: Reduce duplicate API calls
- **Model Selection**: Use most cost-effective model for task

## 🚨 Error Handling

### Circuit Breaker Pattern
- Automatic failure detection
- Graceful degradation
- Auto-recovery with timeout
- Admin override capabilities

### Fallback Mechanisms
- Primary → Secondary model fallback
- Cloud → On-device fallback
- Cached → Live response fallback
- English → User language fallback

### Error Recovery
- Retry logic with exponential backoff
- Dead letter queues for failed jobs
- Health check recovery
- Manual intervention endpoints

## 📈 Scaling Guidelines

### Vertical Scaling
- **CPU**: 4+ cores for model inference
- **Memory**: 8GB+ for on-device models
- **Storage**: SSD for model files and cache

### Horizontal Scaling
- **Load Balancer**: Nginx or AWS ALB
- **Worker Nodes**: Stateless FastAPI instances
- **Database**: PostgreSQL with read replicas
- **Cache**: Redis cluster

### Cost Management
- Monitor daily spend via `/api/v1/ai/performance/stats`
- Set appropriate `AI_DAILY_COST_LIMIT`
- Use on-device models for simple tasks
- Implement request batching for efficiency

## 🔄 Maintenance

### Regular Tasks
```bash
# Update AI performance stats
curl -X POST /api/v1/ai/maintenance/cleanup

# Reset circuit breakers if needed
curl -X POST /api/v1/ai/admin/circuit-breaker/reset \
     -H "Content-Type: application/json" \
     -d '{"model_type": "gpt_4_mini"}'

# Monitor health
curl /api/v1/ai/health
```

### Database Maintenance
```bash
# Run migrations
alembic upgrade head

# Backup database
pg_dump $DATABASE_URL > backup.sql

# Clean old conversation logs (optional)
# Implement data retention policies
```

### Model Updates
1. Download new model files
2. Update `GEMMA_4_MODEL_PATH`
3. Restart application
4. Monitor health checks

## 🐛 Troubleshooting

### Common Issues

#### AI Models Not Loading
```bash
# Check model path
ls -la $GEMMA_4_MODEL_PATH

# Check API keys
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models

# Check logs
tail -f /var/log/lyoapp/app.log
```

#### High Response Times
```bash
# Check performance stats
curl /api/v1/ai/performance/stats

# Monitor circuit breakers
curl /api/v1/ai/health

# Check resource usage
htop
```

#### Cost Overruns
```bash
# Check daily spend
curl /api/v1/ai/performance/stats | jq '.daily_cost'

# Reduce cost limit
# Update AI_DAILY_COST_LIMIT in .env

# Switch to on-device models
# Set preferred model in orchestrator
```

### Support
- **Logs**: Check application logs for detailed error information
- **Metrics**: Use Prometheus metrics for performance insights
- **Health**: Monitor health endpoints for system status
- **Documentation**: API documentation available at `/docs`

## 📞 Production Checklist

### Pre-Deployment
- [ ] Environment variables configured
- [ ] Database migrations run
- [ ] API keys validated
- [ ] SSL certificates installed
- [ ] Firewall rules configured
- [ ] Monitoring setup

### Post-Deployment
- [ ] Health checks passing
- [ ] AI models loading correctly
- [ ] Performance metrics collected
- [ ] Error tracking configured
- [ ] Backup procedures tested
- [ ] Load testing completed

### Security Review
- [ ] Authentication working
- [ ] Rate limiting active
- [ ] Input validation enabled
- [ ] Security headers configured
- [ ] CORS properly set
- [ ] Secrets encrypted

---

**LyoApp AI Backend v1.0.0**  
Production-ready with Gemma 4 integration and multi-language support.

For technical support or questions, refer to the API documentation at `/docs` or contact the development team.
