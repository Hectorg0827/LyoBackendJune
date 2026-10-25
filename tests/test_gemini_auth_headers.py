"""Gemini authorization keys must never be embedded in request URLs.

New AI Studio auth keys can be rejected when sent via the legacy ?key=
transport. Both regular and streaming generation use x-goog-api-key.
No network or real secrets are used by these tests.
"""
import pytest

from lyo_app.core.ai_resilience import AIModelConfig, AIResilienceManager


class StopRequest(Exception):
    pass


class CapturingSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self

    async def __aenter__(self):
        raise StopRequest()

    async def __aexit__(self, *args):
        return None


def config():
    return AIModelConfig(
        name="Google Gemini 3.8 Flash",
        endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
        api_key="test-secret-never-print",
        max_tokens=300,
        priority=1,
        capabilities=["chat"],
    )


def check_call(method, url, options):
    assert method in ("POST", "GET")
    assert "test-secret-never-print" not in url
    assert "key=" not in url
    assert options["headers"]["x-goog-api-key"] == "test-secret-never-print"


@pytest.mark.asyncio
async def test_gemini_generate_content_uses_header_not_query():
    manager = AIResilienceManager()
    manager.session = CapturingSession()
    with pytest.raises(StopRequest):
        await manager._make_api_call_with_messages(
            "gemini-3.8-flash", config(),
            [{"role": "user", "content": "Teach fractions"}],
            temperature=0.2, max_tokens=300,
        )
    assert len(manager.session.calls) == 1
    check_call(*manager.session.calls[0])


@pytest.mark.asyncio
async def test_gemini_stream_content_uses_header_not_query():
    manager = AIResilienceManager()
    manager.session = CapturingSession()
    stream = manager._stream_gemini(
        "gemini-3.8-flash", config(),
        [{"role": "user", "content": "Teach fractions"}],
        temperature=0.2, max_tokens=300,
    )
    with pytest.raises(StopRequest):
        await anext(stream)
    assert len(manager.session.calls) == 1
    method, url, options = manager.session.calls[0]
    check_call(method, url, options)
    assert "alt=sse" in url


@pytest.mark.asyncio
async def test_gemini_prewarm_uses_header_not_query():
    manager = AIResilienceManager()
    manager.session = CapturingSession()
    manager.models = {"gemini-3.8-flash": config()}
    await manager._prewarm_connections()
    assert len(manager.session.calls) == 1
    check_call(*manager.session.calls[0])

 
@pytest.mark.parametrize(
    "budget,expected_level",
    [(0, "low"), (256, "medium"), (-1, "high")],
)
@pytest.mark.asyncio
async def test_gemini_38_stream_uses_thinking_levels_not_numeric_budgets(
    budget, expected_level,
):
    manager = AIResilienceManager()
    manager.session = CapturingSession()
    stream = manager._stream_gemini(
        "gemini-3.8-flash", config(),
        [{"role": "user", "content": "Explain fractions"}],
        temperature=0.2, max_tokens=300,
        thinking_budget=budget,
    )
    with pytest.raises(StopRequest):
        await anext(stream)
    payload = manager.session.calls[0][2]["json"]
    thinking = payload["generationConfig"]["thinkingConfig"]
    assert thinking == {"thinkingLevel": expected_level}
    assert "thinkingBudget" not in thinking
