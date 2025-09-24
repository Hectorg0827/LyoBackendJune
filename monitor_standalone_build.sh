#!/bin/bash
# Monitor the new standalone GCR build

BUILD_ID="960fbcd7-a014-4c61-a040-3801afbe3a2e"
PROJECT_ID="lyobackend"
IMAGE_NAME="gcr.io/$PROJECT_ID/lyo-backend-production:latest"

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🔄 Monitoring Standalone Backend GCR Build${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "${BLUE}Build ID: $BUILD_ID${NC}"
echo -e "${BLUE}Image: $IMAGE_NAME${NC}"
echo -e "${BLUE}Logs: https://console.cloud.google.com/cloud-build/builds/$BUILD_ID?project=$PROJECT_ID${NC}"
echo ""

# Real-time monitoring loop
while true; do
    STATUS=$(gcloud builds describe $BUILD_ID --format="value(status)" 2>/dev/null || echo "UNKNOWN")
    
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] Status: $STATUS${NC}"
    
    case $STATUS in
        "SUCCESS")
            echo -e "${GREEN}🎉 BUILD SUCCESSFUL!${NC}"
            echo ""
            
            # Verify image in GCR
            if gcloud container images describe $IMAGE_NAME --quiet > /dev/null 2>&1; then
                echo -e "${GREEN}✅ Image successfully uploaded to GCR!${NC}"
                echo -e "${BLUE}📦 Image: $IMAGE_NAME${NC}"
                
                # Get image details
                DIGEST=$(gcloud container images describe $IMAGE_NAME --format="value(image_summary.fully_qualified_digest)" 2>/dev/null || echo "N/A")
                SIZE_MB=$(gcloud container images describe $IMAGE_NAME --format="value(image_summary.layer_id)" 2>/dev/null | wc -l || echo "N/A")
                
                echo -e "${BLUE}📋 Layers: $SIZE_MB${NC}"
                echo -e "${BLUE}🔗 Digest: ${DIGEST:0:20}...${NC}"
                
                echo ""
                echo -e "${GREEN}🚀 READY TO DEPLOY!${NC}"
                echo -e "${BLUE}Deploy command:${NC}"
                echo -e "gcloud run deploy lyo-backend-production \\"
                echo -e "  --image $IMAGE_NAME \\"
                echo -e "  --region us-central1 \\"
                echo -e "  --allow-unauthenticated \\"
                echo -e "  --memory 2Gi \\"
                echo -e "  --cpu 2"
                
            else
                echo -e "${YELLOW}⏳ Image uploading to GCR...${NC}"
            fi
            break
            ;;
        "FAILURE"|"CANCELLED"|"TIMEOUT")
            echo -e "${RED}❌ Build failed: $STATUS${NC}"
            echo -e "${BLUE}📋 Check logs for details${NC}"
            
            # Show last few lines of logs
            echo -e "${YELLOW}Last log entries:${NC}"
            gcloud builds log $BUILD_ID | tail -10 2>/dev/null || echo "Could not fetch logs"
            break
            ;;
        "WORKING"|"QUEUED")
            echo -e "${BLUE}⏳ Build in progress...${NC}"
            ;;
        *)
            echo -e "${YELLOW}⚠️ Unknown status: $STATUS${NC}"
            ;;
    esac
    
    sleep 10
done

echo ""
echo -e "${GREEN}🎊 Monitoring complete!${NC}"
