from unittest.mock import AsyncMock
import asyncio
import logging
import pytest
from fastapi import HTTPException
from lyo_app.tts import routes
from lyo_app.tts.service import TTSUnavailableError

@pytest.mark.asyncio
async def test_route_primes_only_first_chunk_and_preserves_locale(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger='lyo_app.tts.routes')
    events = []
    class Service:
        async def synthesize_streaming(self, **kwargs):
            assert kwargs['language'] == 'es-US'
            try:
                events.append('first')
                yield b'first'
                events.append('last')
                yield b'last'
            finally:
                events.append('closed')
    monkeypatch.setattr(routes, 'get_tts_service', AsyncMock(return_value=Service()))
    response = await routes.synthesize_stream(routes.SynthesizeRequest(text='Una respuesta concreta.', language='es-US'), None)
    assert events == ['first']
    assert response.headers['x-accel-buffering'] == 'no'
    assert b''.join([part async for part in response.body_iterator]) == b'firstlast'
    assert events == ['first', 'last', 'closed']
    assert 'Classroom TTS first audio bytes' in caplog.text
    assert 'Classroom TTS stream completed' in caplog.text

@pytest.mark.asyncio
async def test_provider_error_before_first_byte_keeps_http_error_status(monkeypatch):
    class Service:
        async def synthesize_streaming(self, **kwargs):
            raise TTSUnavailableError('Provider unavailable')
            yield b''
    monkeypatch.setattr(routes, 'get_tts_service', AsyncMock(return_value=Service()))
    with pytest.raises(HTTPException) as error:
        await routes.synthesize_stream(routes.SynthesizeRequest(text='A useful answer.'), None)
    assert error.value.status_code == 503

@pytest.mark.asyncio
async def test_closed_response_releases_provider_stream(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger='lyo_app.tts.routes')
    closed = []
    class Service:
        async def synthesize_streaming(self, **kwargs):
            try:
                yield b'first'
                yield b'last'
            finally:
                closed.append(True)
    monkeypatch.setattr(routes, 'get_tts_service', AsyncMock(return_value=Service()))
    response = await routes.synthesize_stream(routes.SynthesizeRequest(text='A useful answer.'), None)
    assert await anext(response.body_iterator) == b'first'
    await response.body_iterator.aclose()
    assert closed == [True]
    assert 'Classroom TTS stream interrupted' in caplog.text


@pytest.mark.asyncio
async def test_first_audio_deadline_releases_provider_and_returns_recoverable_504(monkeypatch, caplog):
    """An unhealthy provider cannot hold the teacher silent for 90 seconds."""
    caplog.set_level(logging.WARNING, logger='lyo_app.tts.routes')
    closed = asyncio.Event()

    class SlowService:
        async def synthesize_streaming(self, **kwargs):
            try:
                await asyncio.sleep(60)
                yield b'unreachable'
            finally:
                closed.set()

    monkeypatch.setattr(routes, 'get_tts_service', AsyncMock(return_value=SlowService()))
    monkeypatch.setattr(routes, '_first_audio_budget_seconds', lambda: 0.01)

    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(
            routes.synthesize_stream(routes.SynthesizeRequest(text='Please explain this.'), None),
            timeout=0.25,
        )

    assert error.value.status_code == 504
    assert error.value.detail == 'Speech provider timed out'
    assert closed.is_set(), 'Canceled upstream generator must release its connection'
    assert 'Classroom TTS exceeded first-audio deadline' in caplog.text


@pytest.mark.asyncio
async def test_client_cancel_before_first_audio_releases_provider(monkeypatch):
    """A closed browser must not leave a provider request or cache lock alive."""
    entered = asyncio.Event()
    closed = asyncio.Event()

    class HangingService:
        async def synthesize_streaming(self, **kwargs):
            try:
                entered.set()
                await asyncio.Event().wait()
                yield b'unreachable'
            finally:
                closed.set()

    monkeypatch.setattr(routes, 'get_tts_service', AsyncMock(return_value=HangingService()))
    monkeypatch.delenv('TTS_STREAM_FIRST_BYTE_TIMEOUT_SECONDS', raising=False)
    request_task = asyncio.create_task(
        routes.synthesize_stream(routes.SynthesizeRequest(text='One sentence.'), None)
    )
    await asyncio.wait_for(entered.wait(), timeout=0.25)
    request_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request_task
    assert closed.is_set()


def test_first_audio_deadline_rejects_invalid_configuration(monkeypatch):
    for raw in ('invalid', 'nan', 'inf', '0', '-5', '999'):
        monkeypatch.setenv('TTS_STREAM_FIRST_BYTE_TIMEOUT_SECONDS', raw)
        assert routes._first_audio_budget_seconds() is None

    monkeypatch.setenv('TTS_STREAM_FIRST_BYTE_TIMEOUT_SECONDS', '23.5')
    assert routes._first_audio_budget_seconds() == 23.5


def test_first_audio_deadline_is_opt_in_and_preserves_existing_production_timeout(monkeypatch):
    monkeypatch.delenv('TTS_STREAM_FIRST_BYTE_TIMEOUT_SECONDS', raising=False)
    assert routes._first_audio_budget_seconds() is None

    monkeypatch.setenv('TTS_STREAM_FIRST_BYTE_TIMEOUT_SECONDS', '15')
    assert routes._first_audio_budget_seconds() == 15.0


@pytest.mark.asyncio
async def test_unconfigured_provider_timeout_keeps_existing_502_contract(monkeypatch):
    class TimedOutService:
        async def synthesize_streaming(self, **kwargs):
            raise TimeoutError('upstream 90-second timeout')
            yield b'unreachable'

    monkeypatch.setattr(routes, 'get_tts_service', AsyncMock(return_value=TimedOutService()))
    monkeypatch.delenv('TTS_STREAM_FIRST_BYTE_TIMEOUT_SECONDS', raising=False)

    with pytest.raises(HTTPException) as error:
        await routes.synthesize_stream(routes.SynthesizeRequest(text='One idea.'), None)
    assert error.value.status_code == 502
    assert error.value.detail == 'Speech provider failed'


@pytest.mark.asyncio
async def test_successful_speech_within_deadline_does_not_change_response(monkeypatch):
    class FastService:
        async def synthesize_streaming(self, **kwargs):
            await asyncio.sleep(0)
            yield b'audio-1'
            yield b'audio-2'

    monkeypatch.setattr(routes, 'get_tts_service', AsyncMock(return_value=FastService()))
    monkeypatch.setattr(routes, '_first_audio_budget_seconds', lambda: 0.05)
    response = await routes.synthesize_stream(
        routes.SynthesizeRequest(text='One sentence.', format='mp3'), None
    )
    assert response.media_type == 'audio/mpeg'
    assert b''.join([part async for part in response.body_iterator]) == b'audio-1audio-2'


@pytest.mark.asyncio
async def test_provider_disconnect_after_first_byte_is_not_hidden(monkeypatch, caplog):
    """A truncated recording must never masquerade as a completed stream."""
    caplog.set_level(logging.INFO, logger='lyo_app.tts.routes')
    closed = asyncio.Event()

    class DisconnectedService:
        async def synthesize_streaming(self, **kwargs):
            try:
                yield b'partial-audio'
                raise RuntimeError('upstream disconnected')
            finally:
                closed.set()

    monkeypatch.setattr(routes, 'get_tts_service', AsyncMock(return_value=DisconnectedService()))
    response = await routes.synthesize_stream(
        routes.SynthesizeRequest(text='A teaching explanation.'), None
    )

    assert await anext(response.body_iterator) == b'partial-audio'
    with pytest.raises(RuntimeError, match='upstream disconnected'):
        await anext(response.body_iterator)
    assert closed.is_set()
    assert 'Classroom TTS stream interrupted' in caplog.text
    assert 'Classroom TTS stream completed' not in caplog.text
