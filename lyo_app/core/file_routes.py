"""
File upload routes for LyoApp.
Provides secure file upload, download, and management endpoints.
"""

import os
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_async_session
from lyo_app.core.file_upload import FileUploadService, FileUpload
from lyo_app.auth.dependencies import get_current_user
from lyo_app.models.enhanced import User
from lyo_app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/files", tags=["File Management"])
upload_service = FileUploadService()


@router.post("/upload", response_model=dict)
async def upload_file(
    file: UploadFile = File(...),
    purpose: str = Form(default="document"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Upload a file for the authenticated user."""
    try:
        # Validate file and save
        file_record = await upload_service.save_file(
            file=file,
            user_id=current_user.id,
            purpose=purpose,
            db=db
        )
        
        logger.info(f"File uploaded by user {current_user.id}: {file_record.filename}")
        
        return {
            "id": file_record.id,
            "filename": file_record.filename,
            "original_filename": file_record.original_filename,
            "file_size": file_record.file_size,
            "content_type": file_record.content_type,
            "purpose": file_record.upload_purpose,
            "url": upload_service.get_file_url(file_record),
            "created_at": file_record.created_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed"
        )


@router.get("/download/{file_id}")
async def download_file(
    file_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Download a file by ID."""
    try:
        # Get file record
        from sqlalchemy import select
        stmt = select(FileUpload).where(
            FileUpload.id == file_id,
            FileUpload.user_id == current_user.id
        )
        result = await db.execute(stmt)
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        # Check if file exists on disk
        file_path = Path(file_record.file_path)
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on disk"
            )
        
        # Return file
        return FileResponse(
            path=str(file_path),
            filename=file_record.original_filename,
            media_type=file_record.content_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File download failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File download failed"
        )


@router.get("/", response_model=List[dict])
async def list_user_files(
    purpose: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """List all files uploaded by the authenticated user."""
    try:
        files = await upload_service.get_user_files(
            db=db,
            user_id=current_user.id,
            purpose=purpose
        )
        
        return [
            {
                "id": file_record.id,
                "filename": file_record.filename,
                "original_filename": file_record.original_filename,
                "file_size": file_record.file_size,
                "content_type": file_record.content_type,
                "purpose": file_record.upload_purpose,
                "url": upload_service.get_file_url(file_record),
                "created_at": file_record.created_at
            }
            for file_record in files
        ]
        
    except Exception as e:
        logger.error(f"Failed to list files for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list files"
        )


@router.delete("/{file_id}")
async def delete_file(
    file_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Delete a file by ID."""
    try:
        success = await upload_service.delete_file(
            db=db,
            file_id=file_id,
            user_id=current_user.id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        logger.info(f"File {file_id} deleted by user {current_user.id}")
        
        return {"message": "File deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File deletion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File deletion failed"
        )


@router.post("/avatar", response_model=dict)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Upload user avatar image."""
    try:
        # Upload avatar with specific purpose
        file_record = await upload_service.save_file(
            file=file,
            user_id=current_user.id,
            purpose="avatar",
            db=db
        )
        
        # Update user avatar URL
        current_user.avatar_url = upload_service.get_file_url(file_record)
        await db.commit()
        
        logger.info(f"Avatar uploaded for user {current_user.id}")
        
        return {
            "id": file_record.id,
            "filename": file_record.filename,
            "url": upload_service.get_file_url(file_record),
            "message": "Avatar uploaded successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Avatar upload failed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Avatar upload failed"
        )


@router.get("/info/{file_id}")
async def get_file_info(
    file_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Get file information by ID."""
    try:
        from sqlalchemy import select
        stmt = select(FileUpload).where(
            FileUpload.id == file_id,
            FileUpload.user_id == current_user.id
        )
        result = await db.execute(stmt)
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        return {
            "id": file_record.id,
            "filename": file_record.filename,
            "original_filename": file_record.original_filename,
            "file_size": file_record.file_size,
            "content_type": file_record.content_type,
            "purpose": file_record.upload_purpose,
            "file_hash": file_record.file_hash,
            "url": upload_service.get_file_url(file_record),
            "created_at": file_record.created_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get file info"
        )


@router.post("/cleanup")
async def cleanup_temp_files(
    current_user: User = Depends(get_current_user)
):
    """Cleanup temporary files (admin only)."""
    try:
        # Check if user has admin permissions
        if not current_user.has_permission("manage_files"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        
        cleaned_count = await upload_service.cleanup_temp_files()
        
        logger.info(f"Temp files cleanup performed by user {current_user.id}: {cleaned_count} files")
        
        return {
            "message": f"Cleanup completed. {cleaned_count} temporary files removed."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Temp files cleanup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cleanup failed"
        )
