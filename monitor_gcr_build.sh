#!/bin/bash
# Real-time GCR Deployment Monitor

BUILD_ID="a630ee53-188f-4fd9-aae8-821e1d9d3541"
PROJECT_ID="lyobackend"
IMAGE_NAME="gcr.io/$PROJECT_ID/lyo-backend-production:latest"

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🔄 Monitoring GCR Deployment${NC}"
echo -e "${GREEN}=============================${NC}"
echo -e "${BLUE}Build ID: $BUILD_ID${NC}"
echo -e "${BLUE}Logs: https://console.cloud.google.com/cloud-build/builds/$BUILD_ID?project=$PROJECT_ID${NC}"
echo ""

while true; do
    # Get current status
    STATUS=$(gcloud builds describe $BUILD_ID --format="value(status)" 2>/dev/null || echo "UNKNOWN")
    
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] Status: $STATUS${NC}"
    
    case $STATUS in
        "SUCCESS")
            echo -e "${GREEN}🎉 Build completed successfully!${NC}"
            
            # Check if image is in GCR
            if gcloud container images describe $IMAGE_NAME --quiet > /dev/null 2>&1; then
                echo -e "${GREEN}✅ Image available in GCR: $IMAGE_NAME${NC}"
                
                # Get image details
                DIGEST=$(gcloud container images describe $IMAGE_NAME --format="value(image_summary.fully_qualified_digest)" 2>/dev/null || echo "unknown")
                echo -e "${BLUE}📦 Image digest: $DIGEST${NC}"
                
                echo ""
                echo -e "${GREEN}🚀 Ready to deploy to Cloud Run!${NC}"
                echo -e "${BLUE}Command: gcloud run deploy lyo-backend-production --image $IMAGE_NAME --region us-central1 --allow-unauthenticated${NC}"
            else
                echo -e "${YELLOW}⏳ Waiting for image to appear in GCR...${NC}"
            fi
            break
            ;;
        "FAILURE"|"CANCELLED"|"TIMEOUT")
            echo -e "${RED}❌ Build failed with status: $STATUS${NC}"
            echo -e "${BLUE}📋 Check logs for details${NC}"
            break
            ;;
        "WORKING"|"QUEUED")
            echo -e "${BLUE}⏳ Build in progress...${NC}"
            ;;
        *)
            echo -e "${YELLOW}⚠️  Unknown status: $STATUS${NC}"
            ;;
    esac
    
    sleep 10
done
