#!/bin/bash
# GCR Upload Script for Fully Functional Backend
# Safe cloud-only build (no local Docker)

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 GCR Upload: Fully Functional Backend${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI not found. Install from: https://cloud.google.com/sdk/docs/install${NC}"
    exit 1
fi

# Get project ID
PROJECT_ID=${1:-$(gcloud config get-value project 2>/dev/null)}
if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}📝 Enter your Google Cloud Project ID:${NC}"
    read -p "Project ID: " PROJECT_ID
    if [ -z "$PROJECT_ID" ]; then
        echo -e "${RED}❌ Project ID is required${NC}"
        exit 1
    fi
    gcloud config set project $PROJECT_ID
fi

# Configuration
SERVICE_NAME="lyo-backend-production"
IMAGE_TAG="gcr.io/$PROJECT_ID/$SERVICE_NAME:latest"
REGION="us-central1"

echo -e "${BLUE}📋 Configuration:${NC}"
echo -e "   Project: $PROJECT_ID"
echo -e "   Service: $SERVICE_NAME"
echo -e "   Image: $IMAGE_TAG"
echo -e "   Region: $REGION"
echo ""

# Check authentication
echo -e "${GREEN}1️⃣ Checking authentication...${NC}"
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
    echo -e "${YELLOW}🔐 Please authenticate:${NC}"
    gcloud auth login
fi

# Configure Docker for GCR
echo -e "${GREEN}2️⃣ Configuring Docker for GCR...${NC}"
gcloud auth configure-docker --quiet

# Enable required APIs
echo -e "${GREEN}3️⃣ Enabling required APIs...${NC}"
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable run.googleapis.com

echo -e "${GREEN}4️⃣ Building and uploading to GCR (cloud build)...${NC}"
echo -e "${YELLOW}⚡ Using cloud build to prevent local system crashes${NC}"

# Build and push to GCR using Cloud Build
gcloud builds submit \
    --tag $IMAGE_TAG \
    --dockerfile=Dockerfile.production-gcr \
    --timeout=20m \
    --machine-type=e2-highcpu-8

echo -e "${GREEN}✅ Build completed successfully!${NC}"

# Verify the image was uploaded
echo -e "${GREEN}5️⃣ Verifying GCR upload...${NC}"
if gcloud container images describe $IMAGE_TAG --quiet > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Image successfully uploaded to GCR!${NC}"
    
    # Get image details
    IMAGE_SIZE=$(gcloud container images describe $IMAGE_TAG --format="value(image_summary.fully_qualified_digest)" 2>/dev/null || echo "unknown")
    CREATION_TIME=$(gcloud container images describe $IMAGE_TAG --format="value(image_summary.time_created_utc)" 2>/dev/null || echo "unknown")
    
    echo ""
    echo -e "${BLUE}📦 Image Details:${NC}"
    echo -e "   URL: $IMAGE_TAG"
    echo -e "   Creation: $CREATION_TIME"
    echo ""
else
    echo -e "${RED}❌ Failed to verify image upload${NC}"
    exit 1
fi

echo -e "${GREEN}6️⃣ Optional: Deploy to Cloud Run?${NC}"
echo -e "${YELLOW}Press Enter to skip, or 'y' to deploy:${NC}"
read -p "" deploy_choice

if [ "$deploy_choice" = "y" ] || [ "$deploy_choice" = "Y" ]; then
    echo -e "${GREEN}🚀 Deploying to Cloud Run...${NC}"
    
    gcloud run deploy $SERVICE_NAME \
        --image=$IMAGE_TAG \
        --region=$REGION \
        --platform=managed \
        --allow-unauthenticated \
        --memory=2Gi \
        --cpu=2 \
        --timeout=300 \
        --max-instances=10 \
        --set-env-vars="ENVIRONMENT=production,DEBUG=false,PORT=8080"
    
    # Get service URL
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)" 2>/dev/null || echo "")
    
    if [ -n "$SERVICE_URL" ]; then
        echo ""
        echo -e "${GREEN}🎉 DEPLOYMENT COMPLETE!${NC}"
        echo "=================================="
        echo -e "🌐 Service URL: ${BLUE}$SERVICE_URL${NC}"
        echo -e "📖 API Docs: ${BLUE}$SERVICE_URL/docs${NC}"
        echo -e "❤️  Health Check: ${BLUE}$SERVICE_URL/health${NC}"
        echo "=================================="
        
        # Test the deployment
        echo -e "${GREEN}🧪 Testing deployment...${NC}"
        if curl -s "$SERVICE_URL/health" > /dev/null; then
            echo -e "${GREEN}✅ Service is responding!${NC}"
        else
            echo -e "${YELLOW}⚠️  Service is starting up. Try again in a moment.${NC}"
        fi
    fi
else
    echo -e "${GREEN}✅ Image uploaded to GCR. Deploy manually when ready.${NC}"
fi

echo ""
echo -e "${GREEN}🎊 GCR Upload Complete!${NC}"
echo -e "${BLUE}📝 To use this image:${NC}"
echo -e "   gcloud run deploy your-service --image $IMAGE_TAG"
echo -e "${BLUE}📝 To pull locally:${NC}"
echo -e "   docker pull $IMAGE_TAG"
echo ""
echo -e "${GREEN}🔒 Your fully functional backend is now in Google Container Registry!${NC}"
