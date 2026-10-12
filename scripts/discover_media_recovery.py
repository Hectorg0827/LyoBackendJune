"""Copy reachable legacy Discover media to its original durable key before release.

Read-only database access; never rewrites clip records or overwrites bucket data.
Only fetches validated media paths from the fixed serving API, never arbitrary URLs.
"""
import asyncio
import hashlib
import json
import mimetypes
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
import httpx
from botocore.exceptions import ClientError

from lyo_app.core.config import settings
from lyo_app.routers.clip_media_storage import _provider, _s3_client, _key

MEDIA_PATH = re.compile(r"^/api/v1/media/file/(clips|clip_thumbnails)/([a-f0-9]{32}\.(?:mp4|mov|webm|jpg|jpeg|png|webp|heic))$")
SOURCE = "https://api.lyoai.app"
MAX_BYTES = 200 * 1024 * 1024


def recover_object(url, bucket, cloud, source):
    path = urlsplit(url).path
    match = MEDIA_PATH.fullmatch(path)
    if not match:
        return {"status": "external_or_other_path"}
    folder, name = match.groups()
    key = _key(folder, name)
    try:
        cloud.head_object(Bucket=bucket, Key=key)
        return {"status": "already_durable", "key": key}
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
            raise
    with source.stream("GET", SOURCE + path, follow_redirects=False) as response:
        if response.status_code == 404:
            return {"status": "original_missing", "key": key}
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";")[0] or mimetypes.guess_type(name)[0]
        if not content_type or not content_type.startswith(("video/", "image/")):
            raise RuntimeError("Unexpected source media type")
        size = 0
        digest = hashlib.sha256()
        with tempfile.NamedTemporaryFile(suffix=Path(name).suffix) as temp:
            for chunk in response.iter_bytes(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise RuntimeError("Legacy media exceeds upload limit")
                digest.update(chunk)
                temp.write(chunk)
            temp.flush()
            if not size or size != int(response.headers.get("content-length", size)):
                raise RuntimeError("Incomplete source media")
            cloud.upload_file(temp.name, bucket, key, ExtraArgs={"ContentType": content_type})
    body = cloud.get_object(Bucket=bucket, Key=key)["Body"]
    stored_digest = hashlib.sha256()
    try:
        for chunk in body.iter_chunks(chunk_size=1024 * 1024):
            stored_digest.update(chunk)
    finally:
        body.close()
    if stored_digest.digest() != digest.digest():
        raise RuntimeError("Recovered media failed byte verification")
    return {"status": "recovered", "key": key, "bytes": size, "sha256": digest.hexdigest()}


async def main():
    if not settings.testing or os.getenv("DISCOVER_VALIDATION_ENABLED") != "true":
        raise RuntimeError("Recovery runs only on the isolated validation service")
    provider, bucket = _provider()
    if provider != "s3":
        raise RuntimeError("This release recovery targets the configured S3-compatible bucket")
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn, timeout=15)
    try:
        async with connection.transaction(readonly=True):
            rows = await connection.fetch("SELECT id, video_url, thumbnail_url FROM clips ORDER BY id")
    finally:
        await connection.close()
    results = []
    cloud = _s3_client(provider)
    with httpx.Client(timeout=30, headers={"Connection": "close"}) as source:
        for row in rows:
            for field in ("video_url", "thumbnail_url"):
                if not row[field]:
                    continue
                result = await asyncio.to_thread(recover_object, row[field], bucket, cloud, source)
                results.append({"clip_id": row["id"], "field": field, **result})
    counts = {status: sum(r["status"] == status for r in results) for status in ("recovered", "already_durable", "original_missing", "external_or_other_path")}
    print("DISCOVER_MEDIA_RECOVERY=" + json.dumps({"read_only_database": True, "clip_rows": len(rows), "counts": counts, "objects": results}, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
