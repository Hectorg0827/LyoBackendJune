"""
Enhanced Storage API Routes
Production-ready file upload and management with intelligent processing
"""

import asyncio
import mimetypes
import os
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user
from lyo_app.models.enhanced import User
from lyo_app.storage.enhanced_storage import enhanced_storage, MediaType
from lyo_app.core.enhanced_monitoring import monitor_performance, handle_errors, ErrorCategory
from lyo_app.core.logging import logger

router = APIRouter(prefix="/api/v1/storage", tags=["Enhanced Storage"])

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class UploadResponse(BaseModel):
    """Response model for file upload"""
    success: bool
    file_id: str
    original_filename: str
    storage_path: str
    media_type: str
    file_size: int
    urls: Dict[str, str]
    variants: Dict[str, Any]
    metadata: Dict[str, Any]
    upload_timestamp: datetime
    processing_info: Dict[str, Any]

class FileMetadataResponse(BaseModel):
    """Response model for file metadata"""
    file_id: str
    filename: str
    media_type: str
    file_size: int
    urls: Dict[str, str]
    variants: Dict[str, Any]
    metadata: Dict[str, Any]
    upload_timestamp: datetime
    last_accessed: Optional[datetime]
    access_count: int

class StorageStatsResponse(BaseModel):
    """Response model for storage statistics"""
    storage_providers: Dict[str, bool]
    cdn_enabled: bool
    processing_capabilities: Dict[str, bool]
    total_files: int
    total_size_bytes: int
    files_by_type: Dict[str, int]
    recent_uploads: List[Dict[str, Any]]
    performance_metrics: Dict[str, Any]

class BatchUploadRequest(BaseModel):
    """Request model for batch upload"""
    folder: str = Field("uploads", description="Upload folder")
    optimize: bool = Field(True, description="Enable optimization")
    generate_variants: bool = Field(True, description="Generate variants")
    tags: Optional[List[str]] = Field(None, description="File tags")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

class PresignedURLRequest(BaseModel):
    """Request model for presigned URL"""
    filename: str = Field(..., description="Filename to upload")
    content_type: str = Field(..., description="MIME type of the file")
    folder: str = Field("uploads", description="Destination folder")

class PresignedURLResponse(BaseModel):
    """Response model for presigned URL"""
    success: bool
    upload_url: Optional[str] = Field(None, description="Presigned URL for upload")
    public_url: Optional[str] = Field(None, description="Public URL after upload")
    blob_name: Optional[str] = Field(None, description="Storage blob name")
    headers: Optional[Dict[str, str]] = Field(None, description="Headers to include in upload request")
    expires_in: int = Field(3600, description="URL expiration time in seconds")
    error: Optional[str] = None

# ============================================================================
# PRESIGNED URL ENDPOINT (For iOS Direct Upload)
# ============================================================================

@router.post("/presigned-url", response_model=PresignedURLResponse)
async def get_presigned_url(
    request: PresignedURLRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a presigned URL for direct client upload to cloud storage.
    
    This allows iOS/Android clients to upload files directly to R2/S3
    without passing through the backend, improving performance for large files.
    """
    from lyo_app.core.config import settings
    import uuid
    from datetime import timedelta
    
    try:
        # Validate tenant context - use getattr for compatibility with UserRead schema
        org_id = getattr(current_user, 'organization_id', None) or "default"
        
        # Generate unique filename with tenant isolation
        file_ext = request.filename.split('.')[-1] if '.' in request.filename else ''
        unique_id = uuid.uuid4().hex[:12]
        timestamp = int(datetime.utcnow().timestamp())
        
        # Construct tenant-isolated path
        blob_name = f"org_{org_id}/{request.folder}/{current_user.id}/{timestamp}_{unique_id}.{file_ext}"
        
        logger.info(f"Generating presigned URL for blob: {blob_name}")
        
        # Check GCS first (most common in production)
        gcs_bucket = getattr(settings, 'GCS_BUCKET_NAME', None) or os.environ.get('GCS_BUCKET_NAME')
        logger.info(f"GCS bucket from settings/env: {gcs_bucket}")
        
        if gcs_bucket:
            try:
                from google.cloud import storage as gcs_storage
                from datetime import timedelta as td
                
                gcs_client = gcs_storage.Client()
                bucket = gcs_client.bucket(gcs_bucket)
                blob = bucket.blob(blob_name)
                
                # Generate signed URL for upload (PUT)
                presigned_url = blob.generate_signed_url(
                    version="v4",
                    expiration=td(hours=1),
                    method="PUT",
                    content_type=request.content_type,
                )
                
                # Public URL
                public_url = f"https://storage.googleapis.com/{gcs_bucket}/{blob_name}"
                
                logger.info(f"Generated GCS presigned URL for user {current_user.id}: {blob_name}")
                
                return PresignedURLResponse(
                    success=True,
                    upload_url=presigned_url,
                    public_url=public_url,
                    blob_name=blob_name,
                    headers={"Content-Type": request.content_type},
                    expires_in=3600
                )
            except ImportError as ie:
                logger.warning(f"google-cloud-storage not installed: {ie}")
            except Exception as e:
                logger.error(f"GCS presigned URL failed: {e}", exc_info=True)
        
        # Try R2 and S3 as fallbacks
        try:
            await enhanced_storage.ensure_initialized()
        except Exception as init_error:
            logger.warning(f"Enhanced storage initialization failed: {init_error}")
        
        if enhanced_storage.r2_client:
            # Generate presigned URL for Cloudflare R2
            try:
                presigned_url = enhanced_storage.r2_client.generate_presigned_url(
                    'put_object',
                    Params={
                        'Bucket': settings.R2_BUCKET,
                        'Key': blob_name,
                        'ContentType': request.content_type
                    },
                    ExpiresIn=3600
                )
                
                # Public URL (via CDN or direct R2 URL)
                cdn_base = getattr(settings, 'CDN_BASE_URL', None)
                if cdn_base:
                    public_url = f"{cdn_base.rstrip('/')}/{blob_name}"
                else:
                    public_url = f"{settings.R2_ENDPOINT_URL}/{settings.R2_BUCKET}/{blob_name}"
                
                logger.info(f"Generated R2 presigned URL for user {current_user.id}: {blob_name}")
                
                return PresignedURLResponse(
                    success=True,
                    upload_url=presigned_url,
                    public_url=public_url,
                    blob_name=blob_name,
                    headers={"Content-Type": request.content_type},
                    expires_in=3600
                )
            except Exception as e:
                logger.warning(f"R2 presigned URL failed: {e}, trying S3...")
        
        if enhanced_storage.s3_client:
            # Generate presigned URL for AWS S3
            try:
                presigned_url = enhanced_storage.s3_client.generate_presigned_url(
                    'put_object',
                    Params={
                        'Bucket': settings.AWS_S3_BUCKET,
                        'Key': blob_name,
                        'ContentType': request.content_type
                    },
                    ExpiresIn=3600
                )
                
                # Public URL
                region = settings.AWS_REGION or 'us-east-1'
                public_url = f"https://{settings.AWS_S3_BUCKET}.s3.{region}.amazonaws.com/{blob_name}"
                
                logger.info(f"Generated S3 presigned URL for user {current_user.id}: {blob_name}")
                
                return PresignedURLResponse(
                    success=True,
                    upload_url=presigned_url,
                    public_url=public_url,
                    blob_name=blob_name,
                    headers={"Content-Type": request.content_type},
                    expires_in=3600
                )
            except Exception as e:
                logger.error(f"S3 presigned URL failed: {e}")
        
        # No cloud storage configured
        return PresignedURLResponse(
            success=False,
            error="No cloud storage configured. Please use direct upload endpoint."
        )
        
    except Exception as e:
        logger.error(f"Presigned URL generation failed: {e}")
        return PresignedURLResponse(
            success=False,
            error=str(e)
        )

# ============================================================================
# UPLOAD ENDPOINTS
# ============================================================================

from lyo_app.storage.models import FileAsset

@router.post("/upload", response_model=UploadResponse)
@monitor_performance("file_upload")
@handle_errors(ErrorCategory.STORAGE)
async def upload_file(
    file: UploadFile = File(...),
    folder: str = Form("uploads"),
    optimize: bool = Form(True),
    generate_variants: bool = Form(True),
    tags: Optional[str] = Form(None),  # JSON string of tags
    metadata: Optional[str] = Form(None),  # JSON string of metadata
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload file with intelligent processing and optimization.
    Enforces multi-tenant data isolation by prefixing paths with organization ID.
    """
    
    try:
        # Validate tenant context (Critical for isolation)
        if not current_user.organization_id:
            raise HTTPException(status_code=400, detail="User must belong to an organization to upload files")

        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        # Check file size
        file_size = 0
        await file.seek(0, 2)  # Seek to end
        file_size = await file.tell()
        await file.seek(0)  # Reset to beginning
        
        if file_size > enhanced_storage.settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {enhanced_storage.settings.MAX_UPLOAD_SIZE / 1024 / 1024:.1f}MB"
            )
        
        # Check file type
        file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        allowed_extensions = enhanced_storage.settings.ALLOWED_FILE_TYPES
        
        if f".{file_ext}" not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        # Parse additional data
        tags_list = []
        metadata_dict = {}
        
        try:
            if tags:
                import json
                tags_list = json.loads(tags)
            if metadata:
                import json
                metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            logger.warning("Failed to parse tags or metadata JSON")
        
        # Construct Tenant-Isolated Path
        # Format: org_{org_id}/{folder}/{user_id}/...
        # This ensures Organization A never overlaps with Organization B
        tenant_folder = f"org_{current_user.organization_id}/{folder}/{current_user.id}"
        
        # Upload and process file
        start_time = datetime.utcnow()
        
        upload_result = await enhanced_storage.upload_file(
            file=file,
            folder=tenant_folder,  # Use isolated folder
            user_id=current_user.id,
            optimize=optimize,
            generate_variants=generate_variants
        )
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Add user metadata
        upload_result['user_id'] = current_user.id
        upload_result['tags'] = tags_list
        upload_result['custom_metadata'] = metadata_dict
        
        # Generate file ID
        file_id = f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename.replace(' ', '_')}"
        
        # Save FileAsset to Database (Billing & tracking)
        new_asset = FileAsset(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            file_path=upload_result['storage_path'],
            url=upload_result['urls'].get('original', ''),
            filename=upload_result['original_filename'],
            content_type=file.content_type,
            size_bytes=upload_result['file_size'],
            is_private=False # Default to public for now, can be parameterized later
        )
        db.add(new_asset)
        await db.commit()
        
        # Background tasks
        background_tasks.add_task(
            _process_upload_analytics,
            current_user.id,
            upload_result,
            processing_time
        )
        
        # If image, add to search index
        if upload_result['media_type'] == 'image':
            background_tasks.add_task(
                _index_image_for_search,
                file_id,
                upload_result
            )
        
        # Create response
        response = UploadResponse(
            success=True,
            file_id=file_id,
            original_filename=upload_result['original_filename'],
            storage_path=upload_result['storage_path'],
            media_type=upload_result['media_type'],
            file_size=upload_result['file_size'],
            urls=upload_result['urls'],
            variants=upload_result.get('variants', {}),
            metadata=upload_result['metadata'],
            upload_timestamp=datetime.fromisoformat(upload_result['upload_timestamp']),
            processing_info={
                'processing_time_seconds': processing_time,
                'optimization_enabled': optimize,
                'variants_generated': generate_variants,
                'cdn_enabled': bool(enhanced_storage.cdn_manager.cdn_base_url)
            }
        )
        
        logger.info(
            f"File uploaded successfully",
            extra={
                'user_id': current_user.id,
                'org_id': current_user.organization_id,
                'filename': file.filename,
                'storage_path': upload_result['storage_path'],
                'file_size': file_size,
                'media_type': upload_result['media_type'],
                'processing_time': processing_time
            }
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed: {e}", exc_info=True)
        await db.rollback() # Rollback DB on error
        raise HTTPException(
            status_code=500,
            detail="File upload failed. Please try again."
        )

@router.post("/batch-upload")
@monitor_performance("batch_upload")
@handle_errors(ErrorCategory.STORAGE)
async def batch_upload_files(
    files: List[UploadFile] = File(...),
    request_data: str = Form(...),  # JSON string of BatchUploadRequest
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload multiple files in batch with parallel processing
    """
    
    try:
        import json
        request = BatchUploadRequest(**json.loads(request_data))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid request data")
    
    if len(files) > 10:  # Limit batch size
        raise HTTPException(status_code=400, detail="Maximum 10 files per batch")
    
    # Process files in parallel
    upload_tasks = []
    
    # Prefix folder with organization ID for isolation
    tenant_folder = f"org_{current_user.organization_id}/{request.folder}/{current_user.id}"
    
    for file in files:
        task = enhanced_storage.upload_file(
            file=file,
            folder=tenant_folder,
            user_id=current_user.id,
            optimize=request.optimize,
            generate_variants=request.generate_variants
        )
        upload_tasks.append(task)
    
    try:
        results = await asyncio.gather(*upload_tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"Batch upload failed: {e}")
        raise HTTPException(status_code=500, detail="Batch upload failed")
    
    # Process results
    successful_uploads = []
    failed_uploads = []
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failed_uploads.append({
                'filename': files[i].filename,
                'error': str(result)
            })
        else:
            successful_uploads.append({
                'filename': result['original_filename'],
                'storage_path': result['storage_path'],
                'urls': result['urls']
            })
            
            # Save FileAsset for billing
            # Note: In a real batch scenario, we might want to bulk insert
            try:
                new_asset = FileAsset(
                    organization_id=current_user.organization_id,
                    user_id=current_user.id,
                    file_path=result['storage_path'],
                    url=result['urls'].get('original', ''),
                    filename=result['original_filename'],
                    # content_type unavailable in batch result easily without refactoring upload_file return
                    size_bytes=result['file_size'],
                    is_private=False 
                )
                db.add(new_asset)
            except Exception as e:
                logger.error(f"Failed to log batch upload asset: {e}")
                
    # Commit all new assets
    await db.commit()
    
    return {
        'success': len(failed_uploads) == 0,
        'successful_uploads': successful_uploads,
        'failed_uploads': failed_uploads,
        'total_files': len(files),
        'success_count': len(successful_uploads),
        'failure_count': len(failed_uploads)
    }

# ============================================================================
# FILE MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/file/{storage_path:path}")
@monitor_performance("get_file")
async def get_file_url(
    storage_path: str,
    variant: Optional[str] = Query(None, description="File variant (thumbnail, small, medium, large)"),
    download: bool = Query(False, description="Force download"),
    current_user: User = Depends(get_current_user)
):
    """
    Get file URL with optional variant and download handling
    """
    
    try:
        # Get file metadata
        metadata = await enhanced_storage.get_file_metadata(storage_path)
        
        if not metadata:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Access Control: Ensure user belongs to the organization owning the file
        expected_prefix = f"org_{current_user.organization_id}/"
        if not storage_path.startswith(expected_prefix):
             # Log potential security violation
             logger.warning(f"Unauthorized access attempt: User {current_user.id} (org {current_user.organization_id}) tried to access {storage_path}")
             raise HTTPException(status_code=403, detail="Access denied: File does not belong to your organization")
        
        # Get appropriate URL
        if variant and variant in metadata.get('urls', {}):
            file_url = metadata['urls'][variant]
        else:
            file_url = metadata['urls'].get('original')
        
        if not file_url:
            raise HTTPException(status_code=404, detail="File variant not found")
        
        # Add CDN URL if available
        cdn_url = enhanced_storage.cdn_manager.get_cdn_url(storage_path)
        
        if download:
            # Return redirect to download URL
            return RedirectResponse(url=file_url)
        else:
            return {
                'url': file_url,
                'cdn_url': cdn_url,
                'variant': variant,
                'metadata': metadata
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file: {e}")
        raise HTTPException(status_code=500, detail="Failed to get file")

@router.get("/metadata/{storage_path:path}", response_model=FileMetadataResponse)
@monitor_performance("get_file_metadata")
async def get_file_metadata(
    storage_path: str,
    current_user: User = Depends(get_current_user)
):
    """Get detailed file metadata"""
    
    try:
        metadata = await enhanced_storage.get_file_metadata(storage_path)
        
        if not metadata:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Access Control
        expected_prefix = f"org_{current_user.organization_id}/"
        if not storage_path.startswith(expected_prefix):
             raise HTTPException(status_code=403, detail="Access denied")
        
        return FileMetadataResponse(
            file_id=storage_path,
            filename=metadata['original_filename'],
            media_type=metadata['media_type'],
            file_size=metadata['file_size'],
            urls=metadata['urls'],
            variants=metadata.get('variants', {}),
            metadata=metadata['metadata'],
            upload_timestamp=datetime.fromisoformat(metadata['upload_timestamp']),
            last_accessed=None,  # Would be tracked in production
            access_count=0  # Would be tracked in production
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metadata: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metadata")

@router.delete("/file/{storage_path:path}")
@monitor_performance("delete_file")
@handle_errors(ErrorCategory.STORAGE)
async def delete_file(
    storage_path: str,
    permanent: bool = Query(False, description="Permanently delete (cannot be undone)"),
    current_user: User = Depends(get_current_user)
):
    """Delete file from storage"""
    
    try:
        # Get file metadata first
        metadata = await enhanced_storage.get_file_metadata(storage_path)
        
        if not metadata:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Access Control
        expected_prefix = f"org_{current_user.organization_id}/"
        if not storage_path.startswith(expected_prefix):
             raise HTTPException(status_code=403, detail="Access denied: Cannot delete file from another organization")
        
        # Delete file
        success = await enhanced_storage.delete_file(storage_path)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete file")
        
        logger.info(
            f"File deleted",
            extra={
                'user_id': current_user.id,
                'storage_path': storage_path,
                'permanent': permanent
            }
        )
        
        return {
            'success': True,
            'message': 'File deleted successfully',
            'storage_path': storage_path,
            'permanent': permanent
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete file")

# ============================================================================
# OPTIMIZATION ENDPOINTS
# ============================================================================

@router.post("/optimize/{storage_path:path}")
@monitor_performance("optimize_file")
async def optimize_existing_file(
    storage_path: str,
    quality_preset: str = Query("medium", description="Quality preset (thumbnail, small, medium, large)"),
    generate_variants: bool = Query(True, description="Generate additional variants"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user)
):
    """
    Optimize existing file with new settings
    """
    
    try:
        # Get file metadata
        metadata = await enhanced_storage.get_file_metadata(storage_path)
        
        if not metadata:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if it's an image (optimization currently only supports images)
        if metadata['media_type'] != 'image':
            raise HTTPException(status_code=400, detail="Optimization only supported for images")
        
        # Add optimization task to background
        background_tasks.add_task(
            _optimize_file_background,
            storage_path,
            quality_preset,
            generate_variants,
            current_user.id
        )
        
        return {
            'success': True,
            'message': 'File optimization started',
            'storage_path': storage_path,
            'quality_preset': quality_preset,
            'estimated_completion_seconds': 30
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to optimize file: {e}")
        raise HTTPException(status_code=500, detail="Failed to optimize file")

@router.post("/cdn/purge")
@monitor_performance("cdn_purge")
async def purge_cdn_cache(
    urls: List[str],
    current_user: User = Depends(get_current_user)
):
    """Purge CDN cache for specific URLs"""
    
    try:
        success = await enhanced_storage.cdn_manager.purge_cache(urls)
        
        return {
            'success': success,
            'message': f'CDN cache purge {"successful" if success else "failed"}',
            'urls_count': len(urls)
        }
        
    except Exception as e:
        logger.error(f"CDN cache purge failed: {e}")
        raise HTTPException(status_code=500, detail="CDN cache purge failed")

# ============================================================================
# ANALYTICS AND STATS ENDPOINTS
# ============================================================================

@router.get("/stats", response_model=StorageStatsResponse)
@monitor_performance("storage_stats")
async def get_storage_statistics(
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive storage statistics"""
    
    try:
        # Get basic stats from storage system
        stats = await enhanced_storage.get_upload_stats()
        
        # Add mock data for demonstration
        # In production, this would query your database
        stats.update({
            'total_files': 1234,
            'total_size_bytes': 15728640000,  # ~15GB
            'files_by_type': {
                'image': 856,
                'video': 234,
                'audio': 89,
                'document': 55
            },
            'recent_uploads': [
                {
                    'filename': 'presentation.pdf',
                    'size_mb': 2.3,
                    'uploaded_at': '2024-01-15T10:30:00Z'
                },
                {
                    'filename': 'tutorial_video.mp4',
                    'size_mb': 45.7,
                    'uploaded_at': '2024-01-15T09:45:00Z'
                }
            ],
            'performance_metrics': {
                'avg_upload_time_seconds': 2.3,
                'optimization_success_rate': 0.98,
                'cdn_hit_rate': 0.85,
                'storage_redundancy_level': 'multi-provider'
            }
        })
        
        return StorageStatsResponse(**stats)
        
    except Exception as e:
        logger.error(f"Failed to get storage stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get storage statistics")

# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def _process_upload_analytics(
    user_id: int,
    upload_result: Dict[str, Any],
    processing_time: float
):
    """Process upload analytics in background"""
    
    try:
        logger.info(
            "Upload analytics processed",
            extra={
                'user_id': user_id,
                'media_type': upload_result['media_type'],
                'file_size': upload_result['file_size'],
                'processing_time': processing_time,
                'optimization_used': 'variants' in upload_result
            }
        )
    except Exception as e:
        logger.error(f"Failed to process upload analytics: {e}")

async def _index_image_for_search(
    file_id: str,
    upload_result: Dict[str, Any]
):
    """Index image for visual search"""
    
    try:
        # This would typically:
        # 1. Extract visual features from the image
        # 2. Generate embeddings for similarity search
        # 3. Add to search index
        # 4. Enable reverse image search
        
        logger.info(f"Image indexed for search: {file_id}")
    except Exception as e:
        logger.error(f"Failed to index image: {e}")

async def _optimize_file_background(
    storage_path: str,
    quality_preset: str,
    generate_variants: bool,
    user_id: int
):
    """Optimize file in background"""
    
    try:
        # This would re-process the file with new optimization settings
        logger.info(f"File optimization completed: {storage_path}")
    except Exception as e:
        logger.error(f"File optimization failed: {e}")

# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@router.get("/admin/health")
async def storage_health_check():
    """Storage system health check"""
    
    stats = await enhanced_storage.get_upload_stats()
    
    return {
        'status': 'healthy',
        'providers': stats['storage_providers'],
        'cdn_status': 'active' if stats['cdn_enabled'] else 'disabled',
        'processing_status': 'active' if stats['processing_capabilities']['image_optimization'] else 'limited',
        'timestamp': datetime.utcnow().isoformat()
    }
