from unittest.mock import AsyncMock

import pytest

from lyo_app.tts.service import (
    TTSConfig,
    TTSService,
    TTSUnavailableError,
)


def _config(tmp_path, **overrides):
    values = {
        "provider": "kokoro",
        "kokoro_base_url": "http://kokoro.test:8880",
        "cache_dir": str(tmp_path),
    }
    values.update(overrides)
    return TTSConfig(**values)


def test_spanish_resolves_to_a_spanish_teacher_voice(tmp_path):
    service = TTSService(_config(tmp_path))

    explicit = service.resolve_voice(
        "Vamos a comparar estas dos ideas.",
        language="es-MX",
    )
    detected = service.resolve_voice(
        "¿Por qué la respuesta es diferente para cada ejemplo?",
        language="auto",
    )

    assert explicit.language_code == "es-MX"
    assert explicit.provider_voice == "ef_dora"
    assert detected.language_code == "es-US"
    assert detected.provider_voice == "ef_dora"


def test_language_names_from_course_metadata_are_normalized(tmp_path):
    service = TTSService(_config(tmp_path))

    spanish = service.resolve_voice("Una idea concreta.", language="Spanish")

    assert spanish.language_code == "es-US"
    assert spanish.provider_voice == "ef_dora"


@pytest.mark.asyncio
async def test_identical_turns_are_rendered_only_once(tmp_path):
    service = TTSService(_config(tmp_path))
    render = AsyncMock(return_value=b"same-neural-audio")
    service._synthesize_uncached = render

    try:
        first = await service.synthesize(
            "One idea, then the learner gets a turn.",
            language="en-US",
        )
        second = await service.synthesize(
            "One idea, then the learner gets a turn.",
            language="en-US",
        )
    finally:
        await service.close()

    assert first == second == b"same-neural-audio"
    render.assert_awaited_once()


def test_openai_tts_requires_explicit_cost_opt_in(tmp_path):
    service = TTSService(
        _config(
            tmp_path,
            provider="openai",
            openai_api_key="present-but-not-authorized-for-tts",
            allow_openai_tts=False,
        )
    )

    assert service.provider_available is False
    with pytest.raises(TTSUnavailableError, match="disabled"):
        service.resolve_voice("This should never incur a charge.")


@pytest.mark.asyncio
async def test_cache_separates_languages(tmp_path):
    service = TTSService(_config(tmp_path))
    render = AsyncMock(side_effect=[b"english", b"spanish"])
    service._synthesize_uncached = render

    try:
        english = await service.synthesize("A short example.", language="en-US")
        spanish = await service.synthesize("A short example.", language="es-US")
    finally:
        await service.close()

    assert english == b"english"
    assert spanish == b"spanish"
    assert render.await_count == 2


@pytest.mark.asyncio
async def test_first_audio_precedes_provider_completion_and_native_reuses_cache(tmp_path):
    import asyncio
    from aiohttp import web
    finish = asyncio.Event()
    calls = []
    async def provider(request):
        calls.append(await request.json())
        response = web.StreamResponse(headers={"Content-Type": "audio/mpeg"})
        await response.prepare(request)
        await response.write(b'first')
        await finish.wait()
        await response.write(b'last')
        await response.write_eof()
        return response
    app = web.Application()
    app.router.add_post('/v1/audio/speech', provider)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    service = TTSService(_config(tmp_path, kokoro_base_url=f'http://127.0.0.1:{port}'))
    stream = service.synthesize_streaming('A useful answer.', language='es-US')
    try:
        assert await asyncio.wait_for(anext(stream), 1) == b'first'
        assert not finish.is_set()
        native = asyncio.create_task(service.synthesize('A useful answer.', language='es-US'))
        await asyncio.sleep(0)
        assert not native.done()
        finish.set()
        assert b''.join([chunk async for chunk in stream]) == b'last'
        assert await native == b'firstlast'
        assert len(calls) == 1
        assert calls[0]['voice'] == 'ef_dora'
        assert not service._key_locks
    finally:
        finish.set()
        await stream.aclose()
        await service.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_canceled_stream_does_not_cache_partial_audio_or_leak_lock(tmp_path):
    from unittest.mock import MagicMock
    service = TTSService(_config(tmp_path))
    await service.initialize()
    real_session = service._session
    async def chunks(_size):
        yield b'partial'
        raise AssertionError('Canceled stream must not request the rest')
    response = MagicMock(status=200)
    response.content.iter_chunked = chunks
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=None)
    service._session = MagicMock()
    service._session.post.return_value = context
    stream = service.synthesize_streaming('Interrupted answer.')
    try:
        assert await anext(stream) == b'partial'
        await stream.aclose()
        assert list(tmp_path.iterdir()) == []
        assert not service._key_locks
        assert not service._key_users
        context.__aexit__.assert_awaited_once()
    finally:
        await real_session.close()


@pytest.mark.asyncio
async def test_streaming_preserves_paid_provider_opt_in(tmp_path):
    service = TTSService(_config(tmp_path, provider='openai', openai_api_key='unauthorized'))
    try:
        with pytest.raises(TTSUnavailableError):
            await anext(service.synthesize_streaming('Do not charge.'))
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_stalled_cached_stream_does_not_block_another_cached_client(tmp_path):
    import asyncio
    service = TTSService(_config(tmp_path))
    service._synthesize_uncached = AsyncMock(return_value=b"firstlast")
    try:
        await service.synthesize("Same cached teacher turn.")
        stalled = service.synthesize_streaming("Same cached teacher turn.", chunk_size=5)
        assert await anext(stalled) == b"first"
        # Leave that client suspended at yield while a second consumes audio.
        assert not service._key_locks
        async def download():
            return b"".join([chunk async for chunk in service.synthesize_streaming(
                "Same cached teacher turn.", chunk_size=5)])
        assert await asyncio.wait_for(download(), 1) == b"firstlast"
        service._synthesize_uncached.assert_awaited_once()
        await stalled.aclose()
    finally:
        await service.close()
