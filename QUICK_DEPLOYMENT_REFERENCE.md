# 🚀 LyoBackend Quick Deployment Reference

## Prerequisites Checklist

- [ ] Google Cloud SDK installed (`gcloud --version`)
- [ ] Docker installed (`docker --version`)
- [ ] Project billing enabled
- [ ] Domain ready (optional)

## 🔑 API Keys Required

### 1. OpenAI API Key
1. Visit: https://platform.openai.com/api-keys
2. Create account / Sign in
3. Click "Create new secret key"
4. Copy key starting with `sk-`
5. **Save securely** - you can't view it again!

### 2. Google Gemini API Key  
1. Visit: https://aistudio.google.com/app/apikey
2. Create project or select existing
3. Click "Create API Key"
4. Copy key starting with `AIza`

### 3. YouTube API Key (Optional)
1. Visit: https://console.developers.google.com/
2. Create project / Select project
3. Enable YouTube Data API v3
4. Create credentials > API key
5. Restrict key to YouTube Data API v3

## 🚀 One-Command Setup

```bash
# Replace with your project ID
export PROJECT_ID="your-lyo-project-id"

# Run setup (creates everything)
./setup_gcp.sh $PROJECT_ID

# Deploy application  
./deploy_cloudrun.sh $PROJECT_ID

# Test deployment
./test_deployment.sh
```

## 📋 Step-by-Step Commands

### 1. Initial Setup
```bash
# Set project variables
export PROJECT_ID="your-project-id"
export REGION="us-central1"

# Run GCP setup
./setup_gcp.sh $PROJECT_ID
```

### 2. Store API Keys
The setup script will prompt you for:
- OpenAI API key
- Gemini API key  
- YouTube API key (optional)

Or store manually:
```bash
# Store API keys in Secret Manager
echo -n "your-openai-key" | gcloud secrets create openai-api-key --data-file=-
echo -n "your-gemini-key" | gcloud secrets create gemini-api-key --data-file=-
```

### 3. Deploy Application
```bash
./deploy_cloudrun.sh $PROJECT_ID
```

### 4. Test Deployment
```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe lyo-backend --platform managed --region us-central1 --format "value(status.url)")

# Run tests
./test_deployment.sh $SERVICE_URL
```

## 🔧 Manual Setup Commands

<details>
<summary>Click to expand manual setup commands</summary>

```bash
# Enable APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com vertexai.googleapis.com

# Create service account
gcloud iam service-accounts create lyo-backend-sa --display-name="LyoBackend Service Account"

# Grant permissions
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:lyo-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com" --role="roles/aiplatform.user"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:lyo-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"

# Create database
gcloud sql instances create lyo-postgres --database-version=POSTGRES_15 --tier=db-g1-small --region=$REGION
gcloud sql databases create lyo_db --instance=lyo-postgres
gcloud sql users create lyo_user --instance=lyo-postgres --password="secure-password"
```

</details>

## 🌐 Your Deployed Endpoints

After successful deployment, your API will be available at:

- **API Documentation**: `https://SERVICE-URL/docs`
- **Health Check**: `https://SERVICE-URL/health`
- **Authentication**: `https://SERVICE-URL/api/v1/auth/`
- **AI Chat**: `https://SERVICE-URL/api/v1/ai/chat`
- **Study Mode**: `https://SERVICE-URL/api/v1/ai/study`
- **User Management**: `https://SERVICE-URL/api/v1/users/`
- **Content**: `https://SERVICE-URL/api/v1/content/`

## 🐛 Troubleshooting

### Common Issues

**"Permission denied"**
```bash
# Check service account permissions
gcloud iam service-accounts get-iam-policy lyo-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com
```

**"Secret not found"**
```bash
# List secrets
gcloud secrets list

# Create missing secret
echo -n "your-key" | gcloud secrets create secret-name --data-file=-
```

**"Database connection failed"**
```bash
# Check Cloud SQL instance
gcloud sql instances list

# Test connection
gcloud sql connect lyo-postgres --user=lyo_user
```

### Debugging Commands

```bash
# View service logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=lyo-backend" --limit=50

# Service details
gcloud run services describe lyo-backend --region=us-central1

# Test endpoints
curl -v https://your-service-url/health
```

## 📊 Monitoring

### View Metrics
```bash
# Open Cloud Console
open "https://console.cloud.google.com/run/detail/us-central1/lyo-backend/metrics?project=${PROJECT_ID}"

# Stream logs
gcloud logging read "resource.type=cloud_run_revision" --follow
```

### Performance Monitoring
- **CPU Usage**: Monitor in Cloud Console
- **Memory Usage**: Check for out-of-memory errors
- **Request Latency**: Aim for <1000ms
- **Error Rate**: Should be <1%

## 🔄 Updates & Maintenance

### Deploy Updates
```bash
# Deploy new version
./deploy_cloudrun.sh $PROJECT_ID

# Zero-downtime deployment
gcloud run deploy lyo-backend --source . --region us-central1 --no-traffic --tag candidate
gcloud run services update-traffic lyo-backend --to-tags candidate=100 --region us-central1
```

### Database Maintenance
```bash
# Backup database
gcloud sql backups create --instance=lyo-postgres --description="Pre-update backup"

# View backups
gcloud sql backups list --instance=lyo-postgres
```

## 💰 Cost Optimization

### Development
- `--min-instances 0` (scales to zero)
- `--memory 512Mi` (smaller memory)
- `--cpu 1` (single CPU)

### Production
- `--min-instances 1` (avoid cold starts)
- `--memory 1Gi` (better performance)
- `--max-instances 10` (handle traffic spikes)

## ✅ Success Checklist

- [ ] Project created and configured
- [ ] APIs enabled
- [ ] Service account created
- [ ] Database running
- [ ] Secrets stored
- [ ] Application deployed
- [ ] Health check passing
- [ ] API documentation accessible
- [ ] Authentication working
- [ ] AI endpoints responding
- [ ] Monitoring enabled
- [ ] Custom domain configured (optional)

## 📞 Support Resources

- **Google Cloud Run Docs**: https://cloud.google.com/run/docs
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **OpenAI API Docs**: https://platform.openai.com/docs
- **Google AI Studio**: https://aistudio.google.com/

---

**🎉 Congratulations!** Your LyoBackend is now running on Google Cloud Run with enterprise-grade infrastructure, AI integrations, and production-ready monitoring!
