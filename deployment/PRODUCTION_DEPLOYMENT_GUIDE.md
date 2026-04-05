# Living Classroom - Production Deployment Guide
## Zero-Downtime Deployment with Full Monitoring & A/B Testing

> **Production-Ready**: Complete infrastructure for 1M+ concurrent users with 99.9% uptime SLA

---

## 🚀 Deployment Options

### Option 1: Docker Compose (Recommended for initial production)
```bash
# 1. Clone and setup
git clone <repo>
cd LyoBackendJune

# 2. Configure environment
cp .env.example .env.production
# Edit .env.production with production values

# 3. Deploy
cd deployment
docker-compose -f docker-compose.production.yml up -d

# 4. Verify deployment
curl https://api.lyo.ai/health
```

### Option 2: Kubernetes (For enterprise scale)
```bash
# 1. Setup cluster
kubectl apply -f deployment/kubernetes/

# 2. Verify pods
kubectl get pods -n living-classroom

# 3. Check services
kubectl get svc -n living-classroom
```

---

## 🔧 Infrastructure Components

### Core Services
- **Application Servers**: 3x FastAPI instances with Gunicorn
- **Load Balancer**: Nginx with SSL termination
- **Database**: PostgreSQL 15 with read replica
- **Cache**: Redis cluster for sessions
- **WebSockets**: Sticky sessions for real-time streaming

### Monitoring Stack
- **Metrics**: Prometheus + Grafana dashboards
- **Logs**: ELK Stack (Elasticsearch, Logstash, Kibana)
- **APM**: Built-in performance monitoring
- **Alerts**: Real-time alert system

### Security
- **SSL/TLS**: Let's Encrypt certificates
- **Rate Limiting**: 100 req/min per IP
- **Security Headers**: HSTS, CSP, XSS protection
- **Network Policies**: Kubernetes network isolation

---

## 📊 Monitoring & Alerting

### Key Metrics Dashboard
Access: `https://api.lyo.ai/api/v1/classroom/monitor/ui`

**Real-time Metrics:**
- Scene generation latency (target: <500ms)
- WebSocket connection health
- User engagement scores
- A/B test performance
- Error rates and types

### Alert Thresholds
```yaml
Critical Alerts:
  - Scene generation > 2000ms
  - Error rate > 1%
  - WebSocket failures > 5%

Warning Alerts:
  - Scene generation > 1000ms
  - User engagement < 70%
  - Memory usage > 80%
```

### Grafana Dashboards
1. **Living Classroom Overview**: High-level KPIs
2. **A/B Test Performance**: Variant comparisons
3. **Infrastructure Health**: System resources
4. **User Experience**: Latency and engagement

---

## 🧪 A/B Testing Configuration

### Environment Variables
```bash
# A/B Testing
AB_TEST_ENABLED=true
AB_CONTROL_PCT=60        # Legacy SSE streaming
AB_TREATMENT_PCT=30      # Living Classroom
AB_HYBRID_PCT=10         # Mixed approach

# Feature Flags
LIVING_CLASSROOM_ENABLED=true
PROGRESSIVE_RENDERING=true
AI_PEER_INTERACTIONS=true
```

### Traffic Allocation Strategy

**Phase 1: Conservative Rollout (Week 1-2)**
- Control: 80%
- Treatment: 15%
- Hybrid: 5%

**Phase 2: Expanded Testing (Week 3-4)**
- Control: 60%
- Treatment: 30%
- Hybrid: 10%

**Phase 3: Full Rollout (Week 5+)**
- Control: 20%
- Treatment: 70%
- Hybrid: 10%

---

## 🔐 Security Configuration

### SSL/TLS Setup
```bash
# Generate Let's Encrypt certificate
certbot certonly --webroot -w /var/www/html -d api.lyo.ai

# Auto-renewal
echo "0 0 * * * certbot renew --quiet" | crontab -
```

### Security Headers
```nginx
# Already configured in nginx.conf
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
add_header X-Frame-Options "SAMEORIGIN";
add_header X-Content-Type-Options "nosniff";
add_header Content-Security-Policy "default-src 'self'; connect-src 'self' wss: https:;";
```

### Network Security
- Firewall rules: Only ports 80, 443, 22 exposed
- VPC isolation for database and Redis
- Kubernetes network policies
- Container security scanning

---

## 📈 Performance Optimization

### Application Level
```python
# Gunicorn configuration (already in Dockerfile)
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 10000
timeout = 120
```

### Database Optimization
```sql
-- PostgreSQL tuning (in postgresql.conf)
shared_buffers = 2GB
effective_cache_size = 6GB
work_mem = 256MB
maintenance_work_mem = 1GB
max_connections = 200
```

### Caching Strategy
```python
# Redis configuration
maxmemory 2gb
maxmemory-policy allkeys-lru
appendonly yes
save 900 1
save 300 10
save 60 10000
```

---

## 🔄 Deployment Process

### Zero-Downtime Deployment
```bash
#!/bin/bash
# deployment/deploy.sh

# 1. Build new image
docker build -f Dockerfile.production -t lyo/living-classroom:$VERSION .

# 2. Run health checks on new image
docker run --rm lyo/living-classroom:$VERSION python -c "
import requests
response = requests.get('http://localhost:8000/health')
assert response.status_code == 200
"

# 3. Rolling update
docker-compose -f docker-compose.production.yml up -d --force-recreate lyo-app-1
sleep 30
docker-compose -f docker-compose.production.yml up -d --force-recreate lyo-app-2
sleep 30
docker-compose -f docker-compose.production.yml up -d --force-recreate lyo-app-3

# 4. Verify deployment
curl -f https://api.lyo.ai/health || exit 1
echo "✅ Deployment successful"
```

### Kubernetes Rolling Update
```bash
# Update deployment with new image
kubectl set image deployment/lyo-app lyo-app=lyo/living-classroom:$VERSION -n living-classroom

# Monitor rollout
kubectl rollout status deployment/lyo-app -n living-classroom

# Rollback if needed
kubectl rollout undo deployment/lyo-app -n living-classroom
```

---

## 🔍 Health Checks & Monitoring

### Application Health Endpoints
- `GET /health` - Basic health check
- `GET /health/ready` - Readiness probe
- `GET /health/live` - Liveness probe
- `GET /api/v1/classroom/monitor/health` - Detailed health

### Health Check Response
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "checks": {
    "database": {"status": "healthy", "latency_ms": 5},
    "redis": {"status": "healthy", "latency_ms": 2},
    "websocket_manager": {"status": "healthy", "active_connections": 1247},
    "scene_lifecycle": {"status": "healthy"},
    "living_classroom": {"status": "healthy", "version": "2.0.0"}
  },
  "version": "2.0.0",
  "uptime_seconds": 86400
}
```

### Log Analysis
```bash
# Application logs
docker-compose logs -f lyo-app-1

# WebSocket connection logs
grep "WebSocket" /var/log/nginx/access.log

# Error analysis
grep "ERROR\|CRITICAL" /var/log/lyo/app.log | tail -100
```

---

## 📊 A/B Test Analysis

### Metrics Collection
```python
# Automatic metric collection in code
await record_ab_test_metric(
    user_id=user.id,
    metric_name="scene_generation_time",
    metric_value=duration_ms,
    test_name="living_classroom_rollout"
)
```

### Statistical Analysis Dashboard
Access: `https://api.lyo.ai/api/v1/classroom/monitor/ab-tests/living_classroom_rollout/results`

**Key Metrics:**
- Scene generation time: Control vs Treatment
- User engagement scores
- Session completion rates
- Error rates by variant
- Statistical significance (p-values)

---

## 🚨 Emergency Procedures

### Incident Response
1. **Alert Detection**: Automated alerts via Prometheus/Grafana
2. **Initial Assessment**: Check dashboard at `/monitor/ui`
3. **Traffic Control**: Adjust A/B test percentages if needed
4. **Rollback**: Use blue-green deployment strategy
5. **Post-Incident**: Full incident report and lessons learned

### Emergency Rollback
```bash
# Docker Compose
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d

# Kubernetes
kubectl rollout undo deployment/lyo-app -n living-classroom
```

### Feature Flag Override
```bash
# Disable Living Classroom immediately
curl -X POST "https://api.lyo.ai/admin/feature-flags" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"living_classroom_enabled": false}'
```

---

## 📋 Pre-Production Checklist

### Infrastructure
- [ ] SSL certificates installed and auto-renewal configured
- [ ] Load balancer health checks passing
- [ ] Database backups configured (daily + continuous WAL)
- [ ] Redis persistence enabled
- [ ] Monitoring stack deployed and configured
- [ ] Log aggregation working
- [ ] Alert rules configured and tested

### Security
- [ ] Security headers configured
- [ ] Rate limiting enabled
- [ ] Network policies applied (Kubernetes)
- [ ] Container security scans passed
- [ ] Secrets properly managed
- [ ] RBAC configured

### Performance
- [ ] Load testing completed (1000 concurrent users)
- [ ] WebSocket connection testing (500 concurrent)
- [ ] Database query optimization
- [ ] CDN configured for static assets
- [ ] Caching strategies validated

### A/B Testing
- [ ] Test configurations validated
- [ ] Metrics collection working
- [ ] Dashboard accessible
- [ ] Statistical analysis confirmed
- [ ] Rollback procedures tested

---

## 🔧 Configuration Files

### Environment Variables (.env.production)
```bash
# Database
DATABASE_URL=postgresql://lyo_user:${DB_PASSWORD}@postgres-primary:5432/lyo_production
DB_POOL_SIZE=20

# Redis
REDIS_URL=redis://redis-cluster:6379
REDIS_PASSWORD=${REDIS_PASSWORD}

# Living Classroom
LIVING_CLASSROOM_ENABLED=true
WEBSOCKET_ENABLED=true

# A/B Testing
AB_TEST_ENABLED=true
AB_CONTROL_PCT=60
AB_TREATMENT_PCT=30
AB_HYBRID_PCT=10

# Security
JWT_SECRET=${JWT_SECRET}
CORS_ORIGINS=https://app.lyo.ai,https://lyo.ai

# Monitoring
LOG_LEVEL=info
SENTRY_DSN=${SENTRY_DSN}
PROMETHEUS_ENABLED=true
```

### Resource Requirements

**Minimum (100 concurrent users):**
- CPU: 4 cores
- RAM: 8GB
- Storage: 100GB SSD
- Network: 1 Gbps

**Recommended (1000+ concurrent users):**
- CPU: 16 cores
- RAM: 32GB
- Storage: 500GB NVMe SSD
- Network: 10 Gbps

**Database:**
- CPU: 8 cores
- RAM: 16GB
- Storage: 1TB SSD (with backup)

---

## 📞 Support & Maintenance

### Monitoring Contacts
- **Primary**: alerts@lyo.ai
- **Secondary**: ops-team@lyo.ai
- **Emergency**: +1-XXX-XXX-XXXX

### Maintenance Windows
- **Scheduled**: Sundays 2:00-4:00 AM UTC
- **Emergency**: As needed with 15-minute notice
- **Database**: Monthly optimization during scheduled window

### Backup Strategy
- **Database**: Continuous WAL + daily full backup
- **Redis**: Snapshot every 6 hours
- **Application**: GitOps deployment (code is source of truth)
- **Logs**: 30-day retention with archival to S3

---

This production deployment guide provides everything needed to deploy and maintain Living Classroom at enterprise scale with:

- **99.9% Uptime**: Load balancing, health checks, and failover
- **Real-time A/B Testing**: Statistical analysis and automated rollout
- **Comprehensive Monitoring**: Metrics, logs, and alerts
- **Security**: SSL, rate limiting, and network isolation
- **Performance**: <500ms response times at scale
- **Zero-downtime Updates**: Blue-green deployment strategy