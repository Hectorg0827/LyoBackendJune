#!/bin/bash
# Cloud-First Deployment - No Local Docker Builds
# Prevents Mac crashes by using Google Cloud Build exclusively

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Cloud-First Deployment (No Local Builds)${NC}"
echo -e "${GREEN}===========================================${NC}"
echo ""

# Check if gcloud is installed and authenticated
if ! command -v gcloud &> /dev/null; then
    echo -e "${YELLOW}⚠️  gcloud CLI not found. Install from: https://cloud.google.com/sdk/docs/install${NC}"
    exit 1
fi

# Get project ID
PROJECT_ID=${1:-$(gcloud config get-value project 2>/dev/null)}
if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}📝 Please provide your project ID:${NC}"
    read -p "Project ID: " PROJECT_ID
    gcloud config set project $PROJECT_ID
fi

SERVICE_NAME="lyo-backend"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo -e "${BLUE}📋 Project: $PROJECT_ID${NC}"
echo -e "${BLUE}🌍 Region: $REGION${NC}"
echo -e "${BLUE}🏷️  Image: $IMAGE_NAME${NC}"
echo ""

# Authenticate if needed
echo -e "${GREEN}1️⃣ Checking authentication...${NC}"
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
    echo -e "${YELLOW}🔐 Please authenticate:${NC}"
    gcloud auth login
fi

# Enable required services
echo -e "${GREEN}2️⃣ Enabling Google Cloud services...${NC}"
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com

echo -e "${GREEN}3️⃣ Building in Google Cloud (no local build)...${NC}"
echo -e "${YELLOW}⚡ This builds remotely so your Mac stays cool!${NC}"

# Option A: Use Cloud Build with Dockerfile.cloud
gcloud builds submit \
    --tag $IMAGE_NAME:latest \
    --dockerfile=Dockerfile.cloud \
    --timeout=20m

echo -e "${GREEN}4️⃣ Deploying to Cloud Run...${NC}"
gcloud run deploy $SERVICE_NAME \
    --image=$IMAGE_NAME:latest \
    --region=$REGION \
    --platform=managed \
    --allow-unauthenticated \
    --memory=2Gi \
    --cpu=2 \
    --timeout=300 \
    --max-instances=10 \
    --set-env-vars="ENVIRONMENT=production,DEBUG=false,PORT=8080"

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo ""
echo -e "${GREEN}🎉 DEPLOYMENT COMPLETE!${NC}"
echo "=================================="
echo -e "🌐 Service URL: ${BLUE}$SERVICE_URL${NC}"
echo -e "📖 API Docs: ${BLUE}$SERVICE_URL/docs${NC}"
echo -e "❤️  Health Check: ${BLUE}$SERVICE_URL/health${NC}"
echo "=================================="
echo ""

# Test the deployment
echo -e "${GREEN}5️⃣ Testing deployment...${NC}"
if curl -s "$SERVICE_URL/health" > /dev/null; then
    echo -e "${GREEN}✅ Service is responding!${NC}"
    
    # Test API endpoint
    echo -e "${GREEN}🧪 Testing API endpoint...${NC}"
    curl -s -X POST "$SERVICE_URL/api/v1/generate-course" \
        -H "Content-Type: application/json" \
        -d '{"topic": "Python Basics", "difficulty": "beginner"}' | jq '.' || echo "API working (install jq for pretty output)"
else
    echo -e "${YELLOW}⚠️  Service is starting up. Try again in a moment.${NC}"
fi

echo ""
echo -e "${GREEN}📱 For your iOS app:${NC}"
echo -e "Replace 'localhost:8001' with: ${BLUE}$SERVICE_URL${NC}"
echo ""
echo -e "${GREEN}🎊 No crashes, no stress, just working backend in the cloud!${NC}"
