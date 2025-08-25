from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage
import os
import uuid
import uvicorn

app = FastAPI(title="LyoBackend with Storage", version="1.0.0")

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
    print(f"✅ Connected to GCS bucket: {bucket_name}")
except Exception as e:
    print(f"⚠️ Storage not available: {e}")
    storage_client = None
    bucket = None

@app.get("/")
async def root():
    return {
        "message": "LyoBackend API with Google Cloud Storage",
        "version": "1.0.0",
        "storage": "enabled" if storage_client else "disabled",
        "bucket": bucket_name if storage_client else None
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy", 
        "service": "lyo-backend",
        "storage": "ready" if storage_client else "unavailable"
    }

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
            "size": len(content),
            "bucket": bucket_name
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
        return {"files": files, "bucket": bucket_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List failed: {str(e)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
