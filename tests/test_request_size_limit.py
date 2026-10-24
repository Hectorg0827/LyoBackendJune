"""The blanket request cap must not undercut the media upload's own limits."""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lyo_app.auth.security_middleware import SecurityConfig, request_size_middleware

ELEVEN_MB = b"x" * (11 * 1024 * 1024)


@pytest.fixture
def client():
    app = FastAPI()
    app.middleware("http")(request_size_middleware)

    @app.post("/api/v1/media/upload")
    async def upload(request: Request):
        return {"received": len(await request.body())}

    @app.post("/api/v1/clips")
    async def clips(request: Request):
        return {"received": len(await request.body())}

    return TestClient(app)


def test_a_video_over_ten_megabytes_reaches_the_upload_route(client):
    response = client.post("/api/v1/media/upload", content=ELEVEN_MB)
    assert response.status_code == 200
    assert response.json() == {"received": len(ELEVEN_MB)}


def test_other_routes_keep_the_ten_megabyte_cap(client):
    assert client.post("/api/v1/clips", content=ELEVEN_MB).status_code == 413


def test_the_upload_cap_still_stops_requests_over_the_largest_video(client):
    oversize = str(SecurityConfig.MAX_MEDIA_UPLOAD_REQUEST_SIZE + 1)
    response = client.post("/api/v1/media/upload", content=b"x", headers={"Content-Length": oversize})
    assert response.status_code == 413
