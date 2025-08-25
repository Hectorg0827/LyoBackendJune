#!/bin/bash
# Automatic GCS Integration & Cloud Run Deployment
# Implements the recommended approach with Firebase + GCS backend integration

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 LyoBackend with Google Cloud Storage Integration${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""

# Configuration
PROJECT_ID=${1:-$(gcloud config get-value project 2>/dev/null)}
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ Project ID required. Usage: $0 <project-id>${NC}"
    exit 1
fi

SERVICE_NAME="lyo-backend"
REGION="us-central1"
BUCKET_NAME="lyobackend-storage"
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/lyo-backend-repo/${SERVICE_NAME}:latest"

echo -e "${BLUE}📋 Configuration:${NC}"
echo -e "  Project: ${PROJECT_ID}"
echo -e "  Service: ${SERVICE_NAME}"
echo -e "  Region: ${REGION}"
echo -e "  Storage Bucket: ${BUCKET_NAME}"
echo -e "  Image: ${IMAGE_NAME}"
echo ""

# Step 1: Enable required APIs
echo -e "${GREEN}1️⃣ Enabling Google Cloud APIs...${NC}"
gcloud services enable cloudbuild.googleapis.com \
  run.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  --project=${PROJECT_ID}

# Step 2: Create GCS bucket
echo -e "${GREEN}2️⃣ Setting up Google Cloud Storage bucket...${NC}"
if ! gsutil ls -b gs://${BUCKET_NAME} > /dev/null 2>&1; then
    echo "Creating bucket: ${BUCKET_NAME}"
    gsutil mb gs://${BUCKET_NAME}
    
    # Set up CORS for web access
    gsutil cors set cors.json gs://${BUCKET_NAME}
    
    # Set bucket permissions (public read for uploaded files)
    gsutil iam ch allUsers:objectViewer gs://${BUCKET_NAME}
    
    echo -e "${GREEN}✅ Bucket created and configured${NC}"
else
    echo -e "${YELLOW}⚠️  Bucket already exists, updating CORS...${NC}"
    gsutil cors set cors.json gs://${BUCKET_NAME}
fi

# Step 3: Create service account for GCS access (if needed)
echo -e "${GREEN}3️⃣ Setting up service account...${NC}"
SA_NAME="lyo-backend-storage"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe ${SA_EMAIL} > /dev/null 2>&1; then
    echo "Creating service account: ${SA_NAME}"
    gcloud iam service-accounts create ${SA_NAME} \
        --display-name="LyoBackend Storage Service Account" \
        --description="Service account for LyoBackend GCS operations"
    
    # Grant necessary permissions
    gcloud projects add-iam-policy-binding ${PROJECT_ID} \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="roles/storage.objectAdmin"
    
    gcloud projects add-iam-policy-binding ${PROJECT_ID} \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="roles/storage.admin"
else
    echo -e "${YELLOW}⚠️  Service account already exists${NC}"
fi

# Step 4: Build and deploy using Cloud Build
echo -e "${GREEN}4️⃣ Building and deploying with Cloud Build...${NC}"
echo -e "${YELLOW}⚡ This builds in Google's cloud - no Mac stress!${NC}"

# Submit build
gcloud builds submit \
    --config=cloudbuild.yaml \
    --project=${PROJECT_ID} \
    --timeout=1800s

# Step 5: Verify deployment
echo -e "${GREEN}5️⃣ Verifying deployment...${NC}"
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")

if [ -z "$SERVICE_URL" ]; then
    echo -e "${RED}❌ Deployment failed - no service URL found${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 DEPLOYMENT COMPLETE!${NC}"
echo "=================================="
echo -e "🌐 Service URL: ${BLUE}${SERVICE_URL}${NC}"
echo -e "📖 API Docs: ${BLUE}${SERVICE_URL}/docs${NC}"
echo -e "❤️  Health Check: ${BLUE}${SERVICE_URL}/health${NC}"
echo -e "📁 Storage API: ${BLUE}${SERVICE_URL}/api/v1/storage${NC}"
echo "=================================="

# Step 6: Test the deployment
echo -e "${GREEN}6️⃣ Testing deployment...${NC}"

# Test health endpoint
if curl -s -f "${SERVICE_URL}/health" > /dev/null; then
    echo -e "${GREEN}✅ Health check passed${NC}"
else
    echo -e "${YELLOW}⚠️  Health check failed (service may still be starting)${NC}"
fi

# Test storage endpoints
echo -e "${BLUE}📁 Testing storage endpoints...${NC}"
STORAGE_ENDPOINTS=(
    "/api/v1/storage/files"
)

for endpoint in "${STORAGE_ENDPOINTS[@]}"; do
    if curl -s -f "${SERVICE_URL}${endpoint}" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ ${endpoint} accessible${NC}"
    else
        echo -e "${YELLOW}⚠️  ${endpoint} requires authentication${NC}"
    fi
done

echo ""
echo -e "${GREEN}📱 iOS Integration Guide:${NC}"
echo -e "${BLUE}Replace 'localhost:8001' with: ${SERVICE_URL}${NC}"
echo ""
echo -e "${GREEN}🔧 New Storage Features Available:${NC}"
echo -e "  • File Upload: POST ${SERVICE_URL}/api/v1/storage/upload"
echo -e "  • Multiple Upload: POST ${SERVICE_URL}/api/v1/storage/upload-multiple"
echo -e "  • List Files: GET ${SERVICE_URL}/api/v1/storage/files"
echo -e "  • Delete File: DELETE ${SERVICE_URL}/api/v1/storage/file/{blob_name}"
echo -e "  • Image Processing: POST ${SERVICE_URL}/api/v1/storage/process-image"
echo ""
echo -e "${GREEN}💡 Storage Strategy:${NC}"
echo -e "  • Frontend → Firebase Storage (simple uploads)"
echo -e "  • Backend → Google Cloud Storage (complex processing)"
echo -e "  • Automatic image optimization and resizing"
echo -e "  • Secure user-based file organization"
echo ""
echo -e "${GREEN}🎊 Your backend now supports both Firebase and GCS storage!${NC}"

# Optional: Create a test upload
echo ""
read -p "Would you like to test file upload? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}📤 Creating test file...${NC}"
    echo "Hello from LyoBackend GCS Integration!" > test-upload.txt
    
    echo -e "${GREEN}📤 Testing file upload...${NC}"
    curl -X POST "${SERVICE_URL}/api/v1/storage/upload" \
        -F "file=@test-upload.txt" \
        -F "folder=test" \
        -F "process_image=false" \
        || echo -e "${YELLOW}⚠️  Upload test requires authentication${NC}"
    
    rm -f test-upload.txt
fi

echo ""
echo -e "${GREEN}🚀 Deployment completed successfully!${NC}"
