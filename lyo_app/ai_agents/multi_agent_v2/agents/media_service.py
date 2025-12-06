"""
Media Service - Image Generation and Storage

MIT Architecture Engineering - Media Generation Pipeline

This module provides:
- AI image generation (placeholder/Imagen)
- Google Cloud Storage integration
- Diagram generation (Mermaid support)
- Signed URL generation
"""

import logging
import hashlib
import base64
import io
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import uuid

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)


# Try to import Google Cloud Storage
try:
    from google.cloud import storage as gcs_storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("Google Cloud Storage not available")


class ImageStyle(str, Enum):
    """Styles for generated images"""
    EDUCATIONAL_DIAGRAM = "educational_diagram"
    CONCEPT_ILLUSTRATION = "concept_illustration"
    FLOWCHART = "flowchart"
    INFOGRAPHIC = "infographic"
    PHOTO_REALISTIC = "photo_realistic"
    SKETCH = "sketch"


class DiagramType(str, Enum):
    """Types of diagrams that can be generated"""
    FLOWCHART = "flowchart"
    SEQUENCE = "sequence"
    CLASS = "class"
    STATE = "state"
    ER = "er"
    MINDMAP = "mindmap"


class ImageGenerationRequest(BaseModel):
    """Request for image generation"""
    concept: str
    style: ImageStyle = ImageStyle.EDUCATIONAL_DIAGRAM
    width: int = 512
    height: int = 512
    additional_context: Optional[str] = None


class DiagramGenerationRequest(BaseModel):
    """Request for diagram generation"""
    title: str
    diagram_type: DiagramType
    content: str  # Mermaid syntax or description
    theme: str = "default"


class MediaResult(BaseModel):
    """Result of media generation"""
    success: bool
    url: Optional[str] = None
    public_url: Optional[str] = None
    signed_url: Optional[str] = None
    media_type: str = "image/png"
    width: Optional[int] = None
    height: Optional[int] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MediaService:
    """
    Service for generating and storing media assets.
    
    Features:
    - AI image generation
    - Diagram generation
    - GCS storage integration
    - Signed URL generation
    """
    
    def __init__(self):
        self.bucket_name = getattr(settings, 'gcs_bucket_name', None) or getattr(settings, 'GCS_BUCKET_NAME', 'lyobackend-storage')
        self.project_id = getattr(settings, 'gcp_project_id', None) or getattr(settings, 'GCP_PROJECT_ID', 'lyobackend')
        self._storage_client = None
        self._bucket = None
        
        # Initialize storage client
        if GCS_AVAILABLE:
            try:
                self._storage_client = gcs_storage.Client(project=self.project_id)
                self._bucket = self._storage_client.bucket(self.bucket_name)
                logger.info(f"MediaService initialized with bucket: {self.bucket_name}")
            except Exception as e:
                logger.warning(f"MediaService: Failed to initialize GCS: {e}")
        else:
            logger.warning("MediaService: GCS not available, using placeholder mode")
    
    @property
    def is_storage_available(self) -> bool:
        return self._bucket is not None
    
    async def generate_image(
        self,
        request: ImageGenerationRequest
    ) -> MediaResult:
        """
        Generate an educational image for a concept.
        
        Currently generates placeholder images.
        In production, integrate with Imagen API.
        """
        try:
            # Generate a unique filename
            image_id = str(uuid.uuid4())
            filename = f"generated/{request.style.value}/{image_id}.png"
            
            # Generate placeholder image
            image_data = self._generate_placeholder_image(
                request.concept,
                request.style,
                request.width,
                request.height
            )
            
            # Upload to storage if available
            if self.is_storage_available:
                blob = self._bucket.blob(filename)
                blob.upload_from_string(
                    image_data,
                    content_type="image/png"
                )
                
                # Generate signed URL
                signed_url = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(hours=24),
                    method="GET"
                )
                
                return MediaResult(
                    success=True,
                    url=f"gs://{self.bucket_name}/{filename}",
                    public_url=f"https://storage.googleapis.com/{self.bucket_name}/{filename}",
                    signed_url=signed_url,
                    media_type="image/png",
                    width=request.width,
                    height=request.height,
                    metadata={
                        "concept": request.concept,
                        "style": request.style.value,
                        "generated_at": datetime.utcnow().isoformat()
                    }
                )
            else:
                # Return base64 data URL
                b64_data = base64.b64encode(image_data).decode('utf-8')
                return MediaResult(
                    success=True,
                    url=f"data:image/png;base64,{b64_data}",
                    media_type="image/png",
                    width=request.width,
                    height=request.height,
                    metadata={
                        "concept": request.concept,
                        "style": request.style.value,
                        "mode": "base64"
                    }
                )
                
        except Exception as e:
            logger.error(f"Image generation error: {e}")
            return MediaResult(
                success=False,
                error=str(e)
            )
    
    def _generate_placeholder_image(
        self,
        concept: str,
        style: ImageStyle,
        width: int,
        height: int
    ) -> bytes:
        """
        Generate a simple placeholder image.
        
        This creates a basic SVG-based placeholder.
        In production, replace with Imagen API.
        """
        # Create a simple SVG placeholder
        color_hash = hashlib.md5(concept.encode()).hexdigest()[:6]
        bg_color = f"#{color_hash}"
        
        # Generate contrasting text color
        r, g, b = int(color_hash[:2], 16), int(color_hash[2:4], 16), int(color_hash[4:6], 16)
        text_color = "#FFFFFF" if (r * 0.299 + g * 0.587 + b * 0.114) < 128 else "#000000"
        
        # Truncate concept for display
        display_text = concept[:30] + "..." if len(concept) > 30 else concept
        
        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    <rect width="100%" height="100%" fill="{bg_color}"/>
    <text x="50%" y="45%" font-family="Arial, sans-serif" font-size="16" 
          fill="{text_color}" text-anchor="middle" dominant-baseline="middle">
        {display_text}
    </text>
    <text x="50%" y="55%" font-family="Arial, sans-serif" font-size="12" 
          fill="{text_color}" text-anchor="middle" dominant-baseline="middle" opacity="0.7">
        [{style.value}]
    </text>
</svg>'''
        
        return svg.encode('utf-8')
    
    async def generate_diagram(
        self,
        request: DiagramGenerationRequest
    ) -> MediaResult:
        """
        Generate a diagram (Mermaid-based).
        
        Returns the Mermaid code that can be rendered client-side.
        """
        try:
            # Generate Mermaid code based on type
            mermaid_code = self._build_mermaid_code(request)
            
            # Create a unique ID
            diagram_id = str(uuid.uuid4())
            filename = f"diagrams/{request.diagram_type.value}/{diagram_id}.mmd"
            
            # Store the Mermaid code if storage is available
            if self.is_storage_available:
                blob = self._bucket.blob(filename)
                blob.upload_from_string(
                    mermaid_code,
                    content_type="text/plain"
                )
                
                return MediaResult(
                    success=True,
                    url=f"gs://{self.bucket_name}/{filename}",
                    media_type="text/mermaid",
                    metadata={
                        "title": request.title,
                        "diagram_type": request.diagram_type.value,
                        "mermaid_code": mermaid_code,
                        "theme": request.theme
                    }
                )
            else:
                return MediaResult(
                    success=True,
                    media_type="text/mermaid",
                    metadata={
                        "title": request.title,
                        "diagram_type": request.diagram_type.value,
                        "mermaid_code": mermaid_code,
                        "theme": request.theme
                    }
                )
                
        except Exception as e:
            logger.error(f"Diagram generation error: {e}")
            return MediaResult(
                success=False,
                error=str(e)
            )
    
    def _build_mermaid_code(self, request: DiagramGenerationRequest) -> str:
        """Build Mermaid code from request"""
        
        # If content is already Mermaid syntax, use it directly
        if any(keyword in request.content.lower() for keyword in ['graph', 'flowchart', 'sequencediagram', 'classDiagram']):
            return request.content
        
        # Otherwise, wrap in appropriate diagram type
        prefixes = {
            DiagramType.FLOWCHART: "flowchart TD",
            DiagramType.SEQUENCE: "sequenceDiagram",
            DiagramType.CLASS: "classDiagram",
            DiagramType.STATE: "stateDiagram-v2",
            DiagramType.ER: "erDiagram",
            DiagramType.MINDMAP: "mindmap"
        }
        
        prefix = prefixes.get(request.diagram_type, "flowchart TD")
        return f"---\ntitle: {request.title}\n---\n{prefix}\n{request.content}"
    
    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        folder: str = "uploads"
    ) -> MediaResult:
        """
        Upload a file to cloud storage.
        """
        try:
            if not self.is_storage_available:
                return MediaResult(
                    success=False,
                    error="Cloud storage not available"
                )
            
            # Generate unique path
            file_id = str(uuid.uuid4())
            ext = filename.split('.')[-1] if '.' in filename else ''
            storage_path = f"{folder}/{file_id}.{ext}" if ext else f"{folder}/{file_id}"
            
            # Upload
            blob = self._bucket.blob(storage_path)
            blob.upload_from_string(
                file_data,
                content_type=content_type
            )
            
            # Generate URLs
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=24),
                method="GET"
            )
            
            return MediaResult(
                success=True,
                url=f"gs://{self.bucket_name}/{storage_path}",
                public_url=f"https://storage.googleapis.com/{self.bucket_name}/{storage_path}",
                signed_url=signed_url,
                media_type=content_type,
                metadata={
                    "original_filename": filename,
                    "uploaded_at": datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"File upload error: {e}")
            return MediaResult(
                success=False,
                error=str(e)
            )
    
    async def get_signed_url(
        self,
        blob_path: str,
        expiration_hours: int = 24
    ) -> Optional[str]:
        """
        Generate a signed URL for an existing blob.
        """
        try:
            if not self.is_storage_available:
                return None
            
            blob = self._bucket.blob(blob_path)
            if not blob.exists():
                return None
            
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=expiration_hours),
                method="GET"
            )
            
        except Exception as e:
            logger.error(f"Signed URL generation error: {e}")
            return None
    
    async def delete_file(self, blob_path: str) -> bool:
        """Delete a file from storage"""
        try:
            if not self.is_storage_available:
                return False
            
            blob = self._bucket.blob(blob_path)
            blob.delete()
            return True
            
        except Exception as e:
            logger.error(f"File deletion error: {e}")
            return False


# Singleton instance
_media_service: Optional[MediaService] = None


def get_media_service() -> MediaService:
    """Get or create the singleton MediaService instance"""
    global _media_service
    if _media_service is None:
        _media_service = MediaService()
    return _media_service
