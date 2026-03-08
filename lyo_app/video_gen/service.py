"""
Video Generation Service — Runway Gen-4.5 Integration

Provides AI-powered video generation for Lyo's educational platform.
Supports text-to-video and image-to-video via Runway's official SDK.
Tasks are async (poll-based): create → poll status → download URL.
"""

import os
import logging
import asyncio
from typing import Optional, Dict, Any, Literal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class VideoModel(str, Enum):
    GEN4_5 = "gen4.5"


class VideoRatio(str, Enum):
    LANDSCAPE = "1280:720"
    PORTRAIT = "720:1280"


class VideoDuration(int, Enum):
    SHORT = 4
    MEDIUM = 6
    LONG = 8


@dataclass
class VideoConfig:
    api_key: str = ""
    default_model: str = VideoModel.GEN4_5.value
    default_ratio: str = VideoRatio.LANDSCAPE.value
    default_duration: int = VideoDuration.MEDIUM.value
    poll_interval_sec: float = 5.0
    max_poll_time_sec: float = 300.0  # 5 min timeout


@dataclass
class GeneratedVideo:
    task_id: str
    status: str  # PENDING, THROTTLED, RUNNING, SUCCEEDED, FAILED
    url: Optional[str] = None
    prompt_used: str = ""
    model: str = ""
    ratio: str = ""
    duration: int = 0
    created_at: str = ""
    failure_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class VideoService:
    """
    Runway video generation service.

    Usage:
        svc = await get_video_service()
        result = await svc.generate_text_to_video("A glowing neuron firing")
    """

    def __init__(self, config: Optional[VideoConfig] = None):
        self.config = config or VideoConfig()
        self._client = None
        self._initialized = False

    async def initialize(self):
        """Lazy-init the Runway SDK client."""
        if self._initialized:
            return

        api_key = self.config.api_key or os.getenv("RUNWAYML_API_SECRET", "")
        if not api_key:
            raise RuntimeError(
                "Runway API key not found.  Set RUNWAYML_API_SECRET in your environment or .env file."
            )

        try:
            from runwayml import RunwayML
            self._client = RunwayML(api_key=api_key)
            self._initialized = True
            logger.info("🎬 Runway VideoService initialized (model=%s)", self.config.default_model)
        except ImportError:
            raise RuntimeError("runwayml package not installed. Run: pip install runwayml")

    async def close(self):
        self._client = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Text → Video
    # ------------------------------------------------------------------

    async def generate_text_to_video(
        self,
        prompt: str,
        *,
        duration: Optional[int] = None,
        ratio: Optional[str] = None,
        model: Optional[str] = None,
        seed: Optional[int] = None,
        wait: bool = True,
    ) -> GeneratedVideo:
        """
        Generate video from a text prompt.

        Args:
            prompt: descriptive text (max ~500 chars recommended)
            duration: 4 | 6 | 8 seconds
            ratio: "1280:720" or "720:1280"
            model: "gen4.5" (default)
            seed: optional reproducibility seed
            wait: if True, poll until complete; otherwise return immediately with task_id
        """
        await self.initialize()

        dur = duration or self.config.default_duration
        rat = ratio or self.config.default_ratio
        mdl = model or self.config.default_model

        logger.info("🎬 Runway text_to_video | model=%s  dur=%ss  ratio=%s  prompt=%.80s…", mdl, dur, rat, prompt)

        # SDK call (sync) — run in executor so we don't block the event loop
        loop = asyncio.get_running_loop()
        task = await loop.run_in_executor(
            None,
            lambda: self._client.text_to_video.create(
                model=mdl,
                prompt_text=prompt,
                duration=dur,
                ratio=rat,
                **({"seed": seed} if seed is not None else {}),
            ),
        )

        result = GeneratedVideo(
            task_id=task.id,
            status=task.status or "PENDING",
            prompt_used=prompt,
            model=mdl,
            ratio=rat,
            duration=dur,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if not wait:
            return result

        # Poll until done
        return await self._poll_task(result)

    # ------------------------------------------------------------------
    # Image → Video
    # ------------------------------------------------------------------

    async def generate_image_to_video(
        self,
        prompt: str,
        image_url: str,
        *,
        duration: Optional[int] = None,
        ratio: Optional[str] = None,
        model: Optional[str] = None,
        seed: Optional[int] = None,
        wait: bool = True,
    ) -> GeneratedVideo:
        """Generate video from an image + text prompt."""
        await self.initialize()

        dur = duration or self.config.default_duration
        rat = ratio or self.config.default_ratio
        mdl = model or self.config.default_model

        logger.info("🎬 Runway image_to_video | model=%s  dur=%ss  prompt=%.80s…", mdl, dur, prompt)

        loop = asyncio.get_running_loop()
        task = await loop.run_in_executor(
            None,
            lambda: self._client.image_to_video.create(
                model=mdl,
                prompt_text=prompt,
                prompt_image=image_url,
                duration=dur,
                ratio=rat,
                **({"seed": seed} if seed is not None else {}),
            ),
        )

        result = GeneratedVideo(
            task_id=task.id,
            status=task.status or "PENDING",
            prompt_used=prompt,
            model=mdl,
            ratio=rat,
            duration=dur,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if not wait:
            return result

        return await self._poll_task(result)

    # ------------------------------------------------------------------
    # Poll / Status
    # ------------------------------------------------------------------

    async def get_task_status(self, task_id: str) -> GeneratedVideo:
        """Fetch current status of a Runway task."""
        await self.initialize()

        loop = asyncio.get_running_loop()
        task = await loop.run_in_executor(
            None,
            lambda: self._client.tasks.retrieve(id=task_id),
        )

        return GeneratedVideo(
            task_id=task.id,
            status=task.status or "UNKNOWN",
            url=getattr(task, "output", [None])[0] if getattr(task, "output", None) else None,
            prompt_used="",
            model=self.config.default_model,
            ratio=self.config.default_ratio,
            duration=self.config.default_duration,
            created_at=getattr(task, "created_at", "") or "",
            failure_reason=getattr(task, "failure", None),
        )

    async def _poll_task(self, result: GeneratedVideo) -> GeneratedVideo:
        """Poll a Runway task until SUCCEEDED / FAILED or timeout."""
        elapsed = 0.0
        while elapsed < self.config.max_poll_time_sec:
            await asyncio.sleep(self.config.poll_interval_sec)
            elapsed += self.config.poll_interval_sec

            loop = asyncio.get_running_loop()
            task = await loop.run_in_executor(
                None,
                lambda: self._client.tasks.retrieve(id=result.task_id),
            )
            result.status = task.status or "UNKNOWN"

            if task.status == "SUCCEEDED":
                output = getattr(task, "output", None)
                if output and len(output) > 0:
                    result.url = output[0]
                logger.info("🎬 Runway task %s SUCCEEDED → %s", result.task_id, result.url)
                return result

            if task.status == "FAILED":
                result.failure_reason = getattr(task, "failure", "Unknown failure")
                logger.error("🎬 Runway task %s FAILED: %s", result.task_id, result.failure_reason)
                return result

            logger.debug("🎬 Runway poll %s → %s (%.0fs)", result.task_id, task.status, elapsed)

        result.status = "TIMEOUT"
        result.failure_reason = f"Timed out after {self.config.max_poll_time_sec}s"
        logger.warning("🎬 Runway task %s timed out", result.task_id)
        return result


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_video_service: Optional[VideoService] = None


async def get_video_service() -> VideoService:
    global _video_service
    if _video_service is None:
        _video_service = VideoService()
        await _video_service.initialize()
    return _video_service
