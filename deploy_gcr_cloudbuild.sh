#!/bin/bash

# Deploy LyoBackend with Power Users to GCR using Cloud Build
set -e

echo "🚀 Deploying LyoBackend with Power Users to Google Container Registry..."

PROJECT_ID="lyobackend"

# Verify database file exists
if [[ ! -f "lyo_app_dev.db" ]]; then
    echo "❌ Error: Database file lyo_app_dev.db not found!"
    echo "Please run: python quick_power_users.py"
    exit 1
fi

echo "✅ Database file found ($(ls -lh lyo_app_dev.db | awk '{print $5}'))"

# Check if gcloud is configured
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "🔐 Authenticating with Google Cloud..."
    gcloud auth login
fi

# Set project
echo "⚙️  Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com

# Submit build to Cloud Build
echo "🏗️  Submitting build to Cloud Build..."
gcloud builds submit --config cloudbuild-gcr.yaml --project $PROJECT_ID

echo "✅ Deployment complete!"
echo "🌐 Check your Cloud Run service at: https://console.cloud.google.com/run?project=$PROJECT_ID"

# Get service URL
SERVICE_URL=$(gcloud run services describe lyo-backend-power-users --region=us-central1 --format="value(status.url)" 2>/dev/null || echo "Service URL not available yet")
if [[ "$SERVICE_URL" != "Service URL not available yet" ]]; then
    echo "🎯 Service URL: $SERVICE_URL"
    echo "🧪 Test the API: curl $SERVICE_URL/health"
fi
