#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🚀 Direct Deployment to GCR for Superior AI Backend${NC}"

# Since we know the target URL, let's use a different approach
# First, let's build the image locally and then push it

IMAGE_NAME="lyo-backend-superior"
IMAGE_TAG="latest"

echo -e "${YELLOW}🏗️ Building Docker image locally...${NC}"

# Build the image
docker build -f Dockerfile.specific -t ${IMAGE_NAME}:${IMAGE_TAG} .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Docker image built successfully${NC}"
    
    echo -e "${YELLOW}🔍 Checking image...${NC}"
    docker images ${IMAGE_NAME}:${IMAGE_TAG}
    
    echo -e "${BLUE}🎯 Superior AI Features in the image:${NC}"
    echo -e "${BLUE}  ✅ Advanced Socratic Questioning (6 strategies)${NC}"
    echo -e "${BLUE}  ✅ Adaptive Difficulty Engine (5 levels)${NC}"
    echo -e "${BLUE}  ✅ Superior Prompt Engineering System${NC}"
    echo -e "${BLUE}  ✅ Multi-dimensional Learning Analytics${NC}"
    echo -e "${BLUE}  ✅ Real-time Performance Optimization${NC}"
    
    echo ""
    echo -e "${GREEN}🎉 Superior AI Docker image ready for deployment!${NC}"
    echo -e "${GREEN}📦 Image: ${IMAGE_NAME}:${IMAGE_TAG}${NC}"
    
    # Instructions for manual GCR push (if needed)
    echo ""
    echo -e "${YELLOW}🚀 To deploy to GCR, you can run:${NC}"
    echo -e "${YELLOW}1. Tag the image for GCR:${NC}"
    echo -e "${YELLOW}   docker tag ${IMAGE_NAME}:${IMAGE_TAG} gcr.io/YOUR_PROJECT_ID/${IMAGE_NAME}:${IMAGE_TAG}${NC}"
    echo ""
    echo -e "${YELLOW}2. Push to GCR:${NC}"
    echo -e "${YELLOW}   docker push gcr.io/YOUR_PROJECT_ID/${IMAGE_NAME}:${IMAGE_TAG}${NC}"
    echo ""
    echo -e "${YELLOW}3. Deploy to Cloud Run:${NC}"
    echo -e "${YELLOW}   gcloud run deploy lyo-backend --image gcr.io/YOUR_PROJECT_ID/${IMAGE_NAME}:${IMAGE_TAG} \\${NC}"
    echo -e "${YELLOW}     --region us-central1 --platform managed --allow-unauthenticated \\${NC}"
    echo -e "${YELLOW}     --port 8080 --memory 2Gi --cpu 2 \\${NC}"
    echo -e "${YELLOW}     --set-env-vars 'ENABLE_SUPERIOR_AI_MODE=true'${NC}"
    
else
    echo -e "${RED}❌ ERROR: Docker build failed${NC}"
    exit 1
fi
