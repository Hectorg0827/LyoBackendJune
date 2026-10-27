import io
import logging
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from websockets.sync.client import connect

from lyo_app.core.log_redaction import install_log_redaction, redact_log_text


TEST_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.testSignature"


@pytest.mark.parametrize("query", [
    "token=" + TEST_JWT,
    "to%6ben=" + TEST_JWT,
    "ticket=one-time-test-ticket&device_type=web",
    "api_key=test-guest-key",
])
def test_redacts_entire_query_and_embedded_bearer(query):
    message = f'WebSocket /api/v1/sync/ws?{query} [accepted] Bearer {TEST_JWT}'
    sanitized = redact_log_text(message)
    assert sanitized == 'WebSocket /api/v1/sync/ws?[REDACTED] [accepted] Bearer [REDACTED]'


def test_record_factory_covers_nonpropagating_logger_and_traceback():
    install_log_redaction()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("lyo.test.nonpropagating")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.info("Credential: %(ticket)s", {"ticket": "opaque-test-ticket"})
        try:
            raise ValueError("Authorization: Bearer " + TEST_JWT)
        except ValueError:
            logger.exception("Failed at /ws?token=%s", TEST_JWT)
        assert TEST_JWT not in stream.getvalue()
        assert "opaque-test-ticket" not in stream.getvalue()
        assert "token=" not in stream.getvalue()
        assert "ValueError" in stream.getvalue()
    finally:
        logger.handlers = []
        logger.propagate = True


def test_real_uvicorn_http_and_websocket_logs_never_emit_credentials():
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.websocket("/ws/{outcome}")
    async def websocket_route(ws: WebSocket, outcome: str):
        if outcome == "denied":
            await ws.close(code=1008)
            return
        await ws.accept()
        await ws.close()

    stream = io.StringIO()
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(message)s"},
            "access": {"()": "uvicorn.logging.AccessFormatter", "fmt": '%(request_line)s %(status_code)s'},
        },
        "handlers": {
            "default": {"class": "logging.StreamHandler", "stream": stream, "formatter": "default"},
            "access": {"class": "logging.StreamHandler", "stream": stream, "formatter": "access"},
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }
    install_log_redaction()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_config=log_config, lifespan="off", ws="websockets"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        httpx.get(f"http://127.0.0.1:{port}/health?token={TEST_JWT}", trust_env=False).raise_for_status()
        with connect(f"ws://127.0.0.1:{port}/ws/accepted?token={TEST_JWT}", proxy=None):
            pass
        with pytest.raises(Exception):
            with connect(f"ws://127.0.0.1:{port}/ws/denied?ticket=opaque-test-ticket", proxy=None):
                pass
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
    output = stream.getvalue()
    assert 'WebSocket /ws/accepted?[REDACTED]' in output
    assert 'WebSocket /ws/denied?[REDACTED]' in output
    assert 'GET /health?[REDACTED] HTTP/1.1' in output
    assert TEST_JWT not in output
    assert "opaque-test-ticket" not in output
    assert "token=" not in output
    assert "ticket=" not in output
