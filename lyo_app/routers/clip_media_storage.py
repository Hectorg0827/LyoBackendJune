"""Durable clip media storage and byte-range playback.

Uploads keep their stable /api/v1/media/file/... URL. If persistent object
storage is configured, clip bytes are saved outside Railway's ephemeral
container and streamed with HTTP Range support for seekable HTML5/Media3 video.
Chat/Test Prep/Classroom attachments retain their existing local storage path.
"""
import logging
import mimetypes
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from lyo_app.core.config import settings

log = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


def _provider():
    name = (getattr(settings, "storage_provider", "") or "").lower()
    if name in {"gcs", "google_cloud_storage"}:
        bucket = getattr(settings, "gcs_bucket", None) or getattr(settings, "storage_bucket", None)
        return ("gcs", bucket) if bucket else None
    if name in {"aws_s3", "s3", "cloudflare_r2", "r2"}:
        bucket = (
            (getattr(settings, "r2_bucket", None) if name in {"cloudflare_r2", "r2"} else None)
            or getattr(settings, "storage_bucket", None)
        )
        return ("r2" if name in {"cloudflare_r2", "r2"} else "s3", bucket) if bucket else None
    return None


@lru_cache(maxsize=2)
def _gcs_bucket(bucket_name: str):
    from google.cloud import storage

    return storage.Client(
        project=getattr(settings, "gcs_project_id", None) or None
    ).bucket(bucket_name)


@lru_cache(maxsize=2)
def _s3_client(provider: str):
    import boto3

    if provider == "r2":
        return boto3.client(
            "s3",
            endpoint_url=getattr(settings, "r2_endpoint", None),
            aws_access_key_id=getattr(settings, "r2_access_key", None),
            aws_secret_access_key=getattr(settings, "r2_secret_key", None),
            region_name="auto",
        )
    return boto3.client(
        "s3", region_name=getattr(settings, "aws_region", None) or "us-east-1"
    )


def _key(folder: str, name: str) -> str:
    return f"media/{folder}/{name}"


def save_clip_to_cloud(local_file: Path, folder: str, name: str, content_type: str) -> bool:
    """Upload a finished local clip to durable storage, if configured.

    A cloud write failure must not silently create a clip whose URL will 404
    after the next deployment. Caller removes the uncommitted local file.
    """
    config = _provider()
    if not config:
        log.warning("Clip uploaded without persistent object storage; configure STORAGE_PROVIDER/STORAGE_BUCKET or mount a Railway volume")
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

    def chunks() -> Iterator[bytes]:
        if provider == "gcs":
            for offset in range(start, end + 1, CHUNK_SIZE):
                yield blob.download_as_bytes(start=offset, end=min(end, offset + CHUNK_SIZE - 1))
        else:
            obj = client.get_object(
                Bucket=bucket_name, Key=key,
                Range=f"bytes={start}-{end}",
            )
            body = obj["Body"]
            try:
                for chunk in body.iter_chunks(chunk_size=CHUNK_SIZE):
                    if chunk:
                        yield chunk
            finally:
                body.close()

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Cache-Control": "public, max-age=3600",
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        chunks(),
        media_type=mime_type,
        status_code=206 if partial else 200,
        headers=headers,
    )
