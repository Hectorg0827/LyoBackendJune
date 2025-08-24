# 🚀 Google Cloud Run Deployment Guide

This directory contains everything needed to automatically deploy your LyoBackend to Google Cloud Run.

## 📦 What's Included

- **Dockerfile.production** - Optimized container for Cloud Run
- **cloud-run-config.yaml** - Cloud Run service configuration  
- **setup-gcp.sh** - One-time Google Cloud SDK setup
- **deploy-to-gcp.sh** - Automated deployment script
- **monitor_deployment.py** - Real-time monitoring
- **test_cloud_deployment.py** - Comprehensive testing suite

## 🎯 Quick Start (For Beginners)

### Step 1: One-Time Setup
```bash
# Make scripts executable
chmod +x setup-gcp.sh deploy-to-gcp.sh monitor_deployment.py test_cloud_deployment.py

# Install Google Cloud SDK and authenticate
./setup-gcp.sh
```

### Step 2: Deploy to Cloud Run
```bash
# Run automated deployment (this does everything!)
./deploy-to-gcp.sh
```

The script will:
- ✅ Build your Docker container
- ✅ Push to Google Container Registry
- ✅ Create PostgreSQL database
- ✅ Set up secrets and security
- ✅ Deploy to Cloud Run
- ✅ Configure scaling and monitoring

### Step 3: Test Your Deployment
```bash
# Test all endpoints (replace with your actual URL)
./test_cloud_deployment.py https://lyo-backend-abc123-uc.a.run.app
```

### Step 4: Monitor Your Service
```bash
# Real-time monitoring
./monitor_deployment.py lyo-backend us-central1
```

## 💰 Cost Estimate

- **Cloud Run**: $0 for low traffic (pay-per-request)
- **Cloud SQL** (db-f1-micro): ~$7-10/month
- **Redis Labs** (free tier): $0
- **Storage & Networking**: ~$1-2/month
- **Total**: ~$10-15/month for production backend

## 🔧 What Gets Created

### Google Cloud Resources
- Cloud Run service (your backend)
- Cloud SQL PostgreSQL instance
- Secret Manager secrets
- Service account with minimal permissions
- Container Registry repository

### Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET_KEY` - Authentication secret
- `REDIS_URL` - Optional caching layer
- `MODEL_ID` - AI model configuration
- `ENVIRONMENT=production`

### Security Features  
- Secrets stored in Secret Manager
- Service account with minimal permissions
- HTTPS by default
- Container security scanning
- VPC network isolation

## 🎛️ Advanced Usage

### Custom Configuration
Edit `cloud-run-config.yaml` to customize:
- CPU and memory limits
- Scaling parameters  
- Environment variables
- Health check settings

### Manual Deployment
```bash
# Build and push manually
export PROJECT_ID=your-project-id
export REGION=us-central1
export SERVICE_NAME=lyo-backend

# Build image
docker build -f Dockerfile.production -t gcr.io/$PROJECT_ID/$SERVICE_NAME .

# Push to registry
docker push gcr.io/$PROJECT_ID/$SERVICE_NAME

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated
```

### Monitoring and Logs
```bash
# View logs
gcloud run logs read --service=lyo-backend --region=us-central1

# Monitor metrics
gcloud run services describe lyo-backend --region=us-central1

# Set up alerts
gcloud alpha monitoring policies create --policy-from-file=monitoring-policy.yaml
```

## 🐛 Troubleshooting

### Common Issues

**Build Errors:**
```bash
# Check Docker is running
docker info

# Check gcloud authentication
gcloud auth list
```

**Deployment Failures:**
```bash
# Check service logs
gcloud run logs read --service=lyo-backend --region=us-central1 --limit=50

# Check service status
gcloud run services describe lyo-backend --region=us-central1
```

**Database Connection Issues:**
```bash
# Test database connectivity
gcloud sql connect lyo-backend-db --user=postgres

# Check Cloud SQL proxy
gcloud sql instances describe lyo-backend-db
```

### Health Checks

Your service includes built-in health monitoring:
- Startup probe: `/health` (checks if service is ready)
- Liveness probe: `/health` (checks if service is healthy)
- Custom monitoring: `monitor_deployment.py`

## 🔄 Updates and CI/CD

### Manual Updates
```bash
# Redeploy with new code
./deploy-to-gcp.sh
```

### Rollback
```bash
# List revisions
gcloud run revisions list --service=lyo-backend --region=us-central1

# Rollback to previous revision
gcloud run services update-traffic lyo-backend \
  --to-revisions=REVISION_NAME=100 \
  --region=us-central1
```

## 📱 Mobile App Integration

After deployment, update your mobile app to use:
```
Base URL: https://your-service-url.run.app
API Endpoints:
  - GET  /health
  - GET  /api/v1/test-ai  
  - POST /api/v1/generate-course
  - GET  /docs (API documentation)
```

## 🎉 Success!

Once deployed, your LyoBackend will be:
- ✅ **Live** on Google Cloud Run
- ✅ **Scalable** (0 to thousands of users)  
- ✅ **Secure** (HTTPS, secrets, IAM)
- ✅ **Monitored** (health checks, logging)
- ✅ **Cost-effective** (pay only for usage)

Your backend is now ready for production use! 🚀

## 📞 Need Help?

- Check the deployment logs: `./monitor_deployment.py`
- Test all endpoints: `./test_cloud_deployment.py`
- View Cloud Console: https://console.cloud.google.com/run
- Google Cloud Run docs: https://cloud.google.com/run/docs
