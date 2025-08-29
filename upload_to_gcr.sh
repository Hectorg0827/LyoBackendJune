#!/bin/bash

# GCR Upload Script for LyoBackend with Power Users
set -e

echo "🚀 Starting LyoBackend deployment to Google Container Registry..."

# Configuration
PROJECT_ID="lyobackend"
IMAGE_NAME="lyo-backend-power-users"
REGION="us-central1"
SERVICE_NAME="lyo-backend-service"

# Verify required files exist
echo "📋 Checking required files..."
required_files=(
    "lyo_app_dev.db"
    "simple_main.py"
    "requirements-minimal.txt"
    ".env"
)

for file in "${required_files[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo "❌ Error: Required file $file not found!"
        exit 1
    fi
    echo "✅ Found: $file"
done

# Check Docker daemon
echo "🐳 Checking Docker daemon..."
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker daemon is not running. Please start Docker Desktop."
    exit 1
fi
echo "✅ Docker daemon is running"

# Build Docker image
echo "🔨 Building Docker image..."
cat > Dockerfile.gcr << 'EOF'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc sqlite3 && rm -rf /var/lib/apt/lists/*

COPY requirements-minimal.txt .
RUN pip install --no-cache-dir -r requirements-minimal.txt

COPY . .

RUN mkdir -p uploads
RUN ls -la lyo_app_dev.db && echo "Database verified"

EXPOSE 8080

ENV PYTHONPATH=/app
ENV PORT=8080
ENV HOST=0.0.0.0

CMD ["python", "simple_main.py"]
EOF

if docker build -t $IMAGE_NAME -f Dockerfile.gcr .; then
    echo "✅ Docker image built successfully"
else
    echo "❌ Docker build failed"
    exit 1
fi

# Configure gcloud (if not already done)
echo "☁️  Configuring Google Cloud..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "Please authenticate with Google Cloud:"
    gcloud auth login
fi

# Set project
gcloud config set project $PROJECT_ID

# Configure Docker for GCR
echo "🔐 Configuring Docker for GCR..."
gcloud auth configure-docker gcr.io

# Tag image for GCR
GCR_IMAGE="gcr.io/$PROJECT_ID/$IMAGE_NAME:latest"
echo "🏷️  Tagging image as $GCR_IMAGE..."
docker tag $IMAGE_NAME $GCR_IMAGE

# Push to GCR
echo "⬆️  Pushing to Google Container Registry..."
if docker push $GCR_IMAGE; then
    echo "✅ Successfully pushed to GCR: $GCR_IMAGE"
else
    echo "❌ Failed to push to GCR"
    exit 1
fi

# Deploy to Cloud Run
echo "🚢 Deploying to Cloud Run..."
if gcloud run deploy $SERVICE_NAME \
    --image $GCR_IMAGE \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --port 8080 \
    --memory 1Gi \
    --cpu 1 \
    --max-instances 10 \
    --set-env-vars "PORT=8080,HOST=0.0.0.0"; then
    
    echo "✅ Successfully deployed to Cloud Run!"
    
    # Get service URL
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")
    echo "🌐 Service URL: $SERVICE_URL"
    echo "🎉 Deployment complete! Your LyoBackend with power users is now live!"
    
else
    echo "❌ Cloud Run deployment failed"
    exit 1
fi

echo "🎯 Deployment Summary:"
echo "  - Project: $PROJECT_ID"
echo "  - Image: $GCR_IMAGE"
echo "  - Service: $SERVICE_NAME"
echo "  - Region: $REGION"
echo "  - URL: $SERVICE_URL"
