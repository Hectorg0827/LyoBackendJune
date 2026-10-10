"""Regression coverage for long-lived, seekable Discover video uploads."""
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from lyo_app.routers import clip_media_storage as media


@pytest.mark.parametrize(
    "header,size,expected",
    [
        (None, 100, (0, 99, False)),
        ("bytes=0-", 100, (0, 99, True)),
        ("bytes=25-50", 100, (25, 50, True)),
        ("bytes=95-999", 100, (95, 99, True)),
        ("bytes=-10", 100, (90, 99, True)),
        ("bytes=-500", 100, (0, 99, True)),
    ],
)
def test_range_parsing(header, size, expected):
    assert media.parse_byte_range(header, size) == expected


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=8-4", "bytes=0-1,3-5", "items=0-1", "bytes=-0"])
def test_invalid_ranges_are_explicit_416(header):
    with pytest.raises(HTTPException) as exc:
        media.parse_byte_range(header, 100)
    assert exc.value.status_code == 416
    assert exc.value.headers["Content-Range"] == "bytes */100"


def test_cloud_clip_upload_uses_stable_key(monkeypatch, tmp_path):
    sample = tmp_path / "video.mp4"
    sample.write_bytes(b"video")
    captured = {}

    class Blob:
        def upload_from_filename(self, filename, content_type):
            captured["filename"] = filename
            captured["content_type"] = content_type

    class Bucket:
        def blob(self, key):
            captured["key"] = key
            return Blob()

    monkeypatch.setattr(media, "_provider", lambda: ("gcs", "test-bucket"))
    monkeypatch.setattr(media, "_gcs_bucket", lambda _: Bucket())
    assert media.save_clip_to_cloud(sample, "clips", "video.mp4", "video/mp4") is True
    assert captured == {
        "key": "media/clips/video.mp4",
        "filename": str(sample),
        "content_type": "video/mp4",
    }


def test_gcs_media_supports_http_partial_content(monkeypatch):
    class Blob:
        size = 10
        content_type = "video/mp4"

        def download_as_bytes(self, start, end):
            return b"0123456789"[start:end + 1]

    class Bucket:
        def get_blob(self, key):
            assert key == "media/clips/123.mp4"
            return Blob()

    monkeypatch.setattr(media, "_provider", lambda: ("gcs", "test-bucket"))
    monkeypatch.setattr(media, "_gcs_bucket", lambda _: Bucket())
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/media/file/clips/123.mp4",
        "headers": [(b"range", b"bytes=2-5")],
    })
    response = media.stream_clip_from_cloud("clips", "123.mp4", request)
    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["accept-ranges"] == "bytes"

    async def gather():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(chunks)

    assert asyncio.run(gather()) == b"2345"
