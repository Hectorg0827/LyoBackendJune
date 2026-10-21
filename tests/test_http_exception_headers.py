"""Error envelopes retain protocol headers required by clients."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from lyo_app.core.exceptions import setup_error_handlers
from lyo_app.routers.clip_media_storage import parse_byte_range


def test_unsatisfiable_media_range_retains_size_in_real_error_handler():
    app = FastAPI()
    setup_error_handlers(app)

    @app.get("/range")
    def invalid_range():
        parse_byte_range("bytes=9999999-", 663882)

    response = TestClient(app).get("/range")
    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */663882"
    assert response.json()["error"]["code"] == "HTTP_ERROR"


@pytest.mark.parametrize("status,headers", [
    (401, {"WWW-Authenticate": "Bearer"}),
    (429, {"Retry-After": "30"}),
])
def test_auth_and_retry_headers_survive_error_envelope(status, headers):
    app = FastAPI()
    setup_error_handlers(app)

    @app.get("/error")
    def error():
        raise HTTPException(status_code=status, detail="Test error", headers=headers)

    response = TestClient(app).get("/error")
    assert response.status_code == status
    for name, value in headers.items():
        assert response.headers[name] == value
