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
