#!/bin/bash

# Direct Cloud Build Deployment for LyoBackend Phase 3
# Bypasses local Docker completely - builds directly in cloud

set -e

echo "☁️ Direct Cloud Build Deployment for LyoBackend Phase 3..."

# Configuration
PROJECT_ID="${1:-lyobackend}"
SERVICE_NAME="lyobackend-phase3"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

if [ -z "$1" ]; then
    echo "⚠️  No project ID provided, using default: ${PROJECT_ID}"
    echo "   To use your project: ./direct-deploy.sh YOUR_PROJECT_ID"
    echo ""
fi

echo "📋 Configuration:"
echo "  Project ID: ${PROJECT_ID}"
echo "  Service Name: ${SERVICE_NAME}"
echo "  Region: ${REGION}"
echo "  Image: ${IMAGE_NAME}"
echo ""

# Set the project
echo "🔧 Setting Google Cloud project..."
gcloud config set project ${PROJECT_ID}

# Enable required APIs
echo "🔧 Enabling required Google Cloud APIs..."
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com

echo ""
echo "🏗️ Building image directly in Google Cloud Build..."
echo "   This will use Cloud Build instead of local Docker"

# Submit build to Cloud Build
gcloud builds submit \
  --tag ${IMAGE_NAME} \
  --dockerfile Dockerfile.simple \
  --timeout=20m

echo ""
echo "🚀 Deploying to Cloud Run..."

# Deploy to Cloud Run
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --port 8000 \
  --memory 1Gi \
  --cpu 1 \
  --max-instances 10 \
  --concurrency 80 \
  --timeout 300 \
  --set-env-vars "ENVIRONMENT=production" \
  --set-env-vars "DATABASE_URL=sqlite:///lyo_app_prod.db" \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"

echo ""
echo "✅ Deployment completed successfully!"
echo ""

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")
echo "🌐 Your LyoBackend Phase 3 is now live at:"
echo "   ${SERVICE_URL}"
echo ""

echo "🔍 Quick health check:"
echo "   ${SERVICE_URL}/health"
echo ""

echo "📊 To monitor your deployment:"
echo "   Logs: gcloud logs read --filter=\"resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE_NAME}\" --limit=50"
echo "   Console: https://console.cloud.google.com/run/detail/${REGION}/${SERVICE_NAME}/metrics?project=${PROJECT_ID}"
echo ""

echo "🎉 Phase 3 deployment complete with:"
echo "   ✅ Distributed tracing (OpenTelemetry)"
echo "   ✅ AI optimization capabilities" 
echo "   ✅ Auto-scaling (1-10 instances)"
echo "   ✅ Health monitoring"
echo "   ✅ SQLite database"
echo "   ✅ Production-ready configuration"
