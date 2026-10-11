"""Exercise the public media contract, including failed first reads and disconnects."""
import asyncio
import io
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.requests import ClientDisconnect

from lyo_app.routers import clip_media_storage as media
from lyo_app.routers import user_media


@pytest.fixture
def client(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(user_media.router)
    app.dependency_overrides[user_media.get_current_user] = lambda: SimpleNamespace(id=123)
    monkeypatch.setattr(user_media, "_media_root", lambda: tmp_path)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("provider", ["gcs", "s3", "r2", "typo", ""])
@pytest.mark.parametrize("folder", ["clips", "clip_thumbnails"])
def test_unconfigured_cloud_cannot_publish_an_ephemeral_url(client, monkeypatch, tmp_path, provider, folder):
    monkeypatch.setattr(media, "settings", SimpleNamespace(storage_provider=provider, environment="production"))
    response = client.post("/api/v1/media/upload", data={"folder": folder}, files={"file": ("clip.mp4", b"video", "video/mp4")})
    assert response.status_code == 503
    assert not list(tmp_path.rglob("*.mp4"))


@pytest.mark.parametrize("environment,railway", [("production", False), ("staging", False), ("development", True)])
def test_local_storage_is_rejected_for_deployments(monkeypatch, environment, railway):
    monkeypatch.setattr(media, "settings", SimpleNamespace(storage_provider="local", environment=environment))
    if railway:
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test-environment")
    else:
        monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    with pytest.raises(RuntimeError):
        media._provider()


def test_local_storage_is_an_explicit_development_option(client, monkeypatch, tmp_path):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    monkeypatch.setattr(media, "settings", SimpleNamespace(storage_provider="local", environment="development"))
    response = client.post("/api/v1/media/upload", data={"folder": "clips"}, files={"file": ("clip.mp4", b"video", "video/mp4")})
    assert response.status_code == 200
    assert client.get(response.json()["path"]).content == b"video"
    assert len(list(tmp_path.rglob("*.mp4"))) == 1


class FakeS3:
    payload = b"0123456789"

    def __init__(self, failure=None):
        self.failure = failure
        self.objects = {}
        self.streams = []
        self.ranges = []

    def upload_file(self, path, bucket, key, ExtraArgs):
        if self.failure == "write":
            raise OSError("storage write unavailable")
        from pathlib import Path
        self.objects[key] = Path(path).read_bytes()
        assert ExtraArgs["ContentType"] in {"video/mp4", "image/jpeg"}

    def head_object(self, **kwargs):
        if self.failure == "missing":
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        if self.failure == "head":
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")
        return {"ContentLength": len(self.payload), "ContentType": "video/mp4"}

    def get_object(self, **kwargs):
        self.ranges.append(kwargs["Range"])
        if self.failure == "get":
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
        start, end = map(int, kwargs["Range"].removeprefix("bytes=").split("-"))
        payload = self.payload[start:end + 1]
        if self.failure == "empty":
            payload = b""
        raw = io.BytesIO(payload)
        self.streams.append(raw)
        return {"Body": StreamingBody(raw, len(payload)), "ContentLength": end - start + 1}


def configure_s3(monkeypatch, provider="s3", failure=None):
    fake = FakeS3(failure)
    monkeypatch.setattr(media, "_provider", lambda: (provider, "test-bucket"))
    monkeypatch.setattr(media, "_s3_client", lambda _: fake)
    return fake


@pytest.mark.parametrize("provider", ["s3", "r2"])
@pytest.mark.parametrize("header,status,payload", [(None, 200, b"0123456789"), ("bytes=2-5", 206, b"2345"), ("bytes=-3", 206, b"789"), ("bytes=8-", 206, b"89")])
def test_cloud_responses_contain_exact_bytes_and_close_streams(client, monkeypatch, provider, header, status, payload):
    fake = configure_s3(monkeypatch, provider)
    response = client.get("/api/v1/media/file/clips/clip.mp4", headers={"Range": header} if header else {})
    assert response.status_code == status
    assert response.content == payload
    assert response.headers["content-length"] == str(len(payload))
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert all(raw.closed for raw in fake.streams)


@pytest.mark.parametrize("provider", ["s3", "r2"])
@pytest.mark.parametrize("failure", ["head", "get", "empty"])
def test_first_read_failures_return_503_before_success_headers(client, monkeypatch, provider, failure):
    fake = configure_s3(monkeypatch, provider, failure)
    response = client.get("/api/v1/media/file/clips/clip.mp4", headers={"Range": "bytes=2-5"})
    assert response.status_code == 503
    assert "content-range" not in response.headers
    assert all(raw.closed for raw in fake.streams)


def test_gcs_first_read_failure_is_retryable(client, monkeypatch):
    class Blob:
        size = 10
        content_type = "video/mp4"

        def download_as_bytes(self, **_kwargs):
            raise OSError("storage read unavailable")

    monkeypatch.setattr(media, "_provider", lambda: ("gcs", "test-bucket"))
    monkeypatch.setattr(media, "_gcs_bucket", lambda _: SimpleNamespace(get_blob=lambda _: Blob()))
    assert client.get("/api/v1/media/file/clips/clip.mp4").status_code == 503


@pytest.mark.parametrize("folder,content_type,filename", [("clips", "video/mp4", "clip.mp4"), ("clip_thumbnails", "image/jpeg", "poster.jpg")])
def test_successful_upload_is_durable_and_removes_temporary_file(client, monkeypatch, tmp_path, folder, content_type, filename):
    fake = configure_s3(monkeypatch)
    response = client.post("/api/v1/media/upload", data={"folder": folder}, files={"file": (filename, b"durable", content_type)})
    assert response.status_code == 200
    name = response.json()["path"].split("/")[-1]
    assert fake.objects == {f"media/{folder}/{name}": b"durable"}
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_cloud_write_failure_cleans_up_and_does_not_publish_url(client, monkeypatch, tmp_path):
    configure_s3(monkeypatch, failure="write")
    response = client.post("/api/v1/media/upload", data={"folder": "clips"}, files={"file": ("clip.mp4", b"video", "video/mp4")})
    assert response.status_code == 503
    assert "url" not in response.json()
    assert not list(tmp_path.rglob("*.mp4"))


def test_missing_object_is_404_but_unsatisfiable_range_is_416(client, monkeypatch):
    configure_s3(monkeypatch, failure="missing")
    assert client.get("/api/v1/media/file/clips/clip.mp4").status_code == 404
    fake = configure_s3(monkeypatch)
    response = client.get("/api/v1/media/file/clips/clip.mp4", headers={"Range": "bytes=10-"})
    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"
    assert not fake.streams


def test_s3_endpoint_region_style_and_credentials_are_used(monkeypatch):
    import boto3
    captured = {}
    monkeypatch.setattr(media, "settings", SimpleNamespace(aws_endpoint_url="https://storage.example", aws_region="auto", aws_s3_addressing_style="virtual", aws_access_key_id="test-key", aws_secret_access_key="test-secret"))
    monkeypatch.setattr(boto3, "client", lambda service, **kwargs: captured.update(service=service, **kwargs) or captured)
    media._s3_client.cache_clear()
    try:
        media._s3_client("s3")
        assert captured["service"] == "s3"
        assert captured["endpoint_url"] == "https://storage.example"
        assert captured["region_name"] == "auto"
        assert captured["config"].s3["addressing_style"] == "virtual"
        assert captured["aws_access_key_id"] == "test-key"
        assert captured["aws_secret_access_key"] == "test-secret"
    finally:
        media._s3_client.cache_clear()


def test_disconnect_before_body_is_sent_closes_preopened_stream(monkeypatch):
    fake = configure_s3(monkeypatch)
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "asgi": {"spec_version": "2.4"}}
    response = media.stream_clip_from_cloud("clips", "clip.mp4", Request(scope))

    async def send(_message):
        raise OSError("client disconnected before headers")

    async def receive():
        return {"type": "http.disconnect"}

    with pytest.raises(ClientDisconnect):
        asyncio.run(response(scope, receive, send))
    assert all(raw.closed for raw in fake.streams)


def test_large_video_prefetch_is_bounded_and_remaining_body_is_exact(client, monkeypatch):
    fake = configure_s3(monkeypatch)
    fake.payload = b"abcdef" * (media.CHUNK_SIZE // 6 + 40)
    response = client.get("/api/v1/media/file/clips/clip.mp4")
    assert response.content == fake.payload
    assert all(raw.closed for raw in fake.streams)


def test_other_attachments_keep_existing_storage_contract(client, monkeypatch, tmp_path):
    monkeypatch.setattr(media, "_provider", lambda: (_ for _ in ()).throw(AssertionError("unrelated attachment used Discover storage")))
    response = client.post("/api/v1/media/upload", data={"folder": "chat"}, files={"file": ("note.txt", b"note", "text/plain")})
    assert response.status_code == 200
    assert client.get(response.json()["path"]).content == b"note"


@pytest.mark.parametrize("folder", ["clips", "clip_thumbnails"])
def test_empty_discover_upload_is_rejected_before_cloud_write(client, monkeypatch, tmp_path, folder):
    fake = configure_s3(monkeypatch)
    response = client.post("/api/v1/media/upload", data={"folder": folder}, files={"file": ("clip.mp4", b"", "video/mp4")})
    assert response.status_code == 400
    assert not fake.objects
    assert not list(tmp_path.rglob("*.mp4"))
