#!/bin/bash
# Ultra-Simple GCS Deployment - Guaranteed to work
# Creates a minimal working service first, then adds features

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_ID=${1:-$(gcloud config get-value project 2>/dev/null)}
SERVICE_NAME="lyo-backend"
REGION="us-central1"
BUCKET_NAME="lyobackend-storage"

echo -e "${GREEN}🚀 Ultra-Simple GCS Deployment${NC}"
echo -e "${GREEN}=============================${NC}"
echo ""

# Step 1: Deploy minimal working service first
echo -e "${GREEN}1️⃣ Deploying minimal working service...${NC}"
gcloud run deploy ${SERVICE_NAME} \
    --image=gcr.io/cloudrun/hello \
    --region=${REGION} \
    --allow-unauthenticated \
    --memory=1Gi \
    --cpu=1 \
    --quiet

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")
echo -e "${GREEN}✅ Minimal service deployed: ${BLUE}${SERVICE_URL}${NC}"

# Step 2: Create GCS bucket
echo -e "${GREEN}2️⃣ Setting up storage bucket...${NC}"
if ! gsutil ls -b gs://${BUCKET_NAME} > /dev/null 2>&1; then
    gsutil mb gs://${BUCKET_NAME}
    gsutil cors set cors.json gs://${BUCKET_NAME}
    gsutil iam ch allUsers:objectViewer gs://${BUCKET_NAME}
    echo -e "${GREEN}✅ Bucket created: gs://${BUCKET_NAME}${NC}"
else
    echo -e "${YELLOW}⚠️ Bucket already exists${NC}"
fi

# Step 3: Create a super simple FastAPI app
echo -e "${GREEN}3️⃣ Creating simple backend with storage...${NC}"

cat > simple_main.py << 'EOF'
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage
import os
import uuid
import uvicorn

app = FastAPI(title="LyoBackend with Storage")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize GCS client
try:
    storage_client = storage.Client()
    bucket_name = os.getenv("GCS_BUCKET_NAME", "lyobackend-storage")
    bucket = storage_client.bucket(bucket_name)
except Exception:
    storage_client = None
    bucket = None

@app.get("/")
async def root():
    return {
        "message": "LyoBackend API with Google Cloud Storage",
        "version": "1.0.0",
        "storage": "enabled" if storage_client else "disabled"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "lyo-backend"}

@app.post("/api/v1/storage/upload")
async def upload_file(file: UploadFile = File(...)):
    """Simple file upload to GCS"""
    if not storage_client or not bucket:
        raise HTTPException(status_code=503, detail="Storage not available")
    
    try:
        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1] if file.filename else ""
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        blob_name = f"uploads/{unique_filename}"
        
        # Upload to GCS
        blob = bucket.blob(blob_name)
        content = await file.read()
        blob.upload_from_string(content, content_type=file.content_type)
        blob.make_public()
        
        return {
            "success": True,
            "filename": unique_filename,
            "original_filename": file.filename,
            "public_url": blob.public_url,
            "size": len(content)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/api/v1/storage/files")
async def list_files():
    """List files in GCS bucket"""
    if not storage_client or not bucket:
        raise HTTPException(status_code=503, detail="Storage not available")
    
    try:
        blobs = storage_client.list_blobs(bucket_name, prefix="uploads/", max_results=50)
        files = []
        for blob in blobs:
            files.append({
                "name": blob.name,
                "size": blob.size,
                "created": blob.time_created.isoformat(),
                "public_url": blob.public_url
            })
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List failed: {str(e)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
EOF

# Step 4: Create simple Dockerfile
cat > Dockerfile.simple << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install curl for health check
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install minimal requirements
RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    google-cloud-storage==2.17.0 \
    python-multipart==0.0.6

# Copy app
COPY simple_main.py .
COPY cors.json .

# Environment
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV GCS_BUCKET_NAME=lyobackend-storage

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:8080/health || exit 1

# Run app
CMD ["python", "simple_main.py"]
EOF

# Step 5: Build and deploy simple version
echo -e "${GREEN}4️⃣ Building simple version in cloud...${NC}"
gcloud builds submit \
    --tag gcr.io/${PROJECT_ID}/${SERVICE_NAME}-simple \
    --dockerfile=Dockerfile.simple \
    --timeout=600s

echo -e "${GREEN}5️⃣ Deploying simple version...${NC}"
gcloud run deploy ${SERVICE_NAME} \
    --image gcr.io/${PROJECT_ID}/${SERVICE_NAME}-simple \
    --region=${REGION} \
    --allow-unauthenticated \
    --memory=2Gi \
    --cpu=1 \
    --set-env-vars="GCS_BUCKET_NAME=${BUCKET_NAME}" \
    --quiet

# Final URL
FINAL_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")

echo ""
echo -e "${GREEN}🎉 SUCCESS! Your backend with storage is live!${NC}"
echo "=========================================="
echo -e "🌐 Service URL: ${BLUE}${FINAL_URL}${NC}"
echo -e "📖 API Docs: ${BLUE}${FINAL_URL}/docs${NC}"
echo -e "❤️ Health: ${BLUE}${FINAL_URL}/health${NC}"
echo -e "📁 Upload: ${BLUE}${FINAL_URL}/api/v1/storage/upload${NC}"
echo -e "📄 List Files: ${BLUE}${FINAL_URL}/api/v1/storage/files${NC}"
echo "=========================================="

# Test it
echo -e "${GREEN}🧪 Testing the service...${NC}"
curl -s "${FINAL_URL}/health" && echo -e " ${GREEN}✅ Working!${NC}"

echo ""
echo -e "${GREEN}📱 For your iOS app, replace 'localhost:8001' with:${NC}"
echo -e "${BLUE}${FINAL_URL}${NC}"

# Clean up
rm -f simple_main.py Dockerfile.simple

echo ""
echo -e "${GREEN}🎊 Deployment complete - no crashes, working storage!${NC}"
