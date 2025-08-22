# Complete LyoBackend Deployment Guide to Google Cloud Run

This guide will walk you through deploying your Python FastAPI LyoBackend application to Google Cloud Run with all necessary API integrations and backend storage.

## Part 1: Prerequisites and Setup

### 1.1 Install Required Tools

First, ensure you have the necessary tools installed:

```bash
# Install Google Cloud SDK
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init

# Install Docker
# Visit https://docs.docker.com/get-docker/ for your OS

# Verify installations
gcloud --version
docker --version
```

### 1.2 Set Your Project Variables

```bash
# Set your project details (replace with your values)
export PROJECT_ID="your-lyo-project-id"
export REGION="us-central1"
export SERVICE_NAME="lyo-backend"
export SERVICE_ACCOUNT_NAME="lyo-backend-sa"
```

## Part 2: Google Cloud Project Setup

### 2.1 Create and Configure Your Project

```bash
# Create a new project (if you don't have one)
gcloud projects create $PROJECT_ID --name="LyoApp Backend"

# Set the project as active
gcloud config set project $PROJECT_ID

# Enable billing (required for Cloud Run)
# Go to https://console.cloud.google.com/billing and link billing account

# Enable required APIs
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    vertexai.googleapis.com
```

### 2.2 Create Service Account

```bash
# Create service account
gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
    --display-name="LyoBackend Service Account"

# Grant necessary permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client"
```

## Part 3: Database Setup (Cloud SQL PostgreSQL)

### 3.1 Create Cloud SQL Instance

```bash
# Create PostgreSQL instance
gcloud sql instances create lyo-postgres \
    --database-version=POSTGRES_15 \
    --tier=db-g1-small \
    --region=$REGION \
    --storage-type=SSD \
    --storage-size=20GB \
    --storage-auto-increase

# Set root password
gcloud sql users set-password root \
    --instance=lyo-postgres \
    --password="your-secure-database-password"

# Create application database
gcloud sql databases create lyo_db --instance=lyo-postgres

# Create application user
gcloud sql users create lyo_user \
    --instance=lyo-postgres \
    --password="your-secure-user-password"
```

### 3.2 Get Database Connection Details

```bash
# Get connection name
CONNECTION_NAME=$(gcloud sql instances describe lyo-postgres --format="value(connectionName)")
echo "Connection name: $CONNECTION_NAME"
```

## Part 4: API Keys Setup

### 4.1 OpenAI API Key

1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to API keys section
4. Create new secret key
5. Copy and save the key securely

### 4.2 Google AI (Gemini) API Key

```bash
# Enable Vertex AI API (already done above)
# For direct Gemini API, go to Google AI Studio
# Visit https://aistudio.google.com/app/apikey
# Create API key and copy it
```

### 4.3 Store API Keys in Secret Manager

```bash
# Store OpenAI API Key
echo -n "your-openai-api-key" | gcloud secrets create openai-api-key --data-file=-

# Store Gemini API Key
echo -n "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=-

# Store database password
echo -n "your-secure-database-password" | gcloud secrets create db-password --data-file=-

# Store secret key
echo -n "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" | gcloud secrets create secret-key --data-file=-
```

## Part 5: Prepare Your Application for Production

### 5.1 Update Environment Configuration

Create or update your `.env.production` file:

```bash
# Copy the example production environment file
cp .env.production.example .env.production
```

Edit `.env.production` with your actual values:

```env
# Application Settings
ENVIRONMENT=production
DEBUG=false

# Database (Cloud SQL)
DATABASE_URL=postgresql+asyncpg://lyo_user:your-secure-user-password@/lyo_db?host=/cloudsql/your-project:us-central1:lyo-postgres

# API Keys (will be overridden by secret manager)
OPENAI_API_KEY=will-be-set-by-secrets
GEMINI_API_KEY=will-be-set-by-secrets
SECRET_KEY=will-be-set-by-secrets

# Other production settings...
CORS_ORIGINS=["https://your-frontend-domain.com"]
```

### 5.2 Update Dockerfile for Production

Your existing `Dockerfile` is already production-ready! It includes:
- Multi-stage build for smaller image
- Non-root user for security
- Health checks
- Dynamic port configuration
- Proper Python optimizations

### 5.3 Create Cloud Run Deployment Script

Update your existing `deploy_cloudrun.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Enhanced deployment script for LyoBackend
PROJECT_ID=${1:-${PROJECT_ID:-}}
REGION=${REGION:-us-central1}
SERVICE=${SERVICE:-lyo-backend}
SERVICE_ACCOUNT=${SERVICE_ACCOUNT:-${SERVICE}-sa@${PROJECT_ID}.iam.gserviceaccount.com}

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID not set. Provide as env var or first argument." >&2
  exit 1
fi

echo "Deploying service '${SERVICE}' to project '${PROJECT_ID}' region '${REGION}'"

gcloud config set project "${PROJECT_ID}"

# Get database connection name
CONNECTION_NAME=$(gcloud sql instances describe lyo-postgres --format="value(connectionName)" 2>/dev/null || echo "")

echo "Building and deploying to Cloud Run..."

gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --platform managed \
  --port 8080 \
  --allow-unauthenticated \
  --cpu 1 \
  --memory 1Gi \
  --concurrency 80 \
  --timeout 600 \
  --min-instances 0 \
  --max-instances 10 \
  --service-account "${SERVICE_ACCOUNT}" \
  --add-cloudsql-instances "${CONNECTION_NAME}" \
  --set-env-vars "ENVIRONMENT=production" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars "PYTHONUNBUFFERED=1" \
  --set-secrets "OPENAI_API_KEY=openai-api-key:latest" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest" \
  --set-secrets "SECRET_KEY=secret-key:latest" \
  --set-secrets "DATABASE_PASSWORD=db-password:latest"

echo "✅ Deployment completed successfully!"
echo "🌐 Service URL: https://${SERVICE}-$(echo ${PROJECT_ID} | tr '_' '-')-${REGION}.run.app"
echo "📊 Console: https://console.cloud.google.com/run/detail/${REGION}/${SERVICE}/metrics?project=${PROJECT_ID}"
```

Make it executable:

```bash
chmod +x deploy_cloudrun.sh
```

## Part 6: Deploy Your Application

### 6.1 Build and Deploy

```bash
# Deploy using your script
./deploy_cloudrun.sh $PROJECT_ID

# Or deploy manually
gcloud run deploy lyo-backend \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --service-account lyo-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-secrets "OPENAI_API_KEY=openai-api-key:latest" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest"
```

### 6.2 Set Up Database Schema

After deployment, initialize your database:

```bash
# Get your service URL
SERVICE_URL=$(gcloud run services describe lyo-backend --platform managed --region us-central1 --format "value(status.url)")

# Run database migrations (if you have them)
curl -X POST "${SERVICE_URL}/admin/migrate" \
  -H "Content-Type: application/json"

# Or connect directly to run migrations
gcloud sql connect lyo-postgres --user=lyo_user --database=lyo_db
```

## Part 7: Configure Custom Domain (Optional)

### 7.1 Map Custom Domain

```bash
# Map your domain to Cloud Run
gcloud run domain-mappings create \
  --service lyo-backend \
  --domain api.yourdomain.com \
  --region us-central1
```

### 7.2 Update DNS

Add the required DNS records as shown in the Cloud Run console.

## Part 8: Monitoring and Logging

### 8.1 Enable Monitoring

Your application includes comprehensive monitoring with:
- Prometheus metrics
- Structured logging
- Health checks
- Error tracking (Sentry)

### 8.2 View Logs

```bash
# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=lyo-backend" \
  --limit 50 \
  --format "table(timestamp,textPayload)"

# Stream logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=lyo-backend" \
  --follow
```

## Part 9: Testing Your Deployment

### 9.1 Health Check

```bash
# Test health endpoint
curl https://your-service-url.run.app/health

# Test API documentation
curl https://your-service-url.run.app/docs
```

### 9.2 API Testing

```bash
# Test a protected endpoint
curl -X POST https://your-service-url.run.app/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "securepassword123",
    "full_name": "Test User"
  }'
```

## Part 10: Security Hardening

### 10.1 Enable IAP (Identity-Aware Proxy) - Optional

For additional security:

```bash
# Enable IAP for your Cloud Run service
gcloud iap web enable --resource-type=cloud-run \
  --oauth2-client-id=your-oauth-client-id \
  --oauth2-client-secret=your-oauth-client-secret
```

### 10.2 Set up VPC Connector (Advanced)

For private database access:

```bash
# Create VPC connector
gcloud compute networks vpc-access connectors create lyo-connector \
  --region us-central1 \
  --subnet default \
  --subnet-project $PROJECT_ID \
  --machine-type e2-micro \
  --min-instances 2 \
  --max-instances 3
```

## Part 11: Maintenance and Updates

### 11.1 Update Deployment

```bash
# Deploy updates
./deploy_cloudrun.sh $PROJECT_ID

# Or with zero downtime
gcloud run deploy lyo-backend \
  --source . \
  --region us-central1 \
  --no-traffic \
  --tag candidate

# Test the candidate version, then shift traffic
gcloud run services update-traffic lyo-backend \
  --to-tags candidate=100 \
  --region us-central1
```

### 11.2 Database Backups

```bash
# Create backup
gcloud sql backups create \
  --instance=lyo-postgres \
  --description="Pre-deployment backup"
```

## Part 12: Cost Optimization

### 12.1 Monitor Usage

```bash
# Check current usage
gcloud logging read "resource.type=cloud_run_revision" \
  --format="table(timestamp,resource.labels.service_name)" \
  --limit=10

# Monitor costs
gcloud billing budgets list
```

### 12.2 Optimize Resources

- Use `--min-instances 0` for development
- Use `--min-instances 1` for production
- Monitor and adjust `--cpu` and `--memory` based on usage
- Use `--concurrency 80` for Python FastAPI applications

## Troubleshooting

### Common Issues

1. **Cold starts**: Set `--min-instances 1` for production
2. **Memory issues**: Increase `--memory` to `1Gi` or `2Gi`
3. **Database connection**: Ensure Cloud SQL connector is properly configured
4. **Secret access**: Verify service account has Secret Manager access

### Debug Commands

```bash
# Check service status
gcloud run services describe lyo-backend --region us-central1

# View detailed logs
gcloud logging read "resource.type=cloud_run_revision" --limit=100

# Test connectivity
gcloud run services proxy lyo-backend --port=8080
```

## Success Checklist

- [ ] Google Cloud project created and configured
- [ ] Service account created with proper permissions  
- [ ] Cloud SQL PostgreSQL instance running
- [ ] API keys stored in Secret Manager
- [ ] Application successfully deployed to Cloud Run
- [ ] Health endpoint responding
- [ ] API documentation accessible
- [ ] Database schema initialized
- [ ] Custom domain configured (if applicable)
- [ ] Monitoring and logging enabled
- [ ] Backup strategy in place

Your LyoBackend is now successfully deployed to Google Cloud Run! 🎉

The deployment includes:
- ✅ Scalable FastAPI application
- ✅ PostgreSQL database
- ✅ AI integrations (OpenAI, Gemini)
- ✅ Secure secret management
- ✅ Production-ready monitoring
- ✅ Health checks and logging
- ✅ Auto-scaling capabilities

Your backend is ready for production use!
