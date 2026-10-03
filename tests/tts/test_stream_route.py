from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from lyo_app.tts import routes
from lyo_app.tts.service import TTSUnavailableError

@pytest.mark.asyncio
async def test_route_primes_only_first_chunk_and_preserves_locale(monkeypatch):
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
async def test_closed_response_releases_provider_stream(monkeypatch):
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
