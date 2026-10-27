"""Every user upload lives in object storage, and a deployment refuses to
start without it.

Railway's container disk is wiped on each deploy and is not shared between
replicas. Chat, Test Prep and Classroom attachments and avatars used to stay
there, so they disappeared; now they are stored, served and read back by the
AI from the same bucket as Discover clips.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from lyo_app.ai import multimodal
from lyo_app.ai.schemas.lyo2 import InputModality, MediaRef
from lyo_app.routers import clip_media_storage as media
from lyo_app.routers import user_media


class Bucket:
    """An S3-compatible bucket in memory."""

    def __init__(self):
        self.objects = {}

    def upload_file(self, path, bucket, key, ExtraArgs):
        self.objects[key] = (Path(path).read_bytes(), ExtraArgs["ContentType"])

    def _get(self, key):
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return self.objects[key]

    def head_object(self, Bucket, Key):
        data, content_type = self._get(Key)
        return {"ContentLength": len(data), "ContentType": content_type}

    def get_object(self, Bucket, Key, Range=None):
        data, _ = self._get(Key)
        if Range:
            start, end = map(int, Range.removeprefix("bytes=").split("-"))
            data = data[start:end + 1]
        return {"Body": StreamingBody(io.BytesIO(data), len(data)), "ContentLength": len(data)}


@pytest.fixture
def bucket(monkeypatch, tmp_path):
    fake = Bucket()
    monkeypatch.setattr(media, "_provider", lambda: ("s3", "uploads-bucket"))
    monkeypatch.setattr(media, "_s3_client", lambda _: fake)
    monkeypatch.setattr(user_media, "_media_root", lambda: tmp_path / "media")
    monkeypatch.setattr(multimodal, "settings", SimpleNamespace(upload_dir=str(tmp_path)))
    return fake


@pytest.fixture
def client(bucket):
    app = FastAPI()
    app.include_router(user_media.router)
    app.dependency_overrides[user_media.get_current_user] = lambda: SimpleNamespace(id=7)
    with TestClient(app) as client:
        yield client


def test_a_chat_attachment_survives_losing_the_container_disk(client, bucket, tmp_path):
    uploaded = client.post("/api/v1/media/upload", data={"folder": "chat"},
                           files={"file": ("notes.txt", b"photosynthesis notes", "text/plain")})
    assert uploaded.status_code == 200, uploaded.text
    path = uploaded.json()["path"]
    assert not any(p.is_file() for p in tmp_path.rglob("*")), "nothing is left on the container disk"

    served = client.get(path)
    assert served.status_code == 200
    assert served.content == b"photosynthesis notes"
    assert served.headers["content-type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_the_ai_reads_an_attachment_from_the_bucket(client, bucket):
    uploaded = client.post("/api/v1/media/upload", data={"folder": "test-prep"},
                           files={"file": ("photo.png", b"fake-png", "image/png")})
    uri = uploaded.json()["url"]
    parts = await multimodal.load_media_attachments(
        [MediaRef(modality=InputModality.IMAGE, uri=uri, mime_type="image/png", name="photo.png")]
    )
    assert base64.b64decode(parts[0]["data"]) == b"fake-png"


@pytest.mark.asyncio
async def test_an_attachment_missing_from_the_bucket_is_gone(bucket):
    ref = MediaRef(modality=InputModality.IMAGE, uri="/api/v1/media/file/chat/" + "a" * 32 + ".png",
                   mime_type="image/png", name="gone.png")
    assert await multimodal.load_media_attachments([ref], missing_ok=True) == []
    with pytest.raises(HTTPException) as error:
        await multimodal.load_media_attachments([ref])
    assert error.value.status_code == 410


@pytest.mark.asyncio
async def test_an_oversized_attachment_is_refused_before_downloading(bucket, monkeypatch):
    name = "b" * 32 + ".pdf"
    bucket.objects[f"media/chat/{name}"] = (b"x" * (multimodal.MAX_ATTACHMENT_BYTES + 1), "application/pdf")
    monkeypatch.setattr(bucket, "get_object", lambda **_: pytest.fail("downloaded an oversized file"))
    ref = MediaRef(modality=InputModality.DOCUMENT, uri=f"/api/v1/media/file/chat/{name}",
                   mime_type="application/pdf", name="big.pdf")
    with pytest.raises(HTTPException) as error:
        await multimodal.load_media_attachments([ref])
    assert error.value.status_code == 413


def _settings(**values):
    return SimpleNamespace(**{"storage_provider": "gcs", "environment": "production", **values})


@pytest.mark.parametrize("configured", [
    _settings(storage_provider=""),
    _settings(storage_provider="gcs"),  # no bucket
    _settings(storage_provider="local"),
    _settings(storage_provider="local", environment="development"),  # on Railway
    _settings(storage_provider="cloudflare_r2", storage_bucket="b"),  # no R2 credentials
])
def test_a_deployment_without_durable_storage_refuses_to_start(monkeypatch, configured):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "production-environment")
    monkeypatch.setattr(media, "settings", configured)
    with pytest.raises(RuntimeError, match="Refusing to start"):
        media.check_storage_at_startup()


def test_a_deployment_with_a_bucket_starts(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "production-environment")
    monkeypatch.setattr(media, "settings", _settings(storage_provider="aws_s3", storage_bucket="lyo-uploads"))
    assert media.check_storage_at_startup() == ("s3", "lyo-uploads")


def test_development_may_start_without_cloud_storage(monkeypatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    monkeypatch.setattr(media, "settings", _settings(storage_provider="local", environment="development"))
    assert media.check_storage_at_startup() is None
    monkeypatch.setattr(media, "settings", _settings(storage_provider="gcs", environment="development"))
    assert media.check_storage_at_startup() is None  # warns, still starts


def test_the_app_does_not_start_in_production_without_storage(monkeypatch):
    from lyo_app.enhanced_main import app

    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "production-environment")
    monkeypatch.setattr(media, "settings", _settings(storage_provider="local"))
    with pytest.raises(RuntimeError, match="Refusing to start"):
        with TestClient(app):
            pass


@pytest.mark.asyncio
async def test_legacy_storage_never_falls_back_to_the_container_disk(monkeypatch, tmp_path):
    from lyo_app.storage import enhanced_storage

    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "production-environment")
    monkeypatch.setattr(enhanced_storage, "settings", SimpleNamespace(upload_dir=str(tmp_path)))
    system = enhanced_storage.EnhancedStorageSystem()
    with pytest.raises(HTTPException):
        await system._upload_to_storage(b"data", "org_1/uploads/file.txt")
    assert not any(p.is_file() for p in tmp_path.rglob("*"))
