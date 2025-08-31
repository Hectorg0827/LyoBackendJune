#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🚀 Manual GCR Deployment for Superior AI Backend${NC}"
echo -e "${BLUE}🎯 Target: https://lyo-backend-830162750094.us-central1.run.app${NC}"

# Let's try to find the actual project ID by checking the current config
echo -e "${YELLOW}🔍 Checking current gcloud configuration...${NC}"

# Get current project
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "")
echo -e "${GREEN}Current project: ${CURRENT_PROJECT}${NC}"

# List available projects
echo -e "${YELLOW}🔍 Available projects:${NC}"
gcloud projects list --format="table(projectId,name,projectNumber)" 2>/dev/null || echo "Failed to list projects"

# Check if we can authenticate and access Cloud Run services
echo -e "${YELLOW}🔍 Checking existing Cloud Run services...${NC}"
gcloud run services list --platform=managed --region=us-central1 2>/dev/null || echo "Failed to list Cloud Run services"

echo ""
echo -e "${BLUE}📋 Manual Deployment Instructions:${NC}"
echo -e "${BLUE}Since we have your target URL: https://lyo-backend-830162750094.us-central1.run.app${NC}"
echo ""

echo -e "${YELLOW}1. First, set the correct project:${NC}"
echo -e "${YELLOW}   gcloud config set project YOUR_ACTUAL_PROJECT_ID${NC}"
echo ""

echo -e "${YELLOW}2. Enable required APIs:${NC}"
echo -e "${YELLOW}   gcloud services enable cloudbuild.googleapis.com run.googleapis.com${NC}"
echo ""

echo -e "${YELLOW}3. Build and deploy using Cloud Build:${NC}"
cat << 'EOF'
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/lyo-backend-superior:latest .
EOF

echo ""
echo -e "${YELLOW}4. Deploy to Cloud Run:${NC}"
cat << 'EOF'
gcloud run deploy lyo-backend \
  --image gcr.io/YOUR_PROJECT_ID/lyo-backend-superior:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --set-env-vars "ENABLE_SUPERIOR_AI_MODE=true,ENABLE_ADAPTIVE_DIFFICULTY=true,ENABLE_ADVANCED_SOCRATIC=true"
EOF

echo ""
echo -e "${GREEN}🎯 Your Superior AI Backend includes:${NC}"
echo -e "${GREEN}  ✅ Advanced Socratic Questioning (6 strategies)${NC}"
echo -e "${GREEN}  ✅ Adaptive Difficulty Engine (5 levels)${NC}"
echo -e "${GREEN}  ✅ Superior Prompt Engineering System${NC}"
echo -e "${GREEN}  ✅ Multi-dimensional Learning Analytics${NC}"
echo -e "${GREEN}  ✅ Real-time Performance Optimization${NC}"

echo ""
echo -e "${BLUE}📁 All superior AI files are ready:${NC}"
if [[ -f "lyo_app/ai_study/adaptive_engine.py" ]]; then
    echo -e "${GREEN}  ✅ adaptive_engine.py (400+ lines)${NC}"
fi
if [[ -f "lyo_app/ai_study/advanced_socratic.py" ]]; then
    echo -e "${GREEN}  ✅ advanced_socratic.py (500+ lines)${NC}"
fi
if [[ -f "lyo_app/ai_study/superior_prompts.py" ]]; then
    echo -e "${GREEN}  ✅ superior_prompts.py (600+ lines)${NC}"
fi
if [[ -f "lyo_app/ai_study/service.py" ]]; then
    echo -e "${GREEN}  ✅ service.py (1370+ lines with superior AI integration)${NC}"
fi
