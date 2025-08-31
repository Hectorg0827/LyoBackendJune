#!/bin/bash

echo "🚀 Deploying Superior AI Backend to Cloud Run"
echo "🎯 Target: https://lyo-backend-830162750094.us-central1.run.app"

# Simple approach: Use gcloud run deploy with source
gcloud run deploy lyo-backend \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 10 \
  --timeout 300 \
  --set-env-vars "ENABLE_SUPERIOR_AI_MODE=true,ENABLE_ADAPTIVE_DIFFICULTY=true,ENABLE_ADVANCED_SOCRATIC=true"

echo "✅ Superior AI Backend deployment initiated"
