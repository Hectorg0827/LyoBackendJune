"""
Image Generation Routes - REST API for Educational Images
DALL-E 3 powered visuals for Lyo's AI Classroom
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import logging

from .service import (
    ImageService, 
    get_image_service, 
    ImageSize, 
    ImageQuality, 
    ImageStyle,
    GeneratedImage,
    EDUCATIONAL_PROMPTS
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/images", tags=["Image Generation"])


# Request/Response Models
class GenerateRequest(BaseModel):
    """Request to generate an image"""
    prompt: str = Field(..., min_length=10, max_length=4000, description="Image description")
    size: Optional[ImageSize] = Field(default=ImageSize.SQUARE, description="Image size")
    quality: Optional[ImageQuality] = Field(default=ImageQuality.HD, description="Image quality")
    style: Optional[ImageStyle] = Field(default=ImageStyle.NATURAL, description="Image style")


class EducationalImageRequest(BaseModel):
    """Request for educational image generation"""
    topic: str = Field(..., min_length=3, max_length=500, description="Topic to visualize")
    content_type: str = Field(default="concept_diagram", description="Type of educational visual")
    additional_context: Optional[str] = Field(default=None, max_length=500, description="Extra context")
    size: Optional[ImageSize] = Field(default=ImageSize.LANDSCAPE, description="Image size")


class LessonImagesRequest(BaseModel):
    """Request to generate images for a lesson"""
    lesson_topic: str = Field(..., description="Main lesson topic")
    concepts: List[str] = Field(default_factory=list, description="Key concepts to visualize")
    max_images: int = Field(default=3, ge=1, le=5, description="Maximum images to generate")


class ImageResponse(BaseModel):
    """Generated image response"""
    url: str = Field(..., description="Image URL (expires in ~1 hour)")
    revised_prompt: str = Field(..., description="DALL-E's revised prompt")
    size: str = Field(..., description="Image dimensions")
    style: str = Field(..., description="Image style used")
    prompt_used: str = Field(..., description="Original prompt")


class ContentTypesResponse(BaseModel):
    """Available content types"""
    content_types: dict


# Routes

@router.get("/health")
async def image_health():
    """Check image service health"""
    try:
        service = await get_image_service()
        return {
            "status": "healthy",
            "service": "image_generation",
            "model": service.config.model,
            "api_configured": bool(service.config.api_key)
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service": "image_generation",
            "error": str(e)
        }


@router.get("/content-types", response_model=ContentTypesResponse)
async def get_content_types():
    """
    List available educational content types
    
    Returns template descriptions for each type of educational visual
    """
    service = await get_image_service()
    return ContentTypesResponse(content_types=service.get_content_types())


@router.post("/generate", response_model=ImageResponse)
async def generate_image(request: GenerateRequest):
    """
    Generate an image with custom prompt
    
    For full control over the generated image.
    """
    try:
        service = await get_image_service()
        
        result = await service.generate(
            prompt=request.prompt,
            size=request.size,
            quality=request.quality,
            style=request.style
        )
        
        return ImageResponse(
            url=result.url,
            revised_prompt=result.revised_prompt,
            size=result.size,
            style=result.style,
            prompt_used=result.prompt_used
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise HTTPException(status_code=500, detail="Image generation failed")


@router.post("/educational", response_model=ImageResponse)
async def generate_educational_image(request: EducationalImageRequest):
    """
    Generate an educational image
    
    Uses optimized templates for educational content.
    Content types:
    - concept_diagram: Clean diagram illustrating concepts
    - process_flow: Flowchart showing processes
    - comparison_chart: Side-by-side comparisons
    - mind_map: Branching concept maps
    - timeline: Chronological timelines
    - anatomy_diagram: Labeled structure diagrams
    - infographic: Engaging data visualizations
    - scene_illustration: Illustrative scenes
    """
    try:
        service = await get_image_service()
        
        if request.content_type not in EDUCATIONAL_PROMPTS:
            raise ValueError(f"Unknown content type: {request.content_type}")
            
        result = await service.generate_educational(
            topic=request.topic,
            content_type=request.content_type,
            additional_context=request.additional_context,
            size=request.size
        )
        
        return ImageResponse(
            url=result.url,
            revised_prompt=result.revised_prompt,
            size=result.size,
            style=result.style,
            prompt_used=result.prompt_used
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Educational image generation error: {e}")
        raise HTTPException(status_code=500, detail="Image generation failed")


@router.post("/lesson", response_model=List[ImageResponse])
async def generate_lesson_images(request: LessonImagesRequest):
    """
    Generate images for a complete lesson
    
    Creates visual content for the main topic and key concepts.
    Limited to max_images to manage costs.
    """
    try:
        service = await get_image_service()
        
        images = await service.generate_lesson_images(
            lesson_topic=request.lesson_topic,
            concepts=request.concepts,
            max_images=request.max_images
        )
        
        return [
            ImageResponse(
                url=img.url,
                revised_prompt=img.revised_prompt,
                size=img.size,
                style=img.style,
                prompt_used=img.prompt_used
            )
            for img in images
        ]
        
    except Exception as e:
        logger.error(f"Lesson images generation error: {e}")
        raise HTTPException(status_code=500, detail="Lesson image generation failed")


@router.get("/preview")
async def preview_prompt(
    topic: str = Query(..., description="Topic to visualize"),
    content_type: str = Query(default="concept_diagram", description="Content type")
):
    """
    Preview the prompt that would be sent to DALL-E
    
    Useful for debugging and understanding how prompts are constructed.
    """
    service = await get_image_service()
    
    if content_type not in EDUCATIONAL_PROMPTS:
        raise HTTPException(status_code=400, detail=f"Unknown content type: {content_type}")
        
    prompt = service.build_educational_prompt(topic, content_type)
    
    return {
        "topic": topic,
        "content_type": content_type,
        "generated_prompt": prompt,
        "recommended_size": "1792x1024 (landscape)",
        "recommended_style": "natural"
    }
