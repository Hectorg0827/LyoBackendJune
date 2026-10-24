"""Durable clip media storage and byte-range playback.

Uploads keep their stable /api/v1/media/file/... URL. If persistent object
storage is configured, clip bytes are saved outside Railway's ephemeral
container and streamed with HTTP Range support for seekable HTML5/Media3 video.
Chat/Test Prep/Classroom attachments retain their existing local storage path.
"""
import mimetypes
import os
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator, Optional
from urllib.parse import urlsplit

import anyio
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from lyo_app.core.config import settings

CHUNK_SIZE = 1024 * 1024
FIRST_CHUNK_SIZE = 64 * 1024
DURABLE_MEDIA_FOLDERS = {"clips", "clip_thumbnails"}
# One value per running process. Release checks read it from media responses
# to prove a URL was served by a new deployment or by a second replica.
INSTANCE_ID = uuid.uuid4().hex[:12]
MEDIA_PATH = re.compile(
    r"^/api/v1/media/file/(clips|clip_thumbnails)/([a-f0-9]{32}\.(mp4|mov|webm|jpg|png|webp|heic))$"
)
# The upload endpoint stores any allowed type in any folder, so an image can
# sit in "clips". Only a video there may become a clip's video.
FOLDER_EXTENSIONS = {"clips": {"mp4", "mov", "webm"}, "clip_thumbnails": {"jpg", "png", "webp", "heic"}}


def _provider():
    name = (getattr(settings, "discover_storage_provider", None) or getattr(settings, "storage_provider", "") or "").strip().lower()
    discover_bucket = getattr(settings, "discover_storage_bucket", None)
    if name == "local":
        environment = (getattr(settings, "environment", "") or "").lower()
        if environment not in {"development", "dev", "test", "testing"} or os.getenv("RAILWAY_ENVIRONMENT_ID"):
            raise RuntimeError("Discover uploads require durable object storage in deployed environments")
        return None
    if name in {"gcs", "google_cloud_storage"}:
        bucket = discover_bucket or getattr(settings, "gcs_bucket", None) or getattr(settings, "storage_bucket", None)
        provider = "gcs"
    elif name in {"aws_s3", "s3", "cloudflare_r2", "r2"}:
        bucket = (
            discover_bucket
            or (getattr(settings, "r2_bucket", None) if name in {"cloudflare_r2", "r2"} else None)
            or getattr(settings, "storage_bucket", None)
        )
        provider = "r2" if name in {"cloudflare_r2", "r2"} else "s3"
        if provider == "r2" and not all(getattr(settings, key, None) for key in ("r2_endpoint", "r2_access_key", "r2_secret_key")):
            raise RuntimeError("R2 endpoint and credentials must be configured for Discover media")
    else:
        raise RuntimeError("Select a supported Discover storage provider")
    if not bucket or not bucket.strip():
        raise RuntimeError("Discover storage bucket must be configured")
    return provider, bucket.strip()


@lru_cache(maxsize=2)
def _gcs_bucket(bucket_name: str):
    from google.cloud import storage

    return storage.Client(
        project=getattr(settings, "gcs_project_id", None) or None
    ).bucket(bucket_name)


@lru_cache(maxsize=2)
def _s3_client(provider: str):
    import boto3
    from botocore.config import Config

    if provider == "r2":
        return boto3.client(
            "s3",
            endpoint_url=getattr(settings, "r2_endpoint", None),
            aws_access_key_id=getattr(settings, "r2_access_key", None),
            aws_secret_access_key=getattr(settings, "r2_secret_key", None),
            region_name="auto",
        )
    return boto3.client(
        "s3",
        region_name=getattr(settings, "discover_s3_region", None) or getattr(settings, "aws_region", None) or "us-east-1",
        endpoint_url=getattr(settings, "discover_s3_endpoint_url", None) or getattr(settings, "aws_endpoint_url", None),
        aws_access_key_id=getattr(settings, "discover_s3_access_key_id", None) or getattr(settings, "aws_access_key_id", None),
        aws_secret_access_key=getattr(settings, "discover_s3_secret_access_key", None) or getattr(settings, "aws_secret_access_key", None),
        config=Config(s3={"addressing_style": getattr(settings, "discover_s3_addressing_style", None) or getattr(settings, "aws_s3_addressing_style", "auto")}),
    )


def _key(folder: str, name: str) -> str:
    return f"media/{folder}/{name}"


def save_clip_to_cloud(local_file: Path, folder: str, name: str, content_type: str) -> bool:
    """Upload finished Discover media; local storage is an explicit dev option.

    A cloud write failure must not silently create a clip whose URL will 404
    after the next deployment. Caller removes the uncommitted local file.
    """
    config = _provider()
    if not config:
        return False
    provider, bucket_name = config
    key = _key(folder, name)
    if provider == "gcs":
        blob = _gcs_bucket(bucket_name).blob(key)
        blob.upload_from_filename(str(local_file), content_type=content_type)
    else:
        _s3_client(provider).upload_file(
            str(local_file), bucket_name, key,
            ExtraArgs={"ContentType": content_type},
        )
    return True


def media_path_parts(url: str | None) -> Optional[tuple[str, str]]:
    """(folder, name) for a URL that points at this API's durable media, else None."""
    match = MEDIA_PATH.fullmatch(urlsplit(url or "").path)
    if not match or match.group(3) not in FOLDER_EXTENSIONS[match.group(1)]:
        return None
    return match.group(1), match.group(2)


def stat_durable_media(folder: str, name: str, local_root: Path) -> Optional[int]:
    """Size in bytes of stored Discover media, or None when nothing is there.

    Publishing checks this so a clip can never point at an upload that does
    not exist. Storage errors propagate: "could not check" is not "missing".
    With cloud storage configured only the bucket counts: a file on this
    container's disk is exactly what a redeploy or another replica lacks.
    """
    config = _provider()
    if not config:
        local = local_root / folder / name
        return local.stat().st_size if local.is_file() else None
    provider, bucket_name = config
    key = _key(folder, name)
    if provider == "gcs":
        blob = _gcs_bucket(bucket_name).get_blob(key)
        return int(blob.size or 0) if blob is not None else None
    from botocore.exceptions import ClientError

    try:
        head = _s3_client(provider).head_object(Bucket=bucket_name, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise
    return int(head.get("ContentLength", 0))


def parse_byte_range(header: str | None, size: int) -> tuple[int, int, bool]:
    """HTTP bytes range; support normal and suffix requests, reject invalid ones."""
    if size < 1:
        raise HTTPException(status_code=404, detail="Empty video")
    if not header:
        return 0, size - 1, False
    if not header.startswith("bytes=") or "," in header:
        raise HTTPException(status_code=416, detail="Unsupported range", headers={"Content-Range": f"bytes */{size}"})
    try:
        spec = header[len("bytes="):]
        first, last = spec.split("-", 1)
        if not first and last:
            count = int(last)
            if count <= 0:
                raise ValueError("invalid suffix")
            start, end = max(0, size - count), size - 1
        else:
            start = int(first)
            end = min(size - 1, int(last)) if last else size - 1
        if start < 0 or start >= size or end < start:
            raise ValueError("range out of bounds")
        return start, end, True
    except (ValueError, TypeError):
        raise HTTPException(status_code=416, detail="Invalid range", headers={"Content-Range": f"bytes */{size}"})


class _CloudStreamingResponse(StreamingResponse):
    """Close an opened upstream body even if the client disconnects before iteration."""

    def __init__(self, *args, close: Callable[[], None], **kwargs):
        super().__init__(*args, **kwargs)
        self._close_upstream = close

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(self._close_upstream)


def stream_clip_from_cloud(folder: str, name: str, request: Request):
    """Return a range-aware response from GCS/S3/R2, or None for local media."""
    config = _provider()
    if not config:
        return None
    provider, bucket_name = config
    key = _key(folder, name)
    mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"

    if provider == "gcs":
        blob = _gcs_bucket(bucket_name).get_blob(key)
        if blob is None:
            return None
        size = int(blob.size or 0)
        mime_type = blob.content_type or mime_type
    else:
        from botocore.exceptions import ClientError

        client = _s3_client(provider)
        try:
            head = client.head_object(Bucket=bucket_name, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        size = int(head.get("ContentLength", 0))
        mime_type = head.get("ContentType") or mime_type

    start, end, partial = parse_byte_range(request.headers.get("range"), size)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        # Names are random and never rewritten, so a cached copy stays valid;
        # swiping back to a clip then plays from the browser's cache.
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Media-Instance": INSTANCE_ID,
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    status_code = 206 if partial else 200
    if request.method == "HEAD":
        # Players probe with HEAD for length and range support before
        # playing; answer from metadata alone rather than reading the video.
        return Response(status_code=status_code, headers=headers, media_type=mime_type)

    first_end = min(end, start + FIRST_CHUNK_SIZE - 1)
    close = lambda: None
    # Fetch a bounded first chunk before StreamingResponse commits 200/206.
    # Credential/read failures can then become a retryable 503 at the router.
    if provider == "gcs":
        first = blob.download_as_bytes(start=start, end=first_end)
    else:
        obj = client.get_object(Bucket=bucket_name, Key=key, Range=f"bytes={start}-{end}")
        body = obj["Body"]
        closed = False

        def close():
            nonlocal closed
            if not closed:
                closed = True
                body.close()

        try:
            if int(obj.get("ContentLength", end - start + 1)) != end - start + 1:
                raise OSError("Unexpected upstream video length")
            first = body.read(first_end - start + 1)
        except BaseException:
            close()
            raise
    if len(first) != first_end - start + 1:
        close()
        raise OSError("Incomplete initial video read")

    def chunks() -> Iterator[bytes]:
        try:
            yield first
            for offset in range(first_end + 1, end + 1, CHUNK_SIZE):
                count = min(CHUNK_SIZE, end - offset + 1)
                if provider == "gcs":
                    chunk = blob.download_as_bytes(start=offset, end=offset + count - 1)
                else:
                    chunk = body.read(count)
                if len(chunk) != count:
                    raise OSError("Incomplete video stream")
                yield chunk
        finally:
            close()

    return _CloudStreamingResponse(
        chunks(),
        close=close,
        media_type=mime_type,
        status_code=status_code,
        headers=headers,
    )


# Media a moderator removed. /api/v1/media/file only serves media/<folder>/
# in the bucket and <root>/<folder>/ on disk, so a removed file's URL stops
# working while its bytes stay here for a restore.
REMOVED_PREFIX = "removed"
LOCAL_REMOVED_DIR = ".removed"


def set_media_removed(folder: str, name: str, local_root: Path, removed: bool) -> bool:
    """Move stored Discover media out of public reach, or back into it.

    Returns False when the file is in neither place. Moving twice is a no-op,
    so a retried decision cannot fail on the second try. Storage errors
    propagate. With cloud storage the container's own copy of the file, if
    the upload left one, is deleted on removal: it would still be served.
    """
    public_local = local_root / folder / name
    removed_local = local_root / LOCAL_REMOVED_DIR / folder / name
    config = _provider()
    if not config:
        source, target = (public_local, removed_local) if removed else (removed_local, public_local)
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            return True
        return target.is_file()
    if removed:
        public_local.unlink(missing_ok=True)
    provider, bucket_name = config
    public_key, removed_key = _key(folder, name), f"{REMOVED_PREFIX}/{folder}/{name}"
    source, target = (public_key, removed_key) if removed else (removed_key, public_key)
    if provider == "gcs":
        bucket = _gcs_bucket(bucket_name)
        blob = bucket.get_blob(source)
        if blob is None:
            return bucket.get_blob(target) is not None
        bucket.copy_blob(blob, bucket, target)
        blob.delete()
        return True
    from botocore.exceptions import ClientError

    client = _s3_client(provider)

    def exists(key: str) -> bool:
        try:
            client.head_object(Bucket=bucket_name, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    if not exists(source):
        return exists(target)
    client.copy_object(Bucket=bucket_name, Key=target, CopySource={"Bucket": bucket_name, "Key": source})
    client.delete_object(Bucket=bucket_name, Key=source)
    return True


def delete_media(folder: str, name: str, local_root: Path) -> None:
    """Delete stored Discover media wherever it is, public or removed."""
    for path in (local_root / folder / name, local_root / LOCAL_REMOVED_DIR / folder / name):
        path.unlink(missing_ok=True)
    config = _provider()
    if not config:
        return
    provider, bucket_name = config
    keys = (_key(folder, name), f"{REMOVED_PREFIX}/{folder}/{name}")
    if provider == "gcs":
        bucket = _gcs_bucket(bucket_name)
        for key in keys:
            blob = bucket.get_blob(key)
            if blob is not None:
                blob.delete()
        return
    client = _s3_client(provider)
    for key in keys:
        client.delete_object(Bucket=bucket_name, Key=key)  # S3 treats a missing key as deleted
