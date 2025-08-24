"""
File upload system for LyoApp.
Handles secure file uploads with validation and storage.
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional, BinaryIO
from pathlib import Path

from fastapi import UploadFile, HTTPException, status
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lyo_app.core.database import Base
from lyo_app.core.config import settings


class FileUpload(Base):
    """File upload model."""
    
    __tablename__ = "file_uploads"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))  # SHA-256 hash
    upload_purpose: Mapped[Optional[str]] = mapped_column(String(50))  # avatar, document, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", backref="uploaded_files")


class FileUploadService:
    """File upload service with security validations."""
    
    ALLOWED_IMAGE_TYPES = {
        "image/jpeg": [".jpg", ".jpeg"],
        "image/png": [".png"],
        "image/gif": [".gif"],
        "image/webp": [".webp"]
    }
    
    ALLOWED_DOCUMENT_TYPES = {
        "application/pdf": [".pdf"],
        "text/plain": [".txt"],
        "text/markdown": [".md"],
        "application/msword": [".doc"],
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"]
    }
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5MB
    
    def __init__(self, upload_dir: str = "uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        (self.upload_dir / "avatars").mkdir(exist_ok=True)
        (self.upload_dir / "documents").mkdir(exist_ok=True)
        (self.upload_dir / "temp").mkdir(exist_ok=True)
    
    def validate_file(self, file: UploadFile, purpose: str = "document") -> None:
        """Validate uploaded file."""
        # Check file size
        max_size = self.MAX_IMAGE_SIZE if purpose == "avatar" else self.MAX_FILE_SIZE
        if hasattr(file, 'size') and file.size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {max_size // (1024*1024)}MB"
            )
        
        # Check content type
        allowed_types = self.ALLOWED_IMAGE_TYPES if purpose == "avatar" else {
            **self.ALLOWED_IMAGE_TYPES,
            **self.ALLOWED_DOCUMENT_TYPES
        }
        
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed. Allowed types: {list(allowed_types.keys())}"
            )
        
        # Check file extension
        file_ext = Path(file.filename).suffix.lower()
        valid_extensions = allowed_types[file.content_type]
        
        if file_ext not in valid_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File extension does not match content type"
            )
    
    def generate_filename(self, original_filename: str, purpose: str = "document") -> str:
        """Generate unique filename."""
        file_ext = Path(original_filename).suffix
        unique_id = str(uuid.uuid4())
        return f"{purpose}_{unique_id}{file_ext}"
    
    async def save_file(
        self, 
        file: UploadFile, 
        user_id: int, 
        purpose: str = "document",
        db: Optional[AsyncSession] = None
    ) -> FileUpload:
        """Save uploaded file."""
        # Validate file
        self.validate_file(file, purpose)
        
        # Generate unique filename
        filename = self.generate_filename(file.filename, purpose)
        
        # Determine subdirectory
        subdir = "avatars" if purpose == "avatar" else "documents"
        file_path = self.upload_dir / subdir / filename
        
        # Save file to disk
        file_size = 0
        file_hash = None
        
        try:
            import hashlib
            hasher = hashlib.sha256()
            
            with open(file_path, "wb") as buffer:
                content = await file.read()
                file_size = len(content)
                hasher.update(content)
                file_hash = hasher.hexdigest()
                buffer.write(content)
        
        except Exception as e:
            # Clean up file if it was created
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {str(e)}"
            )
        
        # Create database record
        if db:
            file_record = FileUpload(
                user_id=user_id,
                filename=filename,
                original_filename=file.filename,
                file_path=str(file_path),
                file_size=file_size,
                content_type=file.content_type,
                file_hash=file_hash,
                upload_purpose=purpose
            )
            
            db.add(file_record)
            await db.commit()
            await db.refresh(file_record)
            
            return file_record
        
        # Return minimal file info if no DB session
        return {
            "filename": filename,
            "original_filename": file.filename,
            "file_path": str(file_path),
            "file_size": file_size,
            "content_type": file.content_type
        }
    
    async def delete_file(self, db: AsyncSession, file_id: int, user_id: int) -> bool:
        """Delete uploaded file."""
        from sqlalchemy import select
        
        # Get file record
        stmt = select(FileUpload).where(
            FileUpload.id == file_id,
            FileUpload.user_id == user_id
        )
        result = await db.execute(stmt)
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            return False
        
        # Delete file from disk
        file_path = Path(file_record.file_path)
        if file_path.exists():
            file_path.unlink()
        
        # Delete database record
        await db.delete(file_record)
        await db.commit()
        
        return True
    
    async def get_user_files(
        self, 
        db: AsyncSession, 
        user_id: int, 
        purpose: Optional[str] = None
    ) -> List[FileUpload]:
        """Get all files uploaded by user."""
        from sqlalchemy import select
        
        stmt = select(FileUpload).where(FileUpload.user_id == user_id)
        
        if purpose:
            stmt = stmt.where(FileUpload.upload_purpose == purpose)
        
        result = await db.execute(stmt)
        return result.scalars().all()
    
    def get_file_url(self, file_record: FileUpload) -> str:
        """Generate file URL."""
        # In production, this would be a CDN URL or proper file serving endpoint
        return f"/api/v1/files/{file_record.id}"
    
    async def cleanup_temp_files(self, older_than_hours: int = 24) -> int:
        """Clean up temporary files older than specified hours."""
        temp_dir = self.upload_dir / "temp"
        cutoff_time = datetime.utcnow().timestamp() - (older_than_hours * 3600)
        
        cleaned_count = 0
        
        for file_path in temp_dir.iterdir():
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                try:
                    file_path.unlink()
                    cleaned_count += 1
                except OSError:
                    pass
        
        return cleaned_count
