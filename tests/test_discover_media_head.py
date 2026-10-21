"""HEAD probes, durable-media checks and cache headers for Discover video URLs.

Players and CDNs ask for a video's length and range support with HEAD before
they play it. FastAPI does not answer HEAD for a GET route, so those probes
got 405. HEAD must answer from storage metadata alone: reading the video to
answer a HEAD would download it once per probe.
"""
import io

import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lyo_app.core.exceptions import setup_error_handlers
from lyo_app.routers import clip_media_storage as media
from lyo_app.routers import user_media

PAYLOAD = b"0123456789"


class MetadataOnlyS3:
    """Answers head_object; fails the test if anything reads the body."""

    def __init__(self, missing=False, denied=False):
        self.missing = missing
        self.denied = denied
        self.reads = 0

    def head_object(self, **_kwargs):
        if self.missing:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        if self.denied:
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")
        return {"ContentLength": len(PAYLOAD), "ContentType": "video/mp4"}

    def get_object(self, **kwargs):
        self.reads += 1
        start, end = map(int, kwargs["Range"].removeprefix("bytes=").split("-"))
        body = PAYLOAD[start:end + 1]
        return {"Body": StreamingBody(io.BytesIO(body), len(body)), "ContentLength": len(body)}


@pytest.fixture
def client(monkeypatch, tmp_path):
    app = FastAPI()
    setup_error_handlers(app)
    app.include_router(user_media.router)
    monkeypatch.setattr(user_media, "_media_root", lambda: tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def use_s3(monkeypatch, fake):
    monkeypatch.setattr(media, "_provider", lambda: ("r2", "test-bucket"))
    monkeypatch.setattr(media, "_s3_client", lambda _: fake)
    return fake


@pytest.mark.parametrize("header,status,length,content_range", [
    (None, 200, "10", None),
    ("bytes=2-5", 206, "4", "bytes 2-5/10"),
    ("bytes=-3", 206, "3", "bytes 7-9/10"),
])
def test_cloud_head_reports_length_and_ranges_without_reading_the_video(client, monkeypatch, header, status, length, content_range):
    fake = use_s3(monkeypatch, MetadataOnlyS3())
    response = client.head("/api/v1/media/file/clips/clip.mp4", headers={"Range": header} if header else {})
    assert response.status_code == status
    assert response.content == b""
    assert response.headers["content-length"] == length
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers.get("content-range") == content_range
    assert fake.reads == 0


def test_cloud_head_beyond_the_end_is_416_with_the_size(client, monkeypatch):
    use_s3(monkeypatch, MetadataOnlyS3())
    response = client.head("/api/v1/media/file/clips/clip.mp4", headers={"Range": "bytes=10-"})
    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"


def test_cloud_head_for_a_missing_video_is_404(client, monkeypatch):
    use_s3(monkeypatch, MetadataOnlyS3(missing=True))
    assert client.head("/api/v1/media/file/clips/clip.mp4").status_code == 404


def test_local_head_answers_like_get(client, tmp_path):
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "clip.mp4").write_bytes(PAYLOAD)
    head = client.head("/api/v1/media/file/clips/clip.mp4")
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == "10"
    ranged = client.get("/api/v1/media/file/clips/clip.mp4", headers={"Range": "bytes=2-5"})
    assert ranged.status_code == 206
    assert ranged.content == b"2345"


def test_video_responses_name_their_process_and_are_cacheable_forever(client, monkeypatch):
    use_s3(monkeypatch, MetadataOnlyS3())
    response = client.get("/api/v1/media/file/clips/clip.mp4", headers={"Range": "bytes=0-1"})
    assert response.status_code == 206
    assert response.content == b"01"
    assert response.headers["x-media-instance"] == media.INSTANCE_ID
    assert "immutable" in response.headers["cache-control"]


@pytest.mark.parametrize("url,expected", [
    ("https://api.lyoai.app/api/v1/media/file/clips/" + "a" * 32 + ".mp4", ("clips", "a" * 32 + ".mp4")),
    ("/api/v1/media/file/clip_thumbnails/" + "b" * 32 + ".jpg", ("clip_thumbnails", "b" * 32 + ".jpg")),
    ("https://cdn.example.com/video.mp4", None),
    ("/api/v1/media/file/content/" + "a" * 32 + ".mp4", None),
    ("/api/v1/media/file/clips/../secret.mp4", None),
    ("/api/v1/media/file/clips/" + "a" * 32 + ".exe", None),
    # The upload endpoint stores any allowed type in any folder: an image in
    # "clips" is not a video, and a video is not a poster.
    ("/api/v1/media/file/clips/" + "a" * 32 + ".jpg", None),
    ("/api/v1/media/file/clip_thumbnails/" + "a" * 32 + ".mp4", None),
    (None, None),
])
def test_media_path_parts_only_recognises_upload_paths(url, expected):
    assert media.media_path_parts(url) == expected


def test_stat_reports_size_absence_and_refuses_to_guess_on_errors(monkeypatch, tmp_path):
    use_s3(monkeypatch, MetadataOnlyS3())
    assert media.stat_durable_media("clips", "a.mp4", tmp_path) == 10
    use_s3(monkeypatch, MetadataOnlyS3(missing=True))
    assert media.stat_durable_media("clips", "a.mp4", tmp_path) is None
    use_s3(monkeypatch, MetadataOnlyS3(denied=True))
    with pytest.raises(ClientError):
        media.stat_durable_media("clips", "a.mp4", tmp_path)


def test_stat_counts_a_development_file_on_local_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "_provider", lambda: None)
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "a.mp4").write_bytes(PAYLOAD)
    assert media.stat_durable_media("clips", "a.mp4", tmp_path) == 10
    assert media.stat_durable_media("clips", "b.mp4", tmp_path) is None


def test_with_cloud_storage_a_local_copy_is_not_proof(monkeypatch, tmp_path):
    # A file on this container's disk is what a redeploy or another replica
    # lacks; with a bucket configured, only the bucket counts.
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "a.mp4").write_bytes(PAYLOAD)
    use_s3(monkeypatch, MetadataOnlyS3(missing=True))
    assert media.stat_durable_media("clips", "a.mp4", tmp_path) is None
