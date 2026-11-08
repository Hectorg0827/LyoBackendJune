"""Opt-in FastKokoro compatibility, with the original API as the default."""

import asyncio
import hashlib
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from lyo_app.tts.service import TTSConfig, TTSService


def _config(tmp_path, **kwargs):
    values = {
        "provider": "kokoro",
        "kokoro_base_url": "http://kokoro.test:8880",
        "cache_dir": str(tmp_path),
    }
    values.update(kwargs)
    return TTSConfig(**values)


def test_runtime_is_opt_in_and_invalid_environment_values_are_safe(monkeypatch):
    monkeypatch.delenv("KOKORO_TTS_RUNTIME", raising=False)
    assert TTSConfig.from_environment().kokoro_runtime == "fastapi"
    monkeypatch.setenv("KOKORO_TTS_RUNTIME", "FASTKOKORO")
    assert TTSConfig.from_environment().kokoro_runtime == "fastkokoro"
    monkeypatch.setenv("KOKORO_TTS_RUNTIME", "unknown")
    assert TTSConfig.from_environment().kokoro_runtime == "fastapi"


def test_original_kokoro_payload_stays_unchanged(tmp_path):
    service = TTSService(_config(tmp_path))
    resolved = service.resolve_voice("Hola, clase.", language="es-US")

    assert service._kokoro_request_payload(
        "Hola, clase.", resolved, "mp3", 0.98, stream=False
    ) == {
        "model": "kokoro",
        "input": "Hola, clase.",
        "voice": "ef_dora",
        "response_format": "mp3",
        "speed": 0.98,
    }


@pytest.mark.parametrize(
    ("text", "language", "voice", "upstream_lang"),
    [
        ("Welcome to class.", "en-US", "af_heart", "en-us"),
        ("Hola, clase.", "es-MX", "ef_dora", "es-es"),
        ("Bonjour, classe.", "fr-FR", "ff_siwis", "fr-fr"),
    ],
)
def test_fastkokoro_payload_normalizes_locale_and_speed(
    tmp_path, text, language, voice, upstream_lang
):
    service = TTSService(_config(tmp_path, kokoro_runtime="fastkokoro"))
    resolved = service.resolve_voice(text, language=language)

    payload = service._kokoro_request_payload(
        text, resolved, "mp3", 0.98, stream=True
    )
    assert payload == {
        "model": "kokoro",
        "input": text,
        "voice": voice,
        "response_format": "mp3",
        "speed": 1.0,
        "lang": upstream_lang,
        "stream": True,
    }
    assert service._kokoro_request_payload(
        text, resolved, "wav", 1.15, stream=False
    )["speed"] == 1.15


def test_cache_key_separates_fastkokoro_and_original_runtime(tmp_path):
    original = TTSService(_config(tmp_path))
    onnx = TTSService(_config(tmp_path, kokoro_runtime="fastkokoro"))
    original_voice = original.resolve_voice("Hello classroom.", language="en-US")
    onnx_voice = onnx.resolve_voice("Hello classroom.", language="en-US")

    assert original._get_cache_key("Hello classroom.", original_voice, "mp3", 0.98) != (
        onnx._get_cache_key("Hello classroom.", onnx_voice, "mp3", 0.98)
    )
    legacy_parts = [
        "kokoro", "kokoro", "af_heart", "en-US", "mp3", "0.98", "Hello classroom."
    ]
    assert original._get_cache_key("Hello classroom.", original_voice, "mp3", 0.98) == (
        hashlib.sha256("|".join(legacy_parts).encode("utf-8")).hexdigest()
    )


@pytest.mark.asyncio
async def test_buffered_fastkokoro_uses_compatible_upstream_request(tmp_path):
    service = TTSService(_config(tmp_path, kokoro_runtime="fastkokoro"))
    service._post_binary = AsyncMock(return_value=b"non-empty-mp3")
    try:
        assert await service.synthesize(
            "Una explicación para la clase.", language="es-US", speed=0.98
        ) == b"non-empty-mp3"
        _, kwargs = service._post_binary.await_args
        assert kwargs == {}
        url, payload = service._post_binary.await_args.args
        assert url == "http://kokoro.test:8880/v1/audio/speech"
        assert payload["lang"] == "es-es"
        assert payload["speed"] == 1.0
        assert payload["response_format"] == "mp3"
        assert "stream" not in payload
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_streaming_fastkokoro_uses_compatible_upstream_request(tmp_path):
    received = []

    async def provider(request):
        received.append(await request.json())
        return web.Response(body=b"streamed-mp3", content_type="audio/mpeg")

    app = web.Application()
    app.router.add_post("/v1/audio/speech", provider)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    service = TTSService(
        _config(
            tmp_path,
            kokoro_runtime="fastkokoro",
            kokoro_base_url=f"http://127.0.0.1:{port}",
        )
    )
    try:
        audio = await asyncio.wait_for(
            _read_stream(service.synthesize_streaming(
                "Welcome to your lesson.", language="en-US", speed=0.98
            )),
            timeout=2,
        )
        assert audio == b"streamed-mp3"
        assert received == [{
            "model": "kokoro", "input": "Welcome to your lesson.",
            "voice": "af_heart", "response_format": "mp3", "speed": 1.0,
            "lang": "en-us", "stream": True,
        }]
    finally:
        await service.close()
        await runner.cleanup()


async def _read_stream(stream):
    return b"".join([chunk async for chunk in stream])
