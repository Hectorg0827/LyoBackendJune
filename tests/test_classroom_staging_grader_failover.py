"""The staging grader must not strand open-written answers on one unavailable provider."""

from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom import adaptive_teaching
from lyo_app.ai_classroom.adaptive_teaching import Evaluation
from lyo_app.core.ai_resilience import _gemini_visible_text


@pytest.mark.asyncio
async def test_written_evaluation_offers_healthy_gemini_alternatives(monkeypatch):
    expected = Evaluation(
        verdict="clarify",
        confidence=0.9,
        question_clear=False,
        feedback="Please restate what the question is asking.",
    )
    completion = AsyncMock(return_value={
        "content": expected.model_dump_json(),
        "model_used": "gemini-3.8-flash",
        "tokens_used": 30,
    })
    monkeypatch.setattr(
        "lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion",
        completion,
    )
    result = await adaptive_teaching.model_json(
        "Evaluate the meaning of this answer", {"new_answer": "Subtract 3 first."}, Evaluation,
    )
    assert result.verdict == "clarify"
    order = completion.await_args.kwargs["provider_order"]
    assert order == [
        "gpt-4o-mini", "gpt-4o", "gemini-3.8-flash",
        "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite",
    ]
    # The provider can change, but never invent a grade or omit the rubric.
    assert "Evaluate the meaning" in completion.await_args.kwargs["messages"][0]["content"]


def test_gemini_text_parser_accepts_real_generated_text_and_skips_thoughts():
    response = {
        "candidates": [{"content": {"parts": [
            {"thought": True, "text": "private reasoning"},
            {"text": '{"verdict":"partial"}'},
        ]}}],
    }
    assert _gemini_visible_text(response) == '{"verdict":"partial"}'


@pytest.mark.parametrize("response", [
    {"candidates": []},
    {"candidates": [{"finishReason": "MAX_TOKENS"}]},
    {"candidates": [{"finishReason": "SAFETY", "content": {}}]},
    {"candidates": [{"content": {"parts": [{"thought": True, "text": "thinking"}]}}]},
])
def test_gemini_missing_text_is_retryable_provider_failure_not_a_grade(response):
    with pytest.raises(RuntimeError, match="no (candidates|text)"):
        _gemini_visible_text(response)
