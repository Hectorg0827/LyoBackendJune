"""
Google Cloud Storage Integration for LyoBackend
Handles complex storage operations that require backend processing
"""

from google.cloud import storage
from google.cloud.exceptions import NotFound
import os
import io
import uuid
from typing import Optional, Dict, Any, List
from PIL import Image
import asyncio
from concurrent.futures import ThreadPoolExecutor
import mimetypes
from fastapi import UploadFile, HTTPException
import logging

logger = logging.getLogger(__name__)

class GCSManager:
    """Google Cloud Storage Manager for LyoBackend"""
    
    def __init__(self):
        self.client = storage.Client()
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "lyobackend-storage")
        self.bucket = self._get_or_create_bucket()
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    def _get_or_create_bucket(self) -> storage.Bucket:
        """Get or create the GCS bucket"""
        try:
            bucket = self.client.bucket(self.bucket_name)
            bucket.reload()  # Check if bucket exists
            logger.info(f"Using existing GCS bucket: {self.bucket_name}")
            return bucket
        except NotFound:
            logger.info(f"Creating new GCS bucket: {self.bucket_name}")
            bucket = self.client.create_bucket(self.bucket_name)
            return bucket
    
    async def upload_file_async(
        self, 
        file: UploadFile, 
        folder: str = "uploads",
        process_image: bool = False,
        max_width: int = 1920,
        max_height: int = 1080
    ) -> Dict[str, Any]:
        """
        Upload file to GCS with optional image processing
        
        Args:
            file: FastAPI UploadFile object
            folder: GCS folder/prefix for the file
            process_image: Whether to resize/optimize images
            max_width: Maximum image width
            max_height: Maximum image height
            
        Returns:
            Dict with file info including GCS URL
        """
        try:
            # Generate unique filename
            file_extension = os.path.splitext(file.filename)[1] if file.filename else ""
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            blob_name = f"{folder}/{unique_filename}"
            
            # Read file content
            file_content = await file.read()
            
            # Process image if requested and file is an image
            if process_image and self._is_image(file.content_type):
                file_content = await self._process_image_async(
                    file_content, max_width, max_height
                )
            
            # Upload to GCS
            upload_info = await self._upload_to_gcs_async(
                blob_name, file_content, file.content_type
            )
            
            return {
                "success": True,
                "filename": unique_filename,
                "original_filename": file.filename,
                "blob_name": blob_name,
                "public_url": upload_info["public_url"],
                "gcs_uri": upload_info["gcs_uri"],
                "size": len(file_content),
                "content_type": file.content_type,
                "bucket": self.bucket_name
            }
            
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
    async def _upload_to_gcs_async(
        self, blob_name: str, content: bytes, content_type: str
    ) -> Dict[str, str]:
        """Upload content to GCS asynchronously"""
        loop = asyncio.get_event_loop()
        
        def _upload():
            blob = self.bucket.blob(blob_name)
            blob.upload_from_string(content, content_type=content_type)
            blob.make_public()  # Make publicly readable
            
            return {
                "public_url": blob.public_url,
                "gcs_uri": f"gs://{self.bucket_name}/{blob_name}"
            }
        
        return await loop.run_in_executor(self.executor, _upload)
    
    async def _process_image_async(
        self, content: bytes, max_width: int, max_height: int
    ) -> bytes:
        """Process image asynchronously (resize, optimize)"""
        loop = asyncio.get_event_loop()
        
        def _process():
            try:
                # Open image
                image = Image.open(io.BytesIO(content))
                
                # Convert RGBA to RGB if necessary
                if image.mode == 'RGBA':
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1])
                    image = background
                
                # Resize if necessary
                if image.width > max_width or image.height > max_height:
                    image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                # Save optimized image
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=85, optimize=True)
                return output.getvalue()
                
            except Exception as e:
                logger.error(f"Error processing image: {str(e)}")
                return content  # Return original if processing fails
        
        return await loop.run_in_executor(self.executor, _process)
    
    async def delete_file_async(self, blob_name: str) -> bool:
        """Delete file from GCS"""
        loop = asyncio.get_event_loop()
        
        def _delete():
            try:
                blob = self.bucket.blob(blob_name)
                blob.delete()
                return True
            except NotFound:
                return False
            except Exception as e:
                logger.error(f"Error deleting file: {str(e)}")
                return False
        
        return await loop.run_in_executor(self.executor, _delete)
    
    async def list_files_async(
        self, folder: str = "", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List files in GCS bucket"""
        loop = asyncio.get_event_loop()
        
        def _list():
            blobs = self.client.list_blobs(
                self.bucket_name, prefix=folder, max_results=limit
            )
            
            files = []
            for blob in blobs:
                files.append({
                    "name": blob.name,
                    "size": blob.size,
                    "created": blob.time_created.isoformat(),
                    "updated": blob.updated.isoformat(),
                    "content_type": blob.content_type,
                    "public_url": blob.public_url,
                    "gcs_uri": f"gs://{self.bucket_name}/{blob.name}"
                })
            
            return files
        
        return await loop.run_in_executor(self.executor, _list)
    
    def _is_image(self, content_type: str) -> bool:
        """Check if content type is an image"""
        return content_type and content_type.startswith('image/')
    
    async def get_file_metadata(self, blob_name: str) -> Optional[Dict[str, Any]]:
        """Get file metadata from GCS"""
        loop = asyncio.get_event_loop()
        
        def _get_metadata():
            try:
                blob = self.bucket.blob(blob_name)
                blob.reload()
                
                return {
                    "name": blob.name,
                    "size": blob.size,
                    "created": blob.time_created.isoformat(),
                    "updated": blob.updated.isoformat(),
                    "content_type": blob.content_type,
                    "public_url": blob.public_url,
                    "gcs_uri": f"gs://{self.bucket_name}/{blob.name}",
                    "etag": blob.etag
                }
            except NotFound:
                return None
            except Exception as e:
                logger.error(f"Error getting metadata: {str(e)}")
                return None
        
        return await loop.run_in_executor(self.executor, _get_metadata)

# Global GCS manager instance
gcs_manager = None

def get_gcs_manager() -> GCSManager:
    """Get or create GCS manager instance"""
    global gcs_manager
    if gcs_manager is None:
        gcs_manager = GCSManager()
    return gcs_manager
