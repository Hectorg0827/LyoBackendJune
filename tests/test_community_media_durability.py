"""Community post photos must survive restarts and replica changes.

The upload and public GET endpoints are the same routes used by Create Studio
on web, iOS and Android. Never acknowledge an image upload in production when
its durable write fails: the resulting post would contain a broken URL.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient

from lyo_app.routers import clip_media_storage, user_media


@pytest.fixture
def client(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(user_media.router)
    app.dependency_overrides[user_media.get_current_user] = lambda: SimpleNamespace(id=17)
    monkeypatch.setattr(user_media, "_media_root", lambda: tmp_path)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    ("mime_type", "filename", "extension"),
    [
        ("image/png", "study-note.png", ".png"),
        ("image/jpeg", "whiteboard.jpg", ".jpg"),
        ("image/heif", "camera.heif", ".heic"),
    ],
)
def test_community_photo_uploaded_to_cloud_and_served_without_local_copy(
    client, monkeypatch, tmp_path, mime_type, filename, extension
):
    assert "community" in clip_media_storage.DURABLE_MEDIA_FOLDERS

    payload = b"photo-from-device"
    uploaded = []

    def durable_save(path, folder, name, content_type):
        assert path.is_file()
        uploaded.append((folder, name, content_type, path.read_bytes()))
        return True

    def cloud_read(folder, name, request):
        assert folder == "community"
        assert name == uploaded[0][1]
        return Response(payload, media_type=mime_type)

    monkeypatch.setattr(user_media, "save_clip_to_cloud", durable_save)
    monkeypatch.setattr(user_media, "stream_clip_from_cloud", cloud_read)

    result = client.post(
        "/api/v1/media/upload",
        data={"folder": "community"},
        files={"file": (filename, payload, mime_type)},
    )
    assert result.status_code == 200, result.text
    media = result.json()
    assert media["success"] is True
    assert media["path"].startswith("/api/v1/media/file/community/")
    assert media["path"].endswith(extension)
    assert uploaded[0][0] == "community"
    assert uploaded[0][2] == mime_type
    assert uploaded[0][3] == payload

    # Durable uploads delete the temporary container copy immediately.
    assert not list(tmp_path.rglob(f"*{extension}"))
    fetched = client.get(media["path"])
    assert fetched.status_code == 200
    assert fetched.content == payload


def test_community_photo_write_failure_returns_503_and_leaves_no_orphan(
    client, monkeypatch, tmp_path
):
    def fail_to_store(*_args):
        raise RuntimeError("object store unavailable")

    monkeypatch.setattr(user_media, "save_clip_to_cloud", fail_to_store)
    response = client.post(
        "/api/v1/media/upload",
        data={"folder": "community"},
        files={"file": ("notes.png", b"photo", "image/png")},
    )
    assert response.status_code == 503
    assert not list(tmp_path.rglob("*.png"))


def test_discover_url_classifier_remains_clip_only():
    # Extending durable storage must not make Community images publishable as
    # Discover video or thumbnail assets.
    community = "/api/v1/media/file/community/" + "a" * 32 + ".jpg"
    assert clip_media_storage.media_path_parts(community) is None
