#!/bin/bash
# GCR Deployment Status Checker

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🔍 Checking GCR Deployment Status${NC}"
echo -e "${GREEN}================================${NC}"

BUILD_ID="4175a567-e6ca-4ec9-b34b-6d16998a0b1b"
PROJECT_ID="lyobackend"
IMAGE_NAME="gcr.io/$PROJECT_ID/lyo-backend-production:latest"

echo -e "${BLUE}📋 Build Details:${NC}"
echo -e "   Build ID: $BUILD_ID"
echo -e "   Project: $PROJECT_ID"
echo -e "   Image: $IMAGE_NAME"
echo ""

# Check build status
echo -e "${GREEN}1️⃣ Checking build status...${NC}"
BUILD_STATUS=$(gcloud builds describe $BUILD_ID --format="value(status)" 2>/dev/null || echo "UNKNOWN")
BUILD_TIME=$(gcloud builds describe $BUILD_ID --format="value(createTime)" 2>/dev/null || echo "UNKNOWN")

echo -e "   Status: $BUILD_STATUS"
echo -e "   Started: $BUILD_TIME"

case $BUILD_STATUS in
    "SUCCESS")
        echo -e "${GREEN}✅ Build completed successfully!${NC}"
        ;;
    "WORKING" | "QUEUED")
        echo -e "${YELLOW}⏳ Build is still in progress...${NC}"
        echo -e "${BLUE}🌐 Monitor at: https://console.cloud.google.com/cloud-build/builds/$BUILD_ID?project=$PROJECT_ID${NC}"
        ;;
    "FAILURE" | "CANCELLED" | "TIMEOUT")
        echo -e "${RED}❌ Build failed with status: $BUILD_STATUS${NC}"
        echo -e "${BLUE}📋 Check logs at: https://console.cloud.google.com/cloud-build/builds/$BUILD_ID?project=$PROJECT_ID${NC}"
        ;;
    *)
        echo -e "${YELLOW}⚠️  Unknown build status: $BUILD_STATUS${NC}"
        ;;
esac

echo ""

# Check if image exists in GCR
echo -e "${GREEN}2️⃣ Checking GCR image...${NC}"
if gcloud container images describe $IMAGE_NAME --quiet > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Image found in GCR!${NC}"
    
    # Get image details
    IMAGE_SIZE=$(gcloud container images describe $IMAGE_NAME --format="value(image_summary.layer_id)" 2>/dev/null | wc -l || echo "unknown")
    CREATION_TIME=$(gcloud container images describe $IMAGE_NAME --format="value(image_summary.time_created_utc)" 2>/dev/null || echo "unknown")
    
    echo -e "   Layers: $IMAGE_SIZE"
    echo -e "   Created: $CREATION_TIME"
    echo -e "   Registry: $IMAGE_NAME"
    
    echo ""
    echo -e "${GREEN}🚀 Ready to deploy! Use this image:${NC}"
    echo -e "${BLUE}   $IMAGE_NAME${NC}"
    
else
    echo -e "${YELLOW}⏳ Image not yet available in GCR${NC}"
    echo -e "${BLUE}   This is normal if the build is still in progress${NC}"
fi

echo ""

# Check if Cloud Run service exists
echo -e "${GREEN}3️⃣ Checking Cloud Run deployment...${NC}"
SERVICE_NAME="lyo-backend-production"
REGION="us-central1"

if gcloud run services describe $SERVICE_NAME --region=$REGION --quiet > /dev/null 2>&1; then
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)" 2>/dev/null)
    echo -e "${GREEN}✅ Cloud Run service is deployed!${NC}"
    echo -e "   Service: $SERVICE_NAME"
    echo -e "   Region: $REGION"
    echo -e "   URL: ${BLUE}$SERVICE_URL${NC}"
    
    # Test the service
    if [ -n "$SERVICE_URL" ]; then
        echo ""
        echo -e "${GREEN}🧪 Testing service...${NC}"
        if curl -s "$SERVICE_URL/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Service is responding!${NC}"
            echo -e "${BLUE}📖 API Docs: $SERVICE_URL/docs${NC}"
        else
            echo -e "${YELLOW}⚠️  Service might be starting up...${NC}"
        fi
    fi
else
    echo -e "${YELLOW}⏳ Cloud Run service not yet deployed${NC}"
    echo -e "${BLUE}   Deploy manually when build completes:${NC}"
    echo -e "${BLUE}   gcloud run deploy $SERVICE_NAME --image $IMAGE_NAME --region $REGION --allow-unauthenticated${NC}"
fi

echo ""
echo -e "${GREEN}📊 Deployment Summary:${NC}"
echo "========================"
echo -e "Build Status: $BUILD_STATUS"
echo -e "GCR Image: $([ "$BUILD_STATUS" = "SUCCESS" ] && echo "✅ Available" || echo "⏳ Pending")"
echo -e "Cloud Run: $(gcloud run services describe $SERVICE_NAME --region=$REGION --quiet > /dev/null 2>&1 && echo "✅ Deployed" || echo "⏳ Pending")"
echo ""

if [ "$BUILD_STATUS" = "WORKING" ] || [ "$BUILD_STATUS" = "QUEUED" ]; then
    echo -e "${YELLOW}🕐 Build in progress. Run this script again in a few minutes.${NC}"
fi
