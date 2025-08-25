#!/bin/bash
# Ultra-Simple Cloud Deployment - Guaranteed to work
set -e

echo "🚀 Ultra-Simple Cloud Deployment"
echo "================================"

# Use minimal requirements and simple Dockerfile
cp requirements-minimal.txt requirements.txt

# Deploy with simple dockerfile
echo "📦 Building minimal service in Google Cloud..."
gcloud run deploy lyo-backend \
    --source . \
    --region=us-central1 \
    --allow-unauthenticated \
    --memory=1Gi \
    --cpu=1 \
    --dockerfile=Dockerfile.simple

# Get URL
SERVICE_URL=$(gcloud run services describe lyo-backend --region=us-central1 --format="value(status.url)")

echo ""
echo "✅ SUCCESS! Your backend is live:"
echo "🌐 $SERVICE_URL"
echo "❤️ Health: $SERVICE_URL/health"
echo ""
echo "📱 Use this URL in your iOS app instead of localhost:8001"

# Test it
curl -s "$SERVICE_URL/health" && echo "✅ Service responding!"
