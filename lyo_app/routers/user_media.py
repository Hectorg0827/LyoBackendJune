"""
Simple authenticated media upload + public serving for user content
(chat attachments, reel videos, thumbnails, and post images).

This is the consumer-grade path every client uses via multipart POST —
no presigned URLs and no organization gating. Files land under the
local uploads directory; when cloud storage credentials are configured
the enhanced storage service can replace the disk write transparently.
Note Railway's container disk is ephemeral across redeploys, so cloud
storage should be configured for durable production media.
"""
import logging
import re
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from lyo_app.routers.clip_media_storage import save_clip_to_cloud, stream_clip_from_cloud

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/media", tags=["media"])

ALLOWED_TYPES = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/json": ".json",
}
MAX_VIDEO_BYTES = 200 * 1024 * 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
_CHUNK = 1024 * 1024
_FOLDER_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


def _media_root() -> Path:
    root = Path(getattr(settings, "upload_dir", None) or "uploads") / "media"
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post("/upload")
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    folder: str = Form("content"),
    current_user: User = Depends(get_current_user),
):
    """Upload supported media; returns a public, unguessable URL and API path."""
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported media type '{content_type}'. Allowed: {sorted(ALLOWED_TYPES)}",
        )
    if not _FOLDER_RE.match(folder):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid folder name")

    if content_type.startswith("video/"):
        max_bytes = MAX_VIDEO_BYTES
    elif content_type.startswith("image/"):
        max_bytes = MAX_IMAGE_BYTES
    else:
        max_bytes = MAX_DOCUMENT_BYTES
    name = f"{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"
    dest_dir = _media_root() / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name

    size = 0
    try:
        async with aiofiles.open(dest, "wb") as out:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large. Maximum size: {max_bytes // (1024 * 1024)}MB",
                    )
                await out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        logger.error(f"Media upload failed for user {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload failed")

    if folder == "clips":
        try:
            # A stable URL must point to durable bytes, not Railway's ephemeral
            # container filesystem. Keep the local path only when the app
            # deliberately has no object-storage backend configured.
            stored_in_cloud = await run_in_threadpool(
                save_clip_to_cloud, dest, folder, name, content_type
            )
            if stored_in_cloud:
                dest.unlink(missing_ok=True)
        except Exception:
            dest.unlink(missing_ok=True)
            logger.exception("Persistent clip upload failed for user %s", current_user.id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Clip storage is unavailable. Please retry the upload.",
            )

    path = f"/api/v1/media/file/{folder}/{name}"
    absolute = str(request.base_url).rstrip("/") + path
    logger.info(f"Media uploaded by user {current_user.id}: {path} ({size} bytes)")
    return {
        "success": True,
        "url": absolute,
        "path": path,
        "contentType": content_type,
        "size": size,
    }


@router.get("/file/{folder}/{name}")
async def serve_media(folder: str, name: str, request: Request):
    """Public media URL. Persisted clips are seekable and survive redeploys."""
    if not _FOLDER_RE.match(folder) or "/" in name or ".." in name or name.startswith("."):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    path = _media_root() / folder / name
    if path.is_file():
        return FileResponse(path)
    if folder == "clips":
        try:
            response = await run_in_threadpool(stream_clip_from_cloud, folder, name, request)
            if response is not None:
                return response
        except HTTPException:
            raise
        except Exception:
            logger.exception("Unable to stream clip from cloud: %s", name)
            raise HTTPException(status_code=503, detail="Video storage temporarily unavailable")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
