"""
Video Generation Routes — REST API for Runway Gen-4.5 Video
Endpoints for text-to-video, image-to-video, and task polling.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging

from .service import (
    VideoService,
    get_video_service,
    VideoModel,
    VideoRatio,
    VideoDuration,
    GeneratedVideo,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/videos", tags=["Video Generation"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class TextToVideoRequest(BaseModel):
    """Generate a video from a text prompt."""
    prompt: str = Field(..., min_length=5, max_length=2000, description="Descriptive text prompt")
    duration: Optional[int] = Field(default=None, description="Duration in seconds: 4, 6, or 8")
    ratio: Optional[str] = Field(default=None, description="Aspect ratio: '1280:720' or '720:1280'")
    model: Optional[str] = Field(default=None, description="Model ID (default: gen4.5)")
    seed: Optional[int] = Field(default=None, description="Reproducibility seed")
    wait: bool = Field(default=False, description="If true, block until video is ready (can take minutes)")


class ImageToVideoRequest(BaseModel):
    """Animate an image into a video."""
    prompt: str = Field(..., min_length=5, max_length=2000, description="Motion / scene description")
    image_url: str = Field(..., description="URL of the source image")
    duration: Optional[int] = Field(default=None, description="Duration in seconds: 4, 6, or 8")
    ratio: Optional[str] = Field(default=None, description="Aspect ratio")
    model: Optional[str] = Field(default=None, description="Model ID")
    seed: Optional[int] = Field(default=None, description="Reproducibility seed")
    wait: bool = Field(default=False, description="Block until ready")


class VideoResponse(BaseModel):
    """Video generation result."""
    task_id: str = Field(..., description="Runway task ID for polling")
    status: str = Field(..., description="PENDING | THROTTLED | RUNNING | SUCCEEDED | FAILED | TIMEOUT")
    url: Optional[str] = Field(default=None, description="Video download URL (when SUCCEEDED)")
    prompt_used: str = Field(default="")
    model: str = Field(default="")
    ratio: str = Field(default="")
    duration: int = Field(default=0)
    created_at: str = Field(default="")
    failure_reason: Optional[str] = Field(default=None)


class VideoTaskStatusResponse(BaseModel):
    """Polling response."""
    task_id: str
    status: str
    url: Optional[str] = None
    failure_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
async def video_health():
    """Check Runway video service health."""
    import os
    api_key = os.getenv("RUNWAYML_API_SECRET", "")
    return {
        "status": "healthy" if api_key else "unconfigured",
        "service": "video_generation",
        "provider": "runway",
        "model": VideoModel.GEN4_5.value,
        "api_configured": bool(api_key),
    }


@router.post("/text-to-video", response_model=VideoResponse)
async def text_to_video(request: TextToVideoRequest):
    """
    Generate a video from a text prompt via Runway Gen-4.5.

    Returns immediately with a `task_id` (set `wait=true` to block until done).
    Poll `/api/v1/videos/status/{task_id}` for progress.
    """
    try:
        service = await get_video_service()
        result = await service.generate_text_to_video(
            prompt=request.prompt,
            duration=request.duration,
            ratio=request.ratio,
            model=request.model,
            seed=request.seed,
            wait=request.wait,
        )
        return VideoResponse(
            task_id=result.task_id,
            status=result.status,
            url=result.url,
            prompt_used=result.prompt_used,
            model=result.model,
            ratio=result.ratio,
            duration=result.duration,
            created_at=result.created_at,
            failure_reason=result.failure_reason,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("🎬 text_to_video error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Video generation failed: {e}")


@router.post("/image-to-video", response_model=VideoResponse)
async def image_to_video(request: ImageToVideoRequest):
    """
    Animate an image into a video via Runway Gen-4.5.

    Provide an `image_url` plus a motion/scene `prompt`.
    """
    try:
        service = await get_video_service()
        result = await service.generate_image_to_video(
            prompt=request.prompt,
            image_url=request.image_url,
            duration=request.duration,
            ratio=request.ratio,
            model=request.model,
            seed=request.seed,
            wait=request.wait,
        )
        return VideoResponse(
            task_id=result.task_id,
            status=result.status,
            url=result.url,
            prompt_used=result.prompt_used,
            model=result.model,
            ratio=result.ratio,
            duration=result.duration,
            created_at=result.created_at,
            failure_reason=result.failure_reason,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("🎬 image_to_video error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Video generation failed: {e}")


@router.get("/status/{task_id}", response_model=VideoTaskStatusResponse)
async def get_video_status(task_id: str):
    """
    Poll Runway for the current status of a video generation task.

    Returns `SUCCEEDED` with a `url` when the video is ready.
    """
    try:
        service = await get_video_service()
        result = await service.get_task_status(task_id)
        return VideoTaskStatusResponse(
            task_id=result.task_id,
            status=result.status,
            url=result.url,
            failure_reason=result.failure_reason,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("🎬 get_video_status error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Status check failed: {e}")


@router.get("/models")
async def list_video_models():
    """List available video generation models and options."""
    return {
        "models": [
            {
                "id": VideoModel.GEN4_5.value,
                "name": "Runway Gen-4.5",
                "description": "Latest Runway model — cinematic quality video generation",
                "durations": [d.value for d in VideoDuration],
                "ratios": [r.value for r in VideoRatio],
            }
        ]
    }
