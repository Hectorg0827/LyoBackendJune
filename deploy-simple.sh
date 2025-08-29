#!/bin/bash

# Simple Cloud Run Deployment Script for LyoBackend Phase 3
# Uses minimal requirements to avoid dependency conflicts

set -e

echo "🚀 Starting Simple LyoBackend Phase 3 Deployment..."

# Configuration
PROJECT_ID="${1:-lyobackend}"
SERVICE_NAME="lyobackend-phase3-simple"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "📋 Configuration:"
echo "  Project ID: ${PROJECT_ID}"
echo "  Service Name: ${SERVICE_NAME}"
echo "  Region: ${REGION}"
echo "  Image: ${IMAGE_NAME}"

# Enable required APIs
echo "🔧 Enabling required Google Cloud APIs..."
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# Build and push Docker image
echo "🏗️ Building Docker image..."
docker build -f Dockerfile.simple -t ${IMAGE_NAME} .

echo "📤 Pushing image to Google Container Registry..."
gcloud auth configure-docker --quiet
docker push ${IMAGE_NAME}

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
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
  --set-env-vars "DATABASE_URL=sqlite:///lyo_app_prod.db"

echo "✅ Deployment completed!"
echo ""
echo "🌐 Service URL:"
gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)"

echo ""
echo "📊 To check logs:"
echo "gcloud logs read --filter=\"resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE_NAME}\" --limit=50"
