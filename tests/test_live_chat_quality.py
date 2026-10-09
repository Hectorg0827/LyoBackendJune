"""Reject the false-positive conditions reproduced in the quality review."""
import json

import httpx
import pytest

from scripts.live_chat_quality import Scenario, _observe, _turn


def valid_events(answer="4"):
    return [
        {"type": "interaction_contract", "mode": "answer"},
        {"type": "text_delta", "content": answer, "_received_ms": 100},
        {"type": "answer", "generation_status": "completed", "block": {"content": {"text": answer}}},
        {"type": "validation_done"},
    ]


def test_observer_accepts_completed_measured_answer():
    assert _observe(Scenario("direct", "", "answer", r"\b4\b"), valid_events(), 200).passed


@pytest.mark.parametrize("defect", ["incomplete", "error", "no_deltas", "no_done", "slow", "leading_question", "buffered"])
def test_observer_rejects_false_positive_completion_and_latency(defect):
    events = valid_events()
    wall_ms = 200
    if defect == "incomplete":
        events[2]["generation_status"] = "incomplete"
    elif defect == "error":
        events.append({"type": "error", "message": "provider failed"})
    elif defect == "no_deltas":
        events.pop(1)
    elif defect == "no_done":
        events.pop()
    elif defect == "slow":
        wall_ms = 80_000
        events.append({"type": "latency", "metrics": {"total_ms": 0}})
    elif defect == "leading_question":
        events[2]["block"]["content"]["text"] = "Could you first tell me your level? The answer is 4."
    elif defect == "buffered":
        events[1]["_received_ms"] = 5000
    assert not _observe(Scenario("direct", "", "answer", r"\b4\b"), events, wall_ms).passed


def test_empty_source_navigator_is_not_a_comparison():
    events = valid_events("Mitosis and meiosis")
    events.append({"type": "smart_blocks", "blocks": [{"type": "interactive", "subtype": "sourceNavigator", "content": {"items": []}}]})
    observation = _observe(Scenario("compare", "", "answer", require_structured_representation=True), events, 200)
    assert not observation.passed


def test_unrelated_sources_cannot_validate_wrong_current_claim():
    events = valid_events("Napoleon III is the current president of France.")
    events.append({"type": "sources", "sources": [{"url": "https://example.com/random", "title": "Unrelated"}]})
    scenario = Scenario("current", "", "answer", r"Emmanuel\s+Macron", require_sources=True, source_pattern="Macron")
    assert not _observe(scenario, events, 200).passed


@pytest.mark.asyncio
async def test_http_authentication_failure_remains_reportable():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))) as client:
        events, wall_ms = await _turn(client, "https://example.com", "test")
    assert events == [{"type": "validation_error", "error": "HTTPStatusError", "http_status": 401}]
    assert not _observe(Scenario("auth", "", "answer"), events, wall_ms).passed


@pytest.mark.asyncio
async def test_receiver_measures_sse_events_and_done():
    body = "\n\n".join("data: " + json.dumps(event) for event in valid_events()[:-1]) + "\n\ndata: [DONE]\n\n"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))) as client:
        events, _ = await _turn(client, "https://example.com", "test")
    assert any(event["type"] == "text_delta" and isinstance(event["_received_ms"], int) for event in events)
    assert events[-1]["type"] == "validation_done"
