# 🚀 LyoBackend Google Cloud Quick Start

Deploy your LyoBackend to Google Cloud Run in minutes with our streamlined deployment scripts.

## ⚡ One-Click Deployment

The fastest way to get your LyoBackend running on Google Cloud:

```bash
./one-click-gcp-deploy.sh
```

That's it! The script will handle everything automatically:
- ✅ Install Google Cloud SDK (if needed)
- ✅ Set up your GCP project and enable APIs
- ✅ Build and push Docker images
- ✅ Configure secrets and service accounts
- ✅ Deploy to Cloud Run
- ✅ Run health checks

## 📋 Prerequisites

- **Docker** installed and running
- **Google Cloud Project** (create one at [console.cloud.google.com](https://console.cloud.google.com))
- **Billing enabled** on your GCP project (required for Cloud Run)

## 🎯 Deployment Options

### Option 1: Interactive Deployment
```bash
./one-click-gcp-deploy.sh
```
The script will prompt you for:
- GCP Project ID
- Region (default: us-central1)
- Service Name (default: lyo-backend)

### Option 2: Command Line Arguments
```bash
./one-click-gcp-deploy.sh YOUR_PROJECT_ID us-central1 lyo-backend
```

### Option 3: Environment Variables
```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export SERVICE_NAME="lyo-backend"
export SKIP_CONFIRM="true"
./one-click-gcp-deploy.sh
```

## 🧪 Pre-Deployment Testing

Test your setup before deploying:

```bash
./test-gcp-deployment.sh
```

This validates:
- Docker installation
- Application files
- Dockerfile syntax
- Dependencies
- Python app structure

## 📊 What Gets Deployed

Your deployment includes:

### **Infrastructure**
- **Cloud Run Service**: Managed container hosting
- **Artifact Registry**: Docker image storage
- **Secret Manager**: Secure credential storage
- **Service Account**: Proper IAM permissions

### **Application Features**
- **FastAPI Backend**: High-performance async API
- **Health Checks**: `/health` endpoint for monitoring
- **Auto Scaling**: 0-100 instances based on demand
- **HTTPS**: Automatic SSL certificates
- **CORS**: Configured for web/mobile apps

### **Security**
- **Secrets Management**: JWT tokens, API keys
- **IAM Roles**: Least-privilege access
- **Non-root Container**: Enhanced security
- **Environment Isolation**: Production settings

## 🔗 After Deployment

Once deployed, you'll get:

```bash
🎉 LyoBackend successfully deployed to Google Cloud Run!

📋 Deployment Details:
Service URL: https://lyo-backend-xyz-abc123.a.run.app
API Docs: https://lyo-backend-xyz-abc123.a.run.app/docs
Health Check: https://lyo-backend-xyz-abc123.a.run.app/health

🔗 Quick Links:
🌐 Service URL: https://lyo-backend-xyz-abc123.a.run.app
📚 API Docs: https://lyo-backend-xyz-abc123.a.run.app/docs
❤️ Health Check: https://lyo-backend-xyz-abc123.a.run.app/health
📊 Cloud Console: https://console.cloud.google.com/run/detail/...
```

## 🛠️ Configuration Management

### Database Setup
By default, a placeholder database URL is created. For production:

1. **Create Cloud SQL PostgreSQL**:
   ```bash
   gcloud sql instances create lyo-db \
     --database-version=POSTGRES_14 \
     --tier=db-f1-micro \
     --region=us-central1
   ```

2. **Update Database Secret**:
   ```bash
   echo -n "postgresql://user:password@/dbname?host=/cloudsql/project:region:instance" | \
   gcloud secrets versions add database-url --data-file=-
   ```

3. **Redeploy Service**:
   ```bash
   gcloud run deploy lyo-backend --region=us-central1
   ```

### Environment Variables
Add custom environment variables:

```bash
gcloud run services update lyo-backend \
  --set-env-vars="CUSTOM_VAR=value" \
  --region=us-central1
```

### Secrets Management
Add new secrets:

```bash
# Create secret
echo -n "secret-value" | gcloud secrets create my-secret --data-file=-

# Add to Cloud Run service
gcloud run services update lyo-backend \
  --set-secrets="MY_SECRET=my-secret:latest" \
  --region=us-central1
```

## 📈 Monitoring & Logs

### View Logs
```bash
gcloud run logs read --service=lyo-backend --region=us-central1
```

### Real-time Logs
```bash
gcloud run logs tail --service=lyo-backend --region=us-central1
```

### Metrics & Monitoring
Visit the Cloud Run console:
```bash
https://console.cloud.google.com/run
```

## 🔄 Updates & Maintenance

### Update Application
```bash
# Rebuild and push new image
docker build -f Dockerfile.production -t your-image-url .
docker push your-image-url

# Deploy update
gcloud run deploy lyo-backend --image=your-image-url --region=us-central1
```

### Scale Configuration
```bash
gcloud run services update lyo-backend \
  --max-instances=50 \
  --min-instances=1 \
  --memory=4Gi \
  --cpu=2 \
  --region=us-central1
```

## 🚨 Troubleshooting

### Common Issues

**1. Docker Build Fails**
```bash
# Check Docker is running
docker info

# Clean build cache
docker system prune -f
```

**2. Authentication Issues**
```bash
# Re-authenticate
gcloud auth login
gcloud auth configure-docker
```

**3. Permission Denied**
```bash
# Check project permissions
gcloud projects get-iam-policy YOUR_PROJECT_ID
```

**4. Service Not Starting**
```bash
# Check logs for errors
gcloud run logs read --service=lyo-backend --region=us-central1
```

### Health Check
Always test your deployment:
```bash
curl https://your-service-url.run.app/health
```

## 📚 Additional Resources

### Original Deployment Scripts
- `./deploy-to-gcp.sh` - Interactive deployment with more options
- `./setup-gcp.sh` - Google Cloud SDK setup only
- `./test_deployment.sh` - Comprehensive deployment testing

### Documentation
- `COMPLETE_DEPLOYMENT_GUIDE.md` - Comprehensive deployment guide
- `PRODUCTION_DEPLOYMENT_GUIDE.md` - Production-specific guidance
- `README.md` - Project overview

## 🆘 Support

If you encounter issues:

1. **Check logs**: `gcloud run logs read --service=lyo-backend`
2. **Test health**: `curl https://your-service-url.run.app/health`
3. **Validate setup**: `./test-gcp-deployment.sh`
4. **Review documentation**: See guides in the repository

---

**🚀 Ready to deploy? Run:**

```bash
./one-click-gcp-deploy.sh
```

**Happy deploying! 🎉**