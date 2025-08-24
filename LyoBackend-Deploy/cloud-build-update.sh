#!/bin/bash
# Cloud Build Update Script - Updates service with your actual LyoBackend code
# Builds in Google Cloud to prevent local system stress

set -e

PROJECT_ID=${1:-$(gcloud config get-value project)}
SERVICE_NAME="lyo-backend"
REGION="us-central1"

echo "🔄 Updating LyoBackend with Cloud Build (safe method)"
echo "=================================================="

# Create a simple Dockerfile for cloud builds
cat > Dockerfile.minimal << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Set environment
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "lyo_app.enhanced_main:app", "--host", "0.0.0.0", "--port", "8080"]
EOF

echo "1️⃣ Building image in Google Cloud..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME --dockerfile=Dockerfile.minimal

echo "2️⃣ Updating Cloud Run service..."
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --region $REGION \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --set-env-vars="ENVIRONMENT=production,DEBUG=false,PORT=8080" \
    --timeout=300

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo "✅ Service updated!"
echo "🌐 URL: $SERVICE_URL"
echo "🔍 Test health: curl $SERVICE_URL/health"
echo "🔍 Test API: curl $SERVICE_URL/docs"
