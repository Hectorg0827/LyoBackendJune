"""Full classroom HTTP contract through the opt-in FastKokoro adapter.

The upstream here is an intentionally local fake ONNX server.  These tests
exercise the public backend routes and their request mapping without sending
classroom traffic to Railway or enabling the pilot in any environment.
"""

import base64
from unittest.mock import AsyncMock

import httpx
import pytest
from aiohttp import web
from fastapi import FastAPI

from lyo_app.tts import routes
from lyo_app.tts.service import TTSConfig, TTSService


async def _fake_onnx_server(requests_seen):
    async def synthesize(request):
        payload = await request.json()
        requests_seen.append(payload)
        locale = payload.get("lang")
        return web.Response(
            body=b"test-mp3-spanish" if locale == "es-es" else b"test-mp3-english",
            content_type="audio/mpeg",
        )

    app = web.Application()
    app.router.add_post("/v1/audio/speech", synthesize)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


def _classroom_app(monkeypatch, service):
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_current_user_or_guest] = lambda: None
    monkeypatch.setattr(routes, "get_tts_service", AsyncMock(return_value=service))
    return app


@pytest.mark.asyncio
async def test_web_and_android_shared_stream_api_maps_onnx_locale_and_cast(tmp_path, monkeypatch):
    """Both clients call one backend stream route; speech remains self-hosted."""
    requests_seen = []
    runner, upstream = await _fake_onnx_server(requests_seen)
    service = TTSService(TTSConfig(
        provider="kokoro", kokoro_runtime="fastkokoro",
        kokoro_base_url=upstream, cache_dir=str(tmp_path),
        allow_openai_tts=False,
    ))
    app = _classroom_app(monkeypatch, service)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            english = await client.post("/api/v1/tts/synthesize/stream", json={
                "text": "Hello, let us compare two fractions.",
                "language": "en-US", "speaker_id": "lyo",
            })
            spanish = await client.post("/api/v1/tts/synthesize/stream", json={
                "text": "Hola, vamos a comparar dos fracciones.",
                "language": "es-US", "speaker_id": "teacher_3",
            })

        assert english.status_code == spanish.status_code == 200
        assert english.content == b"test-mp3-english"
        assert spanish.content == b"test-mp3-spanish"
        for response in (english, spanish):
            assert response.headers["content-type"].startswith("audio/mpeg")
            assert response.headers["x-accel-buffering"] == "no"
            assert response.headers["cache-control"] == "no-store"
        assert [p["lang"] for p in requests_seen] == ["en-us", "es-es"]
        assert [p["voice"] for p in requests_seen] == ["am_liam", "ef_dora"]
        assert all(p["speed"] == 1.0 and p["stream"] is True for p in requests_seen)
        assert all(p["model"] == "kokoro" for p in requests_seen)
    finally:
        await service.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_buffered_classroom_api_preserves_teacher_identity_and_locale(tmp_path, monkeypatch):
    """Legacy base64 clients resolve a stable teacher voice in either locale."""
    requests_seen = []
    runner, upstream = await _fake_onnx_server(requests_seen)
    service = TTSService(TTSConfig(
        provider="kokoro", kokoro_runtime="fastkokoro",
        kokoro_base_url=upstream, cache_dir=str(tmp_path),
        allow_openai_tts=False,
    ))
    app = _classroom_app(monkeypatch, service)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            english = await client.post("/api/v1/tts/synthesize", json={
                "text": "Today we learn fractions.", "language": "en-US",
                "speaker_id": "teacher_3",
            })
            spanish = await client.post("/api/v1/tts/synthesize", json={
                "text": "Hoy aprendemos las fracciones.", "language": "es-MX",
                "speaker_id": "teacher_3",
            })

        assert english.status_code == spanish.status_code == 200
        english_body, spanish_body = english.json(), spanish.json()
        assert english_body["provider"] == spanish_body["provider"] == "kokoro"
        assert english_body["provider_voice"] == "af_sky"
        assert spanish_body["provider_voice"] == "ef_dora"
        assert english_body["language_code"] == "en-US"
        assert spanish_body["language_code"] == "es-MX"
        assert base64.b64decode(english_body["audio_base64"]) == b"test-mp3-english"
        assert base64.b64decode(spanish_body["audio_base64"]) == b"test-mp3-spanish"
        assert [p["voice"] for p in requests_seen] == ["af_sky", "ef_dora"]
        assert [p["lang"] for p in requests_seen] == ["en-us", "es-es"]
        assert all("stream" not in p for p in requests_seen)
        assert all(p["speed"] == 1.0 for p in requests_seen)
    finally:
        await service.close()
        await runner.cleanup()
