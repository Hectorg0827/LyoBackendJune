#!/bin/bash

echo "🎯 LyoBackend Deployment Status"
echo "==============================="
echo ""

# Get the service URL
SERVICE_URL="https://lyo-backend-830162750094.us-central1.run.app"

echo "🌐 Service URL: $SERVICE_URL"
echo "📚 API Documentation: $SERVICE_URL/docs"
echo "❤️ Health Check: $SERVICE_URL/health"
echo "🧠 Superior AI: $SERVICE_URL/api/v1/study/superior-ai"
echo ""

# Check service status
echo "🔍 Checking service status..."
gcloud run services describe lyo-backend \
  --region=us-central1 \
  --project=lyobackend \
  --format="value(status.conditions[0].status,status.conditions[0].message)" 2>/dev/null || echo "Service not found or not accessible"

echo ""
echo "📊 Recent deployments:"
gcloud run revisions list \
  --service=lyo-backend \
  --region=us-central1 \
  --project=lyobackend \
  --limit=3 \
  --format="table(metadata.name,status.conditions[0].status,metadata.creationTimestamp)" 2>/dev/null || echo "Could not fetch revision list"

echo ""
echo "🧪 Testing deployment..."
python3 test_deployment.py "$SERVICE_URL"
