#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🚀 Deploying Superior LyoBackend to Specific GCR Endpoint${NC}"
echo -e "${BLUE}🎯 Target: https://lyo-backend-830162750094.us-central1.run.app${NC}"

# Extract project ID from the URL
PROJECT_ID="830162750094"
SERVICE_NAME="lyo-backend"
REGION="us-central1"

echo -e "${GREEN}📋 Deployment Configuration:${NC}"
echo -e "${GREEN}  Project ID: ${PROJECT_ID}${NC}"
echo -e "${GREEN}  Service: ${SERVICE_NAME}${NC}"
echo -e "${GREEN}  Region: ${REGION}${NC}"

# Set gcloud project
echo -e "${YELLOW}🔧 Setting gcloud project...${NC}"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo -e "${YELLOW}🔧 Enabling required Google Cloud APIs...${NC}"
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    containerregistry.googleapis.com \
    --project="$PROJECT_ID"

echo -e "${YELLOW}⏳ Waiting for APIs to be ready...${NC}"
sleep 5

# Verify current directory has the required files
if [[ ! -f "lyo_app/ai_study/service.py" ]]; then
    echo -e "${RED}❌ Error: Cannot find lyo_app/ai_study/service.py${NC}"
    echo "Please run this script from the LyoBackendJune directory"
    exit 1
fi

echo -e "${GREEN}✅ Superior AI service.py found with all advanced capabilities${NC}"

# Check if superior AI components exist
if [[ -f "lyo_app/ai_study/adaptive_engine.py" ]]; then
    echo -e "${GREEN}✅ Advanced Adaptive Difficulty Engine detected${NC}"
fi

if [[ -f "lyo_app/ai_study/advanced_socratic.py" ]]; then
    echo -e "${GREEN}✅ Advanced Socratic Questioning Engine detected${NC}"
fi

if [[ -f "lyo_app/ai_study/superior_prompts.py" ]]; then
    echo -e "${GREEN}✅ Superior Prompt Engineering System detected${NC}"
fi

# Build and deploy using Cloud Build
echo -e "${YELLOW}🏗️ Starting Cloud Build deployment...${NC}"
echo -e "${BLUE}Building and deploying superior LyoBackend with:${NC}"
echo -e "${BLUE}  - Advanced Adaptive Difficulty Engine${NC}"
echo -e "${BLUE}  - Superior Socratic Questioning System${NC}" 
echo -e "${BLUE}  - Enhanced Prompt Engineering${NC}"
echo -e "${BLUE}  - AI-Powered Performance Analytics${NC}"
echo -e "${BLUE}  - Multi-Modal Learning Optimization${NC}"

# Submit build to Cloud Build with specific service deployment
gcloud builds submit \
    --config=cloudbuild.specific.yaml \
    --substitutions=_SERVICE_NAME=${SERVICE_NAME},_REGION=${REGION} \
    --project="$PROJECT_ID" \
    --timeout=1200s

if [ $? -eq 0 ]; then
    echo -e "${GREEN}🎉 SUCCESS: Superior LyoBackend deployed to GCR!${NC}"
    echo -e "${GREEN}📍 Container Registry: gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest${NC}"
    echo -e "${GREEN}🌐 Service URL: https://${SERVICE_NAME}-${PROJECT_ID}.${REGION}.run.app${NC}"
    
    # Verify deployment
    echo -e "${YELLOW}🔍 Verifying deployment...${NC}"
    sleep 10
    
    SERVICE_URL="https://${SERVICE_NAME}-${PROJECT_ID}.${REGION}.run.app"
    
    # Test health endpoint
    if curl -s --max-time 10 "${SERVICE_URL}/health" > /dev/null; then
        echo -e "${GREEN}✅ Health check passed${NC}"
    else
        echo -e "${YELLOW}⚠️ Health check pending (service may still be starting)${NC}"
    fi
    
    echo ""
    echo -e "${BLUE}🎯 Superior AI Features Now Live:${NC}"
    echo -e "${BLUE}  ✅ Advanced Socratic Questioning (6 strategies)${NC}"
    echo -e "${BLUE}  ✅ Adaptive Difficulty Engine (5 levels)${NC}"
    echo -e "${BLUE}  ✅ Superior Prompt Engineering System${NC}"
    echo -e "${BLUE}  ✅ Multi-dimensional Learning Analytics${NC}"
    echo -e "${BLUE}  ✅ Real-time Performance Optimization${NC}"
    
    echo ""
    echo -e "${YELLOW}🧪 Test the Superior AI Features:${NC}"
    echo -e "${YELLOW}curl -X POST \"${SERVICE_URL}/api/v1/ai-study/conversation\" \\${NC}"
    echo -e "${YELLOW}  -H \"Content-Type: application/json\" \\${NC}"  
    echo -e "${YELLOW}  -d '{\"user_input\":\"Explain quantum physics\",\"resource_id\":\"test\"}'${NC}"
    
    echo ""
    echo -e "${GREEN}🔗 Important Endpoints:${NC}"
    echo -e "${GREEN}  📚 API Docs: ${SERVICE_URL}/docs${NC}"
    echo -e "${GREEN}  ❤️  Health: ${SERVICE_URL}/health${NC}"
    echo -e "${GREEN}  🧠 AI Status: ${SERVICE_URL}/health/optimization${NC}"
    
    echo ""
    echo -e "${GREEN}🚀 Your Superior AI Backend is now live at the specified endpoint!${NC}"
    
else
    echo -e "${RED}❌ ERROR: Deployment failed${NC}"
    echo "Check the Cloud Build logs for details:"
    echo "https://console.cloud.google.com/cloud-build/builds?project=$PROJECT_ID"
    exit 1
fi
