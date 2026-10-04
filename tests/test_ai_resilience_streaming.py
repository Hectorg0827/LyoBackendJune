import json

import pytest

from lyo_app.core.ai_resilience import AIModelConfig, AIResilienceManager


class _FakeContent:
    def __init__(self, lines):
        self._lines = list(lines)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        value = self._lines[self._index]
        self._index += 1
        return value


class _FakeResponse:
    status = 200

    def __init__(self, lines):
        self.content = _FakeContent(lines)

    async def text(self):
        return ""


class _FakePostContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, lines):
        self.lines = lines
        self.last_endpoint = None
        self.last_json = None

    def post(self, endpoint, **kwargs):
        self.last_endpoint = endpoint
        self.last_json = kwargs.get("json")
        return _FakePostContext(_FakeResponse(self.lines))


@pytest.mark.asyncio
async def test_gemini_stream_is_incremental_and_captures_grounding():
    events = [
        {
            "candidates": [{
                "content": {"parts": [{"text": "Hel"}]},
            }]
        },
        {
            "candidates": [{
                "content": {"parts": [{"text": "lo"}]},
                "groundingMetadata": {
                    "webSearchQueries": ["latest test query"],
                    "groundingChunks": [{
                        "web": {
                            "uri": "https://example.com/live",
                            "title": "Example Live",
                        }
                    }],
                },
            }]
        },
    ]
    lines = [
        ("data: " + json.dumps(event) + "\n").encode("utf-8")
        for event in events
    ]

    manager = AIResilienceManager()
    manager.session = _FakeSession(lines)
    model = AIModelConfig(
        name="Gemini",
        endpoint=(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent"
        ),
        api_key="test-key-long-enough",
    )
    metadata = {}

    chunks = [
        chunk
        async for chunk in manager._stream_gemini(
            "gemini-2.5-flash",
            model,
            [{"role": "user", "content": "What's happening today?"}],
            0.6,
            100,
            thinking_budget=0,
            enable_google_search=True,
            metadata_sink=metadata,
        )
    ]

    assert chunks == ["Hel", "lo"]
    assert ":streamGenerateContent?alt=sse" in manager.session.last_endpoint
    assert manager.session.last_json["generationConfig"]["thinkingConfig"] == {
        "thinkingBudget": 0
    }
    assert manager.session.last_json["tools"] == [{"google_search": {}}]
    assert metadata["search_queries"] == ["latest test query"]
    assert metadata["sources"] == [{
        "url": "https://example.com/live",
        "title": "Example Live",
    }]


@pytest.mark.asyncio
async def test_gemini_stream_suppresses_hidden_thought_parts():
    event = {
        "candidates": [{
            "content": {
                "parts": [
                    {"text": "hidden reasoning", "thought": True},
                    {"text": "visible answer"},
                ]
            }
        }]
    }
    manager = AIResilienceManager()
    manager.session = _FakeSession([
        ("data: " + json.dumps(event) + "\n").encode("utf-8")
    ])
    model = AIModelConfig(
        name="Gemini",
        endpoint=(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent"
        ),
        api_key="test-key-long-enough",
    )

    chunks = [
        chunk
        async for chunk in manager._stream_gemini(
            "gemini-2.5-flash",
            model,
            [{"role": "user", "content": "hello"}],
            0.6,
            100,
            thinking_budget=0,
        )
    ]

    assert chunks == ["visible answer"]
