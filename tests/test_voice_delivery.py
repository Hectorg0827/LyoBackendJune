import pytest

from lyo_app.core.ai_resilience import (
    AIModelConfig,
    AIResilienceManager,
    CircuitBreaker,
    CircuitBreakerConfig,
    StreamingIncompleteError,
)
from lyo_app.teaching_runtime.voice_delivery import VoiceSegmenter, prepare_spoken_text


def test_spoken_text_removes_visual_markup_but_preserves_meaning():
    canonical = (
        "## Result\n"
        "**Rent** is $2,100 【lease.pdf p. 1】. "
        "See [payment schedule](https://example.com/schedule)."
    )

    assert prepare_spoken_text(canonical) == (
        "Result Rent is 2,100. See payment schedule."
    )


def test_spoken_text_drops_raw_urls_images_and_code_fences():
    canonical = (
        "Look here: https://example.com/raw\n"
        "![chart](https://example.com/chart.png)\n"
        "```python\nprint('do not read this')\n```\n"
        "The conclusion is stable."
    )

    assert prepare_spoken_text(canonical) == "Look here: The conclusion is stable."


def test_voice_segmenter_emits_complete_sentence_before_full_answer():
    segmenter = VoiceSegmenter()

    assert segmenter.feed("Photosynthesis converts light into ") == []
    assert segmenter.feed("chemical energy. Plants then use ") == [
        "Photosynthesis converts light into chemical energy."
    ]
    assert segmenter.flush() == ["Plants then use"]


def test_voice_segmenter_splits_long_unpunctuated_turns():
    segmenter = VoiceSegmenter(soft_target_chars=60, hard_max_chars=90)

    segments = segmenter.feed(
        "This is a fairly long spoken clause, with enough material to begin "
        "speaking before the entire model answer has finished generating"
    )

    assert segments
    assert segments[0].endswith(",")
    assert all(len(segment) <= 90 for segment in segments)


def test_voice_segmenter_preserves_order_across_model_deltas():
    segmenter = VoiceSegmenter()
    spoken = []
    for delta in ["First idea", " is here. Sec", "ond idea is here!", " Last bit"]:
        spoken.extend(segmenter.feed(delta))
    spoken.extend(segmenter.flush())

    assert spoken == [
        "First idea is here.",
        "Second idea is here!",
        "Last bit",
    ]


class _Delta:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.delta = _Delta(content)


class _Chunk:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _FailingStream:
    def __init__(self, parts):
        self.parts = list(parts)

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index < len(self.parts):
            value = self.parts[self._index]
            self._index += 1
            return _Chunk(value)
        raise RuntimeError("provider disconnected after partial output")


class _SuccessfulStream:
    def __init__(self, parts):
        self.parts = list(parts)

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self.parts):
            raise StopAsyncIteration
        value = self.parts[self._index]
        self._index += 1
        return _Chunk(value)


class _Completions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs["model"])
        if kwargs["model"] == "first":
            return _FailingStream(["Partial answer."])
        return _SuccessfulStream(["This must not restart the answer."])


class _Chat:
    def __init__(self, completions):
        self.completions = completions


class _OpenAI:
    def __init__(self, completions):
        self.chat = _Chat(completions)


@pytest.mark.asyncio
async def test_streaming_provider_does_not_restart_after_partial_output():
    manager = AIResilienceManager()
    manager._initialized = True
    manager.models = {
        "first": AIModelConfig(
            name="first",
            endpoint="openai",
            api_key="configured-key",
        ),
        "second": AIModelConfig(
            name="second",
            endpoint="openai",
            api_key="configured-key",
        ),
    }
    manager.circuit_breakers = {
        name: CircuitBreaker(CircuitBreakerConfig())
        for name in manager.models
    }
    completions = _Completions()
    manager.openai_client = _OpenAI(completions)

    output = []
    with pytest.raises(StreamingIncompleteError) as incomplete:
        async for delta in manager.stream_chat_completion(
            [{"role": "user", "content": "Explain gravity"}],
            provider_order=["first", "second"],
        ):
            output.append(delta)
    assert incomplete.value.partial_text == "Partial answer."

    assert output == ["Partial answer."]
    assert completions.calls == ["first"]



@pytest.mark.asyncio
async def test_gemini_stream_failure_before_output_falls_through_to_openai(monkeypatch):
    manager = AIResilienceManager()
    manager._initialized = True
    manager.models = {
        "gemini-first": AIModelConfig(
            name="Gemini first",
            endpoint="https://example.invalid/model:generateContent",
            api_key="configured-key",
        ),
        "openai-second": AIModelConfig(
            name="OpenAI second",
            endpoint="openai",
            api_key="configured-key",
        ),
    }
    manager.circuit_breakers = {
        name: CircuitBreaker(CircuitBreakerConfig())
        for name in manager.models
    }

    async def failing_gemini(*args, **kwargs):
        if False:
            yield ""
        raise RuntimeError("gemini unavailable")

    monkeypatch.setattr(manager, "_stream_gemini", failing_gemini)
    completions = _Completions()
    async def openai_create(**kwargs):
        completions.calls.append(kwargs["model"])
        return _SuccessfulStream(["Healthy fallback."])
    completions.create = openai_create
    manager.openai_client = _OpenAI(completions)

    output = []
    async for delta in manager.stream_chat_completion(
        [{"role": "user", "content": "Explain gravity"}],
        provider_order=["gemini-first", "openai-second"],
    ):
        output.append(delta)

    assert output == ["Healthy fallback."]
    assert completions.calls == ["openai-second"]


def test_segmenter_preserves_titles_and_initials_across_deltas():
    segmenter = VoiceSegmenter()
    segments = []
    for part in ['This result came from Dr.', ' Smith in the U.', 'S. laboratory. Next ', 'sentence continues.']:
        segments.extend(segmenter.feed(part))
    segments.extend(segmenter.flush())
    assert segments == ['This result came from Dr. Smith in the U.S. laboratory.', 'Next sentence continues.']
