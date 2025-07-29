# 🚀 Complete Production Deployment Guide
# LyoBackendJune - From Development to Production

## 📋 **Pre-Deployment Checklist**

### **1. Environment Preparation**
- [ ] **Domain Setup**: Purchase and configure your domain (e.g., `api.lyobackend.com`)
- [ ] **SSL Certificate**: Ready for Let's Encrypt or purchased certificate
- [ ] **Cloud Account**: AWS/GCP/Azure account with billing configured
- [ ] **Email Service**: SMTP service for notifications (SendGrid, Amazon SES, etc.)
- [ ] **API Keys**: Collect all required API keys:
  - [ ] YouTube Data API v3
  - [ ] OpenAI API key
  - [ ] Anthropic API key (optional)
  - [ ] Google Gemini API key (optional)
  - [ ] Sentry DSN (for error tracking)

### **2. Repository Setup**
- [ ] **GitHub Repository**: Create and configure repository
- [ ] **Secrets Configuration**: Add GitHub secrets for CI/CD
- [ ] **Branch Protection**: Set up branch protection rules
- [ ] **Environment Configuration**: Configure staging and production environments

---

## 🎯 **Deployment Options**

### **Option 1: Docker Compose (Recommended for Getting Started)**

#### **Step 1: Server Setup**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Logout and login again for group changes
```

#### **Step 2: Deploy Application**
```bash
# Clone repository
git clone https://github.com/yourusername/LyoBackendJune.git
cd LyoBackendJune

# Configure environment
cp .env.production.example .env.production
# Edit .env.production with your actual values

# Set up SSL (replace with your domain)
./docker/ssl/setup-ssl.sh your-domain.com admin@your-domain.com

# Deploy with SSL
./deploy_enhanced.sh

# Validate deployment
python production_validation_final.py
```

#### **Step 3: Set Up Monitoring**
```bash
# Access monitoring dashboards
echo "Grafana: http://your-domain.com:3000 (admin/admin)"
echo "Prometheus: http://your-domain.com:9090"

# Set up cron for SSL renewal
./docker/ssl/setup-cron.sh
```

---

### **Option 2: AWS Cloud Deployment (Enterprise-Ready)**

#### **Step 1: AWS Prerequisites**
```bash
# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Install Terraform
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/

# Configure AWS credentials
aws configure
```

#### **Step 2: Deploy Infrastructure**
```bash
# Deploy AWS infrastructure
cd infrastructure/aws
./deploy-aws.sh production us-east-1 your-secure-db-password

# This will create:
# - VPC with public/private subnets
# - RDS PostgreSQL database
# - ElastiCache Redis cluster
# - ECS Fargate cluster
# - Application Load Balancer
# - S3 bucket for file storage
# - ECR repository for Docker images
```

#### **Step 3: Configure CI/CD**
1. **Add GitHub Secrets**:
   ```
   AWS_ACCESS_KEY_ID: your-aws-access-key
   AWS_SECRET_ACCESS_KEY: your-aws-secret-key
   AWS_REGION: us-east-1
   ECS_CLUSTER_NAME_PRODUCTION: lyobackend-cluster
   ECS_SERVICE_NAME_PRODUCTION: lyobackend-app-service
   PRODUCTION_URL: http://your-alb-dns-name
   SLACK_WEBHOOK_URL: your-slack-webhook (optional)
   ```

2. **Push to main branch** - CI/CD will automatically deploy

---

### **Option 3: Kubernetes (Advanced)**

#### **Step 1: Kubernetes Setup**
```bash
# For managed Kubernetes (EKS, GKE, AKS)
# Follow your cloud provider's setup guide

# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

#### **Step 2: Deploy with Helm** (If you create Helm charts)
```bash
# Create namespace
kubectl create namespace lyobackend

# Deploy
helm install lyobackend ./k8s/helm-chart -n lyobackend

# Monitor deployment
kubectl get pods -n lyobackend
```

---

## 🔧 **Configuration Management**

### **Environment Variables Setup**

#### **Required Variables**
```bash
# Database Configuration
DATABASE_URL=postgresql://user:password@host:5432/database
REDIS_URL=redis://host:6379

# Security
SECRET_KEY=your-super-secure-secret-key
JWT_SECRET_KEY=your-jwt-secret

# API Keys
YOUTUBE_API_KEY=your-youtube-api-key
OPENAI_API_KEY=your-openai-api-key

# Email Configuration
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=your-sendgrid-api-key

# Storage
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_S3_BUCKET=your-s3-bucket
AWS_REGION=us-east-1

# Monitoring
SENTRY_DSN=your-sentry-dsn
```

#### **Production Optimizations**
```bash
# Performance
WORKERS=4
MAX_REQUESTS=1000
MAX_REQUESTS_JITTER=100
TIMEOUT=30

# Database
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=30
DB_POOL_TIMEOUT=30

# Redis
REDIS_MAX_CONNECTIONS=100
REDIS_SOCKET_TIMEOUT=5

# Cache
CACHE_DEFAULT_TIMEOUT=300
CACHE_THRESHOLD=500
```

---

## 🔒 **Security Configuration**

### **1. SSL/TLS Setup**
```bash
# Using Let's Encrypt (automated)
./docker/ssl/setup-ssl.sh your-domain.com admin@your-domain.com

# Using custom certificate
# Place your certificate files in:
# - docker/ssl/certs/your-domain.com/fullchain.pem
# - docker/ssl/certs/your-domain.com/privkey.pem
```

### **2. Firewall Configuration**
```bash
# UFW (Ubuntu)
sudo ufw enable
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw deny 8000/tcp  # Block direct API access

# AWS Security Groups
# Configure in AWS Console or Terraform
```

### **3. Database Security**
```bash
# PostgreSQL security
# - Enable SSL connections
# - Use strong passwords
# - Restrict host access
# - Regular backups with encryption
```

---

## 📊 **Monitoring & Alerting**

### **1. Health Monitoring**
```bash
# Application health check
curl https://your-domain.com/health

# Database health
curl https://your-domain.com/api/health/database

# Detailed system status
curl https://your-domain.com/api/health/detailed
```

### **2. Log Management**
```bash
# View application logs
docker-compose -f docker-compose.production.yml logs -f lyo-api-1

# View nginx logs
docker-compose -f docker-compose.production.yml logs -f nginx

# View PostgreSQL logs
docker-compose -f docker-compose.production.yml logs -f postgres
```

### **3. Metrics Dashboard**
- **Grafana**: `https://your-domain.com:3000`
  - Default login: admin/admin
  - Pre-configured dashboards for API metrics
  - Database performance monitoring
  - System resource tracking

- **Prometheus**: `https://your-domain.com:9090`
  - Raw metrics data
  - Custom query interface
  - Alert rules configuration

---

## 🚀 **Performance Optimization**

### **1. Database Optimization**
```sql
-- Create indexes for better performance
CREATE INDEX CONCURRENTLY idx_learning_resources_category_type 
ON learning_resources(category, resource_type);

CREATE INDEX CONCURRENTLY idx_user_progress_user_id_updated 
ON user_progress(user_id, updated_at DESC);

-- Analyze tables for query optimization
ANALYZE learning_resources;
ANALYZE user_progress;
ANALYZE users;
```

### **2. Redis Configuration**
```bash
# Optimize Redis for production
# Add to redis.conf:
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

### **3. Application Tuning**
```python
# Gunicorn production settings
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
keepalive = 2
```

---

## 🔄 **Backup Strategy**

### **1. Database Backups**
```bash
# Automated daily backups
cat > /etc/cron.d/lyobackend-backup << 'EOF'
0 2 * * * root docker exec postgres pg_dump -U lyouser lyobackend | gzip > /backup/db-$(date +\%Y\%m\%d).sql.gz
EOF

# Backup retention (keep 30 days)
find /backup -name "db-*.sql.gz" -mtime +30 -delete
```

### **2. File Storage Backups**
```bash
# S3 versioning (already enabled in Terraform)
# Configure lifecycle policies for cost optimization

# Local file backup (if using local storage)
rsync -av uploads/ /backup/uploads/
```

---

## 📈 **Scaling Strategy**

### **1. Horizontal Scaling**
```bash
# Docker Compose: Add more API instances
# Edit docker-compose.production.yml:
# Add lyo-api-3, lyo-api-4, etc.

# AWS ECS: Auto Scaling (already configured)
# Will automatically scale 2-10 instances based on CPU/Memory

# Kubernetes: Horizontal Pod Autoscaler
kubectl autoscale deployment lyobackend-api --cpu-percent=70 --min=2 --max=10
```

### **2. Database Scaling**
```bash
# Read Replicas (AWS RDS)
aws rds create-db-instance-read-replica \
  --db-instance-identifier lyobackend-read-replica \
  --source-db-instance-identifier lyobackend-db

# Connection Pooling (PgBouncer)
# Already configured in docker-compose.production.yml
```

---

## 🆘 **Troubleshooting Guide**

### **Common Issues & Solutions**

#### **1. Application Won't Start**
```bash
# Check logs
docker-compose -f docker-compose.production.yml logs lyo-api-1

# Common causes:
# - Database connection issues
# - Missing environment variables
# - Port conflicts
# - SSL certificate problems
```

#### **2. Database Connection Failed**
```bash
# Test database connectivity
docker exec -it postgres psql -U lyouser -d lyobackend

# Check environment variables
docker-compose -f docker-compose.production.yml exec lyo-api-1 env | grep DATABASE

# Verify database is running
docker-compose -f docker-compose.production.yml ps postgres
```

#### **3. SSL Certificate Issues**
```bash
# Check certificate validity
openssl x509 -in docker/ssl/certs/your-domain.com/fullchain.pem -text -noout

# Renew certificate manually
./docker/ssl/renew-ssl.sh

# Check nginx configuration
docker-compose -f docker-compose.production.yml exec nginx nginx -t
```

#### **4. Performance Issues**
```bash
# Check resource usage
docker stats

# Monitor database performance
docker exec -it postgres psql -U lyouser -d lyobackend -c "
SELECT query, calls, total_time, mean_time 
FROM pg_stat_statements 
ORDER BY total_time DESC 
LIMIT 10;"

# Check Redis performance
docker exec -it redis redis-cli INFO stats
```

---

## 📞 **Support & Maintenance**

### **Regular Maintenance Tasks**

#### **Daily**
- [ ] Check application health endpoints
- [ ] Monitor error rates in Sentry
- [ ] Review application logs for issues

#### **Weekly**
- [ ] Review database performance metrics
- [ ] Check disk space usage
- [ ] Verify backup integrity
- [ ] Update security patches

#### **Monthly**
- [ ] Renew SSL certificates (automated)
- [ ] Review and optimize database queries
- [ ] Update dependencies
- [ ] Performance testing
- [ ] Security vulnerability scanning

### **Emergency Contacts**
```bash
# Application health
curl https://your-domain.com/health

# Database status
curl https://your-domain.com/api/health/database

# System metrics
curl https://your-domain.com/metrics

# Quick restart (if needed)
docker-compose -f docker-compose.production.yml restart
```

---

## 🎉 **Deployment Success!**

### **Verify Your Deployment**
1. **Application**: `https://your-domain.com/health` → Should return `{"status": "healthy"}`
2. **API Docs**: `https://your-domain.com/docs` → Interactive API documentation
3. **Admin Panel**: `https://your-domain.com/admin` → Administrative interface
4. **Monitoring**: `https://your-domain.com:3000` → Grafana dashboards

### **Next Steps**
1. **Mobile App Integration**: Configure your iOS app to use your production API
2. **User Testing**: Invite beta users to test the platform
3. **Analytics**: Set up user analytics and usage tracking
4. **Marketing**: Launch your educational platform to the world!

---

**🎯 Congratulations! Your LyoBackendJune is now 100% production-ready and deployed!**

Your educational content aggregation platform is now running with:
- ✅ Enterprise-grade security and monitoring
- ✅ Auto-scaling infrastructure
- ✅ AI-powered educational features
- ✅ Real-time communication
- ✅ Comprehensive backup and recovery
- ✅ Professional CI/CD pipeline

**Your backend is ready to power the future of education! 🚀**
