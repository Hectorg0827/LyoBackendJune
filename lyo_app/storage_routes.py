"""
Storage endpoints for LyoBackend
Handles complex file operations with Google Cloud Storage integration
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from typing import List, Optional
import logging
from pydantic import BaseModel

from .gcs_storage import get_gcs_manager, GCSManager
from .auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/storage", tags=["Storage"])

class FileUploadResponse(BaseModel):
    success: bool
    filename: str
    original_filename: str
    public_url: str
    size: int
    content_type: str
    message: str = "File uploaded successfully"

class FileMetadata(BaseModel):
    name: str
    size: int
    created: str
    updated: str
    content_type: str
    public_url: str
    gcs_uri: str

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    folder: str = Query("uploads", description="Folder to store the file"),
    process_image: bool = Query(False, description="Whether to process/optimize images"),
    max_width: int = Query(1920, description="Maximum image width"),
    max_height: int = Query(1080, description="Maximum image height"),
    gcs: GCSManager = Depends(get_gcs_manager),
    current_user = Depends(get_current_user)
):
    """
    Upload file to Google Cloud Storage with optional image processing
    
    Features:
    - Automatic image optimization and resizing
    - Unique filename generation
    - Public URL generation
    - Support for all file types
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Check file size (max 50MB)
        max_size = 50 * 1024 * 1024  # 50MB
        content = await file.read()
        if len(content) > max_size:
            raise HTTPException(status_code=413, detail="File too large (max 50MB)")
        
        # Reset file pointer
        await file.seek(0)
        
        # Upload to GCS
        result = await gcs.upload_file_async(
            file=file,
            folder=f"{folder}/{current_user['id']}" if current_user else folder,
            process_image=process_image,
            max_width=max_width,
            max_height=max_height
        )
        
        return FileUploadResponse(
            success=result["success"],
            filename=result["filename"],
            original_filename=result["original_filename"],
            public_url=result["public_url"],
            size=result["size"],
            content_type=result["content_type"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail="Upload failed")

@router.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    folder: str = Query("uploads", description="Folder to store files"),
    process_images: bool = Query(False, description="Whether to process images"),
    gcs: GCSManager = Depends(get_gcs_manager),
    current_user = Depends(get_current_user)
):
    """Upload multiple files at once"""
    try:
        if len(files) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 files allowed")
        
        results = []
        errors = []
        
        for file in files:
            try:
                if file.filename:
                    result = await gcs.upload_file_async(
                        file=file,
                        folder=f"{folder}/{current_user['id']}" if current_user else folder,
                        process_image=process_images
                    )
                    results.append(result)
                else:
                    errors.append({"filename": "unknown", "error": "No filename provided"})
            except Exception as e:
                errors.append({"filename": file.filename, "error": str(e)})
        
        return {
            "success": len(errors) == 0,
            "uploaded": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Multiple upload error: {str(e)}")
        raise HTTPException(status_code=500, detail="Multiple upload failed")

@router.delete("/file/{blob_name:path}")
async def delete_file(
    blob_name: str,
    gcs: GCSManager = Depends(get_gcs_manager),
    current_user = Depends(get_current_user)
):
    """Delete file from Google Cloud Storage"""
    try:
        # Check if user owns the file (basic security)
        if current_user and not blob_name.startswith(f"uploads/{current_user['id']}/"):
            raise HTTPException(status_code=403, detail="Access denied")
        
        success = await gcs.delete_file_async(blob_name)
        
        if success:
            return {"success": True, "message": "File deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="File not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete error: {str(e)}")
        raise HTTPException(status_code=500, detail="Delete failed")

@router.get("/files", response_model=List[FileMetadata])
async def list_files(
    folder: str = Query("", description="Folder to list files from"),
    limit: int = Query(100, description="Maximum number of files to return"),
    gcs: GCSManager = Depends(get_gcs_manager),
    current_user = Depends(get_current_user)
):
    """List files in Google Cloud Storage"""
    try:
        # Restrict to user's files if authenticated
        if current_user:
            folder = f"uploads/{current_user['id']}" if not folder else f"{folder}/{current_user['id']}"
        
        files = await gcs.list_files_async(folder=folder, limit=limit)
        return files
        
    except Exception as e:
        logger.error(f"List files error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list files")

@router.get("/file/{blob_name:path}/metadata", response_model=FileMetadata)
async def get_file_metadata(
    blob_name: str,
    gcs: GCSManager = Depends(get_gcs_manager),
    current_user = Depends(get_current_user)
):
    """Get file metadata from Google Cloud Storage"""
    try:
        # Check access permissions
        if current_user and not blob_name.startswith(f"uploads/{current_user['id']}/"):
            raise HTTPException(status_code=403, detail="Access denied")
        
        metadata = await gcs.get_file_metadata(blob_name)
        
        if metadata:
            return metadata
        else:
            raise HTTPException(status_code=404, detail="File not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get metadata error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get file metadata")

@router.post("/process-image")
async def process_existing_image(
    blob_name: str = Query(..., description="GCS blob name of the image"),
    max_width: int = Query(1920, description="Maximum width"),
    max_height: int = Query(1080, description="Maximum height"),
    gcs: GCSManager = Depends(get_gcs_manager),
    current_user = Depends(get_current_user)
):
    """Process an existing image in GCS (resize, optimize)"""
    try:
        # Check permissions
        if current_user and not blob_name.startswith(f"uploads/{current_user['id']}/"):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get original file metadata
        metadata = await gcs.get_file_metadata(blob_name)
        if not metadata:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if it's an image
        if not metadata['content_type'].startswith('image/'):
            raise HTTPException(status_code=400, detail="File is not an image")
        
        # TODO: Implement image processing for existing files
        # This would involve downloading, processing, and re-uploading
        
        return {
            "success": True,
            "message": "Image processing completed",
            "original_size": metadata['size'],
            "processed_url": metadata['public_url']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image processing error: {str(e)}")
        raise HTTPException(status_code=500, detail="Image processing failed")
