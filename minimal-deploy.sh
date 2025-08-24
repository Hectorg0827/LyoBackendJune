#!/bin/bash
# Minimal Safe Deployment to Google Cloud Run
# Prevents computer crashes by avoiding local Docker builds

set -e

# Color codes for better output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Minimal Safe Deployment to Google Cloud Run${NC}"
echo -e "${GREEN}==============================================${NC}"
echo ""
echo -e "${YELLOW}⚡ This method avoids local Docker builds to prevent crashes${NC}"
echo ""

# Get project ID
if [ -z "$1" ]; then
    PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "")
    if [ -z "$PROJECT_ID" ]; then
        echo -e "${RED}❌ No project ID found${NC}"
        echo "Usage: $0 <project-id>"
        echo "Or run: gcloud config set project YOUR_PROJECT_ID"
        exit 1
    fi
    echo -e "${BLUE}📋 Using current project: $PROJECT_ID${NC}"
else
    PROJECT_ID=$1
    echo -e "${BLUE}📋 Using project: $PROJECT_ID${NC}"
    gcloud config set project $PROJECT_ID
fi

SERVICE_NAME="lyo-backend"
REGION="us-central1"

echo -e "${BLUE}🌍 Region: $REGION${NC}"
echo -e "${BLUE}📦 Service: $SERVICE_NAME${NC}"
echo ""

# Enable required APIs
echo -e "${GREEN}1️⃣ Enabling required Google Cloud APIs...${NC}"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    --quiet

echo -e "${GREEN}✅ APIs enabled${NC}"
echo ""

# Deploy minimal service first (no build required)
echo -e "${GREEN}2️⃣ Deploying minimal service (no local build)...${NC}"
gcloud run deploy $SERVICE_NAME \
    --image=gcr.io/cloudrun/hello \
    --platform=managed \
    --region=$REGION \
    --allow-unauthenticated \
    --memory=1Gi \
    --cpu=1 \
    --project=$PROJECT_ID \
    --quiet

echo -e "${GREEN}✅ Minimal service deployed${NC}"
echo ""

# Get the service URL
echo -e "${GREEN}3️⃣ Getting service URL...${NC}"
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)" --project=$PROJECT_ID)

echo -e "${GREEN}✅ Service is live!${NC}"
echo ""
echo "=================================="
echo -e "🌐 Service URL: ${BLUE}$SERVICE_URL${NC}"
echo -e "🔍 Test it: ${BLUE}curl $SERVICE_URL${NC}"
echo "=================================="
echo ""

# Test the deployment
echo -e "${GREEN}4️⃣ Testing the deployment...${NC}"
if curl -s "$SERVICE_URL" > /dev/null; then
    echo -e "${GREEN}✅ Service is responding${NC}"
else
    echo -e "${RED}⚠️ Service might be starting up (try again in a moment)${NC}"
fi
echo ""

# Create update script for later
cat > update-service.sh << EOF
#!/bin/bash
# Use this script to update your service with actual code later

echo "🔄 Updating service with your LyoBackend code..."

# Option 1: Build in Google Cloud (recommended)
echo "Building in Google Cloud (safe, no local build)..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Update the service
gcloud run deploy $SERVICE_NAME \\
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \\
    --region $REGION \\
    --allow-unauthenticated \\
    --memory 2Gi \\
    --cpu 2 \\
    --set-env-vars="ENVIRONMENT=production"

echo "✅ Service updated!"
EOF

chmod +x update-service.sh

echo -e "${GREEN}📝 Next Steps:${NC}"
echo "1. Your minimal service is running at: $SERVICE_URL"
echo "2. To update with your actual LyoBackend code, run: ./update-service.sh"
echo "3. Or build in Cloud Shell to avoid local system stress"
echo ""
echo -e "${YELLOW}💡 This approach prevents computer crashes by:${NC}"
echo "   - No local Docker builds"
echo "   - No heavy AI model downloads"
echo "   - Uses Google's infrastructure for building"
echo ""
echo -e "${GREEN}🎉 Deployment complete! Your service is live and ready.${NC}"
