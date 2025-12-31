# 🚀 Deploy to Google Cloud Run

## Quick Start - Choose Your Deployment Method

### ✅ Option 1: Cloud Build (Recommended - Automated CI/CD)

**Best for:** Production deployments, automated workflows

```bash
# From your local machine with gcloud CLI installed:
gcloud builds submit --config cloudbuild.yaml
```

**What it does:**
- Builds Docker image using `Dockerfile.cloud`
- Pushes to Artifact Registry
- Deploys to Cloud Run with full production configuration
- Configures: 8Gi memory, 4 CPUs, VPC connector, Redis, all secrets

**Project Configuration (from cloudbuild.yaml):**
- Service: `lyo-backend-production`
- Region: `us-central1`
- Project: `lyobackend`
- Image: `us-central1-docker.pkg.dev/lyobackend/lyo-backend-repo/lyo-backend-production:latest`

---

### ✅ Option 2: Enhanced Deployment Script

**Best for:** Production with custom configuration

```bash
# Configure and deploy:
PROJECT_ID=lyobackend REGION=us-central1 ./deploy_cloudrun.sh
```

**Features:**
- ✓ Secret Manager integration
- ✓ Cloud SQL connector
- ✓ Health check verification
- ✓ Automatic service account setup
- ✓ Comprehensive error handling

**Required Secrets (must be created in Secret Manager):**
- `secret-key` - JWT secret key
- `openai-api-key` - OpenAI API key
- `gemini-api-key` - Google Gemini API key
- `database-url` - PostgreSQL connection string

**Optional:**
- Cloud SQL instance named `lyo-postgres` (auto-detected)

---

### ✅ Option 3: Interactive Setup (First-Time Deployment)

**Best for:** Initial setup, learning, or custom configurations

```bash
./deploy-to-gcp.sh
```

**What it does:**
- Guides you through configuration
- Creates Cloud SQL instance (optional)
- Sets up Artifact Registry
- Creates all necessary secrets
- Configures service account with proper permissions
- Deploys with full configuration

**Interactive prompts for:**
- GCP Project ID
- Region
- Service name
- Database setup
- Redis configuration

---

## Prerequisites

### 1. Install Google Cloud SDK

```bash
# macOS
brew install --cask google-cloud-sdk

# Linux
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Windows
# Download from: https://cloud.google.com/sdk/docs/install
```

### 2. Authenticate

```bash
gcloud auth login
gcloud auth application-default login
```

### 3. Enable Required APIs

```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com
```

---

## Production Configuration (Cloud Build)

The `cloudbuild.yaml` is pre-configured for production:

### Resources:
- **Memory:** 8 Gi
- **CPU:** 4 cores
- **Instances:** Min 1, Max 10
- **Timeout:** 300 seconds
- **CPU Boost:** Enabled

### Environment Variables:
```
ENVIRONMENT=production
DEBUG=false
GCP_PROJECT_ID=lyobackend
GCS_BUCKET_NAME=lyobackend-storage
REDIS_HOST=10.57.97.243
REDIS_PORT=6379
FIREBASE_PROJECT_ID=lyo-app
WORKERS=1
```

### Secrets (from Secret Manager):
```
SECRET_KEY=jwt-secret:latest
DATABASE_URL=database-url:latest
GEMINI_API_KEY=gemini-api-key:latest
OPENAI_API_KEY=openai-api-key:latest
STRIPE_SECRET_KEY=stripe-secret-key:latest
STRIPE_PUBLISHABLE_KEY=stripe-publishable-key:latest
STRIPE_WEBHOOK_SECRET=stripe-webhook-secret:latest
FIREBASE_CREDENTIALS_JSON=firebase-credentials:latest
```

### VPC Configuration:
- **VPC Connector:** `lyo-connector`
- **Redis Internal IP:** `10.57.97.243:6379`

---

## Step-by-Step: Cloud Build Deployment

### 1. Ensure Latest Code on Main Branch

```bash
git checkout main
git pull origin main
```

### 2. Verify Secrets Exist

```bash
# Check if all required secrets exist:
gcloud secrets list --project=lyobackend --filter="name:(jwt-secret OR database-url OR gemini-api-key OR openai-api-key)"
```

### 3. Create Missing Secrets

```bash
# Example: Create database-url secret
echo -n "postgresql+asyncpg://user:password@/dbname?host=/cloudsql/CONNECTION_NAME" | \
  gcloud secrets create database-url --data-file=- --project=lyobackend

# Example: Create JWT secret
openssl rand -base64 32 | gcloud secrets create jwt-secret --data-file=- --project=lyobackend

# Example: Create API keys
echo -n "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=- --project=lyobackend
echo -n "your-openai-api-key" | gcloud secrets create openai-api-key --data-file=- --project=lyobackend
```

### 4. Run Cloud Build

```bash
gcloud builds submit --config cloudbuild.yaml --project=lyobackend
```

### 5. Monitor Deployment

```bash
# View logs
gcloud run logs read --service=lyo-backend-production --region=us-central1 --project=lyobackend

# Check service status
gcloud run services describe lyo-backend-production --region=us-central1 --project=lyobackend
```

### 6. Get Service URL

```bash
gcloud run services describe lyo-backend-production \
  --region=us-central1 \
  --project=lyobackend \
  --format="value(status.url)"
```

### 7. Test Deployment

```bash
SERVICE_URL=$(gcloud run services describe lyo-backend-production --region=us-central1 --project=lyobackend --format="value(status.url)")

# Health check
curl $SERVICE_URL/health

# API documentation
open $SERVICE_URL/docs
```

---

## Quick Deploy Commands

### Deploy from Local Machine:

```bash
# Set project
gcloud config set project lyobackend

# Deploy using Cloud Build (Recommended)
gcloud builds submit --config cloudbuild.yaml

# OR deploy using deployment script
PROJECT_ID=lyobackend REGION=us-central1 ./deploy_cloudrun.sh
```

### Deploy from GitHub Actions:

Already configured in `.github/workflows/production-deployment.yml`:
- Triggered on push to `main` branch
- Builds Docker image
- Deploys to production environment

---

## Troubleshooting

### Error: "Secret not found"

```bash
# List all secrets
gcloud secrets list --project=lyobackend

# Create missing secret
echo -n "your-secret-value" | gcloud secrets create secret-name --data-file=- --project=lyobackend
```

### Error: "Permission denied"

```bash
# Grant yourself permissions
gcloud projects add-iam-policy-binding lyobackend \
  --member="user:your-email@example.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding lyobackend \
  --member="user:your-email@example.com" \
  --role="roles/secretmanager.admin"
```

### Error: "VPC connector not found"

Option 1: Create VPC connector:
```bash
gcloud compute networks vpc-access connectors create lyo-connector \
  --network=default \
  --region=us-central1 \
  --range=10.8.0.0/28
```

Option 2: Remove VPC connector from cloudbuild.yaml (line 54):
```yaml
# Comment out or remove this line:
# --vpc-connector=lyo-connector \
```

### Error: "Cloud SQL connection failed"

Verify Cloud SQL connection name and update DATABASE_URL secret:
```bash
# Get connection name
gcloud sql instances describe INSTANCE_NAME --format="value(connectionName)"

# Update DATABASE_URL with correct connection name
echo -n "postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/CONNECTION_NAME" | \
  gcloud secrets versions add database-url --data-file=-
```

---

## Post-Deployment

### Monitor Your Service:

```bash
# View real-time logs
gcloud run logs tail --service=lyo-backend-production --region=us-central1

# View metrics
gcloud run services describe lyo-backend-production --region=us-central1 --format=json
```

### Update Environment Variables:

```bash
gcloud run services update lyo-backend-production \
  --region=us-central1 \
  --set-env-vars="NEW_VAR=value"
```

### Update Secrets:

```bash
# Add new version to existing secret
echo -n "new-secret-value" | gcloud secrets versions add secret-name --data-file=-

# Cloud Run automatically uses :latest
```

### Scale Configuration:

```bash
gcloud run services update lyo-backend-production \
  --region=us-central1 \
  --min-instances=2 \
  --max-instances=20 \
  --memory=16Gi \
  --cpu=8
```

---

## Service URLs (After Deployment)

Once deployed, your service will be available at:

```
https://lyo-backend-production-XXXXX-uc.a.run.app
```

**Endpoints:**
- Health: `/health`
- API Docs: `/docs`
- OpenAPI Spec: `/openapi.json`
- Metrics: `/metrics` (if enabled)

---

## CI/CD Integration

The GitHub Actions workflow (`.github/workflows/production-deployment.yml`) includes:

✓ Automated testing
✓ Docker image building
✓ Security scanning
✓ Cloud Run deployment (via ECS configuration)

To deploy via CI/CD:
1. Push to `main` branch
2. GitHub Actions automatically builds and deploys
3. Monitor in Actions tab

---

## Cost Optimization

Cloud Run pricing:
- **Free tier:** 2 million requests/month
- **Pay per use:** Only charged when handling requests
- **Min instances 0:** No charges when idle

**Recommendations:**
- Set `--min-instances=0` for development
- Set `--min-instances=1` for production (better latency)
- Use `--cpu-boost` for faster cold starts
- Monitor costs in GCP Console

---

## Support

For deployment issues:
- GCP Console: https://console.cloud.google.com/run?project=lyobackend
- Logs: https://console.cloud.google.com/logs/query?project=lyobackend
- Cloud Build History: https://console.cloud.google.com/cloud-build/builds?project=lyobackend

---

## Summary

**Fastest deployment:**
```bash
gcloud builds submit --config cloudbuild.yaml --project=lyobackend
```

**Custom deployment:**
```bash
PROJECT_ID=lyobackend ./deploy_cloudrun.sh
```

**First-time setup:**
```bash
./deploy-to-gcp.sh
```

🎉 **Your LyoBackend will be live in ~5-10 minutes!**
