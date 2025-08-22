"""
Enhanced Storage System with CDN Integration and Media Optimization
Production-ready storage with AWS S3, Cloudflare R2, and intelligent caching
"""

import asyncio
import hashlib
import io
import json
import mimetypes
import os
import tempfile
from typing import Dict, List, Optional, Tuple, Union, Any
from datetime import datetime, timedelta
from pathlib import Path

try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

import aiofiles
try:
    import aiohttp
except ImportError:
    aiohttp = None
from fastapi import HTTPException, UploadFile

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    from lyo_app.core.enhanced_config import EnhancedSettings
    settings = EnhancedSettings()
except ImportError:
    from lyo_app.core.config import settings
from lyo_app.core.logging import logger

class MediaType:
    """Enhanced media type detection and processing"""
    
    IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.heic'}
    VIDEO_FORMATS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
    AUDIO_FORMATS = {'.mp3', '.wav', '.aac', '.ogg', '.m4a', '.flac'}
    DOCUMENT_FORMATS = {'.pdf', '.doc', '.docx', '.txt', '.md', '.rtf'}
    
    @classmethod
    def get_media_type(cls, filename: str) -> str:
        """Get media type from filename"""
        ext = Path(filename).suffix.lower()
        
        if ext in cls.IMAGE_FORMATS:
            return 'image'
        elif ext in cls.VIDEO_FORMATS:
            return 'video'
        elif ext in cls.AUDIO_FORMATS:
            return 'audio'
        elif ext in cls.DOCUMENT_FORMATS:
            return 'document'
        else:
            return 'other'

class ImageProcessor:
    """Advanced image processing for optimization"""
    
    QUALITY_PRESETS = {
        'thumbnail': {'size': (150, 150), 'quality': 85, 'format': 'WEBP'},
        'small': {'size': (400, 400), 'quality': 85, 'format': 'WEBP'},
        'medium': {'size': (800, 800), 'quality': 90, 'format': 'WEBP'},
        'large': {'size': (1200, 1200), 'quality': 95, 'format': 'WEBP'},
        'original': {'quality': 100, 'format': 'WEBP'}
    }
    
    @staticmethod
    async def process_image(
        image_data: bytes, 
        preset: str = 'medium',
        custom_size: Optional[Tuple[int, int]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Process image with optimization"""
        
        if not PIL_AVAILABLE:
            # Return original data if PIL not available
            metadata = {
                'format': 'unknown',
                'size': (0, 0),
                'optimization': 'none',
                'file_size': len(image_data),
                'compression_ratio': 1.0,
                'warning': 'PIL not available - no optimization performed'
            }
            return image_data, metadata
        
        try:
            # Open image
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA', 'P'):
                # Handle transparency
                if image.mode == 'RGBA':
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1])
                    image = background
                else:
                    image = image.convert('RGB')
            
            # Get processing settings
            settings_dict = ImageProcessor.QUALITY_PRESETS.get(preset, ImageProcessor.QUALITY_PRESETS['medium'])
            
            # Resize if needed
            if custom_size:
                image = ImageOps.fit(image, custom_size, Image.Resampling.LANCZOS)
            elif 'size' in settings_dict:
                image = ImageOps.fit(image, settings_dict['size'], Image.Resampling.LANCZOS)
            
            # Save optimized image
            output = io.BytesIO()
            format_name = settings_dict.get('format', 'WEBP')
            quality = settings_dict.get('quality', 90)
            
            save_kwargs = {'format': format_name, 'optimize': True}
            if format_name in ['JPEG', 'WEBP']:
                save_kwargs['quality'] = quality
            
            image.save(output, **save_kwargs)
            optimized_data = output.getvalue()
            
            # Get metadata
            metadata = {
                'original_size': len(image_data),
                'optimized_size': len(optimized_data),
                'compression_ratio': len(optimized_data) / len(image_data),
                'dimensions': image.size,
                'format': format_name.lower(),
                'quality_preset': preset
            }
            
            return optimized_data, metadata
            
        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            raise HTTPException(status_code=400, detail=f"Image processing failed: {str(e)}")

class VideoProcessor:
    """Advanced video processing for optimization"""
    
    QUALITY_PRESETS = {
        'thumbnail': {'size': (320, 240), 'bitrate': '500k', 'fps': 30},
        'low': {'size': (640, 480), 'bitrate': '1M', 'fps': 30},
        'medium': {'size': (1280, 720), 'bitrate': '2.5M', 'fps': 30},
        'high': {'size': (1920, 1080), 'bitrate': '5M', 'fps': 60},
        'original': {'bitrate': '10M', 'fps': 60}
    }
    
    @staticmethod
    async def process_video(
        video_path: str,
        preset: str = 'medium',
        extract_thumbnail: bool = True
    ) -> Dict[str, Any]:
        """Process video with optimization"""
        
        if not CV2_AVAILABLE:
            # Return basic metadata if cv2 not available
            file_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
            return {
                'original_size': file_size,
                'processed_size': file_size,
                'compression_ratio': 1.0,
                'duration': 0,
                'fps': 0,
                'resolution': (0, 0),
                'thumbnail': None,
                'warning': 'cv2 not available - no video processing performed'
            }
        
        try:
            # Open video
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                raise ValueError("Could not open video file")
            
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            
            metadata = {
                'duration': duration,
                'fps': fps,
                'frame_count': frame_count,
                'dimensions': (width, height),
                'file_size': os.path.getsize(video_path)
            }
            
            # Extract thumbnail if requested
            if extract_thumbnail:
                # Get frame from middle of video
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count // 2)
                ret, frame = cap.read()
                
                if ret:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    # Convert to PIL Image
                    thumbnail_image = Image.fromarray(frame_rgb)
                    
                    # Process thumbnail
                    thumbnail_io = io.BytesIO()
                    thumbnail_image.save(thumbnail_io, format='JPEG', quality=85)
                    metadata['thumbnail_data'] = thumbnail_io.getvalue()
            
            cap.release()
            
            return metadata
            
        except Exception as e:
            logger.error(f"Video processing failed: {e}")
            raise HTTPException(status_code=400, detail=f"Video processing failed: {str(e)}")

class CDNManager:
    """Cloudflare CDN integration for global content delivery"""
    
    def __init__(self):
        self.cloudflare_zone_id = settings.CLOUDFLARE_ZONE_ID
        self.cloudflare_api_token = settings.CLOUDFLARE_API_TOKEN
        self.cdn_base_url = settings.CDN_BASE_URL
    
    async def purge_cache(self, urls: List[str]) -> bool:
        """Purge CDN cache for specific URLs"""
        
        if not self.cloudflare_api_token:
            logger.warning("Cloudflare API token not configured")
            return False
        
        try:
            headers = {
                'Authorization': f'Bearer {self.cloudflare_api_token}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'files': urls
            }
            
            async with aiohttp.ClientSession() as session:
                url = f'https://api.cloudflare.com/client/v4/zones/{self.cloudflare_zone_id}/purge_cache'
                async with session.post(url, headers=headers, json=data) as response:
                    result = await response.json()
                    
                    if result.get('success'):
                        logger.info(f"CDN cache purged for {len(urls)} URLs")
                        return True
                    else:
                        logger.error(f"CDN cache purge failed: {result}")
                        return False
        
        except Exception as e:
            logger.error(f"CDN cache purge failed: {e}")
            return False
    
    def get_cdn_url(self, storage_path: str) -> str:
        """Get CDN URL for a storage path"""
        if self.cdn_base_url:
            return f"{self.cdn_base_url.rstrip('/')}/{storage_path.lstrip('/')}"
        return storage_path

class EnhancedStorageSystem:
    """
    Production-ready storage system with multiple backends and optimization
    
    Features:
    - Multi-provider support (AWS S3, Cloudflare R2, local storage)
    - Intelligent media processing and optimization
    - CDN integration for global delivery
    - Redis caching for metadata and frequently accessed files
    - Automatic failover between storage providers
    - Smart compression and format conversion
    """
    
    def __init__(self):
        self.redis_client = None
        self.s3_client = None
        self.r2_client = None
        self.cdn_manager = CDNManager()
        self.image_processor = ImageProcessor()
        self.video_processor = VideoProcessor()
        
        # Will initialize storage clients lazily
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Ensure clients are initialized"""
        if not self._initialized:
            await self._initialize_clients()
            self._initialized = True
    
    async def _initialize_clients(self):
        """Initialize storage and cache clients"""
        
        try:
            # Initialize Redis for caching
            if REDIS_AVAILABLE and settings.REDIS_URL:
                self.redis_client = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True
                )
                logger.info("Redis client initialized")
            
            # Initialize AWS S3
            if BOTO3_AVAILABLE and settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION or 'us-east-1'
                )
                logger.info("AWS S3 client initialized")
            
            # Initialize Cloudflare R2
            if BOTO3_AVAILABLE and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY:
                self.r2_client = boto3.client(
                    's3',
                    endpoint_url=settings.R2_ENDPOINT_URL,
                    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                    region_name='auto'
                )
                logger.info("Cloudflare R2 client initialized")
        
        except Exception as e:
            logger.error(f"Storage client initialization failed: {e}")
    
    async def upload_file(
        self,
        file: UploadFile,
        folder: str = "uploads",
        user_id: Optional[int] = None,
        optimize: bool = True,
        generate_variants: bool = True
    ) -> Dict[str, Any]:
        """
        Upload file with intelligent processing and optimization
        
        Returns:
            Dict containing upload results, URLs, and metadata
        """
        
        try:
            # Read file data
            file_data = await file.read()
            file_size = len(file_data)
            
            # Generate unique filename
            file_hash = hashlib.sha256(file_data).hexdigest()[:16]
            timestamp = int(datetime.utcnow().timestamp())
            file_ext = Path(file.filename).suffix.lower()
            
            base_filename = f"{timestamp}_{file_hash}{file_ext}"
            storage_path = f"{folder}/{base_filename}"
            
            # Detect media type
            media_type = MediaType.get_media_type(file.filename)
            
            # Initialize result
            result = {
                'original_filename': file.filename,
                'storage_path': storage_path,
                'media_type': media_type,
                'file_size': file_size,
                'upload_timestamp': datetime.utcnow().isoformat(),
                'user_id': user_id,
                'urls': {},
                'variants': {},
                'metadata': {}
            }
            
            # Process based on media type
            if media_type == 'image' and optimize:
                processed_files = await self._process_image_variants(
                    file_data, storage_path, generate_variants
                )
                result.update(processed_files)
            
            elif media_type == 'video' and optimize:
                # Save original file temporarily for processing
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
                    temp_file.write(file_data)
                    temp_path = temp_file.name
                
                try:
                    video_metadata = await self.video_processor.process_video(temp_path)
                    result['metadata'].update(video_metadata)
                    
                    # Upload thumbnail if generated
                    if 'thumbnail_data' in video_metadata:
                        thumbnail_path = storage_path.replace(file_ext, '_thumb.jpg')
                        await self._upload_to_storage(
                            video_metadata['thumbnail_data'], thumbnail_path
                        )
                        result['urls']['thumbnail'] = self.cdn_manager.get_cdn_url(thumbnail_path)
                
                finally:
                    os.unlink(temp_path)
                
                # Upload original video
                await self._upload_to_storage(file_data, storage_path)
                result['urls']['original'] = self.cdn_manager.get_cdn_url(storage_path)
            
            else:
                # Upload without processing
                await self._upload_to_storage(file_data, storage_path)
                result['urls']['original'] = self.cdn_manager.get_cdn_url(storage_path)
            
            # Cache metadata
            await self._cache_file_metadata(storage_path, result)
            
            logger.info(f"File uploaded successfully: {storage_path}")
            return result
        
        except Exception as e:
            logger.error(f"File upload failed: {e}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
    async def _process_image_variants(
        self, 
        image_data: bytes, 
        base_path: str, 
        generate_variants: bool
    ) -> Dict[str, Any]:
        """Process image variants for different use cases"""
        
        result = {
            'urls': {},
            'variants': {},
            'metadata': {}
        }
        
        # Process original
        original_processed, original_metadata = await self.image_processor.process_image(
            image_data, 'original'
        )
        
        # Upload original
        await self._upload_to_storage(original_processed, base_path)
        result['urls']['original'] = self.cdn_manager.get_cdn_url(base_path)
        result['metadata']['original'] = original_metadata
        
        if generate_variants:
            # Generate variants for different use cases
            variants_to_generate = ['thumbnail', 'small', 'medium', 'large']
            
            for variant in variants_to_generate:
                try:
                    processed_data, metadata = await self.image_processor.process_image(
                        image_data, variant
                    )
                    
                    # Create variant path
                    variant_path = base_path.replace('.', f'_{variant}.')
                    if not variant_path.endswith('.webp'):
                        variant_path = variant_path.rsplit('.', 1)[0] + '.webp'
                    
                    # Upload variant
                    await self._upload_to_storage(processed_data, variant_path)
                    
                    # Store URLs and metadata
                    result['urls'][variant] = self.cdn_manager.get_cdn_url(variant_path)
                    result['variants'][variant] = {
                        'path': variant_path,
                        'size': len(processed_data),
                        'metadata': metadata
                    }
                
                except Exception as e:
                    logger.warning(f"Failed to generate {variant} variant: {e}")
        
        return result
    
    async def _upload_to_storage(
        self, 
        file_data: bytes, 
        storage_path: str,
        content_type: Optional[str] = None
    ) -> bool:
        """Upload to storage with failover between providers"""
        
        if not content_type:
            content_type = mimetypes.guess_type(storage_path)[0] or 'application/octet-stream'
        
        # Try Cloudflare R2 first (cheaper)
        if self.r2_client:
            try:
                await self._upload_to_r2(file_data, storage_path, content_type)
                return True
            except Exception as e:
                logger.warning(f"R2 upload failed, trying S3: {e}")
        
        # Fallback to AWS S3
        if self.s3_client:
            try:
                await self._upload_to_s3(file_data, storage_path, content_type)
                return True
            except Exception as e:
                logger.warning(f"S3 upload failed, trying local: {e}")
        
        # Final fallback to local storage
        try:
            await self._upload_to_local(file_data, storage_path)
            return True
        except Exception as e:
            logger.error(f"All storage methods failed: {e}")
            raise HTTPException(status_code=500, detail="Storage upload failed")
    
    async def _upload_to_s3(self, file_data: bytes, storage_path: str, content_type: str):
        """Upload to AWS S3"""
        
        self.s3_client.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=storage_path,
            Body=file_data,
            ContentType=content_type,
            CacheControl='public, max-age=31536000',  # 1 year cache
            Metadata={
                'uploaded_at': datetime.utcnow().isoformat(),
                'original_name': storage_path.split('/')[-1]
            }
        )
    
    async def _upload_to_r2(self, file_data: bytes, storage_path: str, content_type: str):
        """Upload to Cloudflare R2"""
        
        self.r2_client.put_object(
            Bucket=settings.R2_BUCKET,
            Key=storage_path,
            Body=file_data,
            ContentType=content_type,
            CacheControl='public, max-age=31536000',  # 1 year cache
            Metadata={
                'uploaded_at': datetime.utcnow().isoformat(),
                'original_name': storage_path.split('/')[-1]
            }
        )
    
    async def _upload_to_local(self, file_data: bytes, storage_path: str):
        """Upload to local storage"""
        
        local_path = Path(settings.UPLOAD_DIR) / storage_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiofiles.open(local_path, 'wb') as f:
            await f.write(file_data)
    
    async def _cache_file_metadata(self, storage_path: str, metadata: Dict[str, Any]):
        """Cache file metadata in Redis"""
        
        if self.redis_client:
            try:
                cache_key = f"file_metadata:{storage_path}"
                await self.redis_client.setex(
                    cache_key,
                    timedelta(days=7),  # Cache for 7 days
                    json.dumps(metadata, default=str)
                )
            except Exception as e:
                logger.warning(f"Failed to cache metadata: {e}")
    
    async def get_file_metadata(self, storage_path: str) -> Optional[Dict[str, Any]]:
        """Get file metadata from cache or storage"""
        
        # Try cache first
        if self.redis_client:
            try:
                cache_key = f"file_metadata:{storage_path}"
                cached_data = await self.redis_client.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning(f"Failed to get cached metadata: {e}")
        
        # TODO: Fallback to storage metadata
        return None
    
    async def delete_file(self, storage_path: str) -> bool:
        """Delete file from all storage locations"""
        
        success = True
        
        # Delete from R2
        if self.r2_client:
            try:
                self.r2_client.delete_object(Bucket=settings.R2_BUCKET, Key=storage_path)
            except Exception as e:
                logger.warning(f"R2 deletion failed: {e}")
                success = False
        
        # Delete from S3
        if self.s3_client:
            try:
                self.s3_client.delete_object(Bucket=settings.AWS_S3_BUCKET, Key=storage_path)
            except Exception as e:
                logger.warning(f"S3 deletion failed: {e}")
                success = False
        
        # Delete from local storage
        try:
            local_path = Path(settings.UPLOAD_DIR) / storage_path
            if local_path.exists():
                local_path.unlink()
        except Exception as e:
            logger.warning(f"Local deletion failed: {e}")
            success = False
        
        # Clear cache
        if self.redis_client:
            try:
                cache_key = f"file_metadata:{storage_path}"
                await self.redis_client.delete(cache_key)
            except Exception as e:
                logger.warning(f"Cache deletion failed: {e}")
        
        # Purge CDN cache
        cdn_url = self.cdn_manager.get_cdn_url(storage_path)
        await self.cdn_manager.purge_cache([cdn_url])
        
        return success
    
    async def get_upload_stats(self) -> Dict[str, Any]:
        """Get upload statistics and storage health"""
        
        stats = {
            'storage_providers': {
                's3_available': self.s3_client is not None,
                'r2_available': self.r2_client is not None,
                'redis_available': self.redis_client is not None
            },
            'cdn_enabled': bool(self.cdn_manager.cdn_base_url),
            'processing_capabilities': {
                'image_optimization': True,
                'video_processing': True,
                'thumbnail_generation': True,
                'format_conversion': True
            }
        }
        
        # Get storage usage if possible
        try:
            if self.redis_client:
                # Get cache statistics
                info = await self.redis_client.info('memory')
                stats['cache_memory_usage'] = info.get('used_memory_human', 'unknown')
        except Exception as e:
            logger.warning(f"Failed to get storage stats: {e}")
        
        return stats

# Global instance
enhanced_storage = EnhancedStorageSystem()
