#!/bin/bash
# Alternative: Source-based deployment (even simpler)
# Uses Cloud Build automatically behind the scenes

set -e

PROJECT_ID=${1:-$(gcloud config get-value project 2>/dev/null)}
if [ -z "$PROJECT_ID" ]; then
    echo "Usage: $0 <project-id>"
    echo "Or run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

SERVICE_NAME="lyo-backend"
REGION="us-central1"

echo "🚀 Source-based deployment (Cloud Build automatic)"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Enable services
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

# Deploy directly from source (Cloud Build handles everything)
echo "🏗️ Building and deploying from source..."
gcloud run deploy $SERVICE_NAME \
    --source . \
    --region=$REGION \
    --allow-unauthenticated \
    --memory=2Gi \
    --cpu=2 \
    --timeout=300 \
    --set-env-vars="ENVIRONMENT=production"

# Get URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo ""
echo "✅ Deployed! Your service: $SERVICE_URL"
echo "📖 API docs: $SERVICE_URL/docs"
echo "❤️ Health: $SERVICE_URL/health"

# Test
curl -s "$SERVICE_URL/health" && echo "✅ Service responding!"
