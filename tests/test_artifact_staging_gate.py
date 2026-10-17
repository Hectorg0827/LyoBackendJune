"""The live acceptance runner must fail closed before it can report success."""
import json
from types import SimpleNamespace

import httpx
import pytest

from scripts.validate_artifact_recovery_staging import completed_answer, decode_sse, require_target, verify_health


SHA = "a" * 40
HEALTH = {"environment": "staging", "commit_sha": SHA,
          "services": {"database": "healthy", "firebase": "enabled"}}


@pytest.mark.parametrize("url", [
    "https://api.lyoai.app", "http://test.up.railway.app",
    "https://token@test.up.railway.app", "https://test.up.railway.app/path",
    "https://test.up.railway.app?token=secret", "https://test.up.railway.app.evil.example",
    "https://test.up.railway.app", "https://lyolaunchbackend-staging.up.railway.app.evil.example",
])
def test_live_runner_rejects_unsafe_targets(url):
    with pytest.raises(ValueError):
        require_target(url, SHA)


@pytest.mark.parametrize("url", [
    "https://lyolaunchbackend-staging.up.railway.app",
    "https://lyojourneystagingbackend-staging.up.railway.app",
])
def test_live_runner_only_accepts_reserved_staging_backends(url):
    assert require_target(url, SHA) == url


@pytest.mark.parametrize("changes", [
    {"commit_sha": "b" * 40}, {"environment": "production"},
    {"services": {"database": "healthy", "firebase": "disabled"}},
    {"services": {"database": "unhealthy", "firebase": "enabled"}},
])
def test_live_runner_rejects_wrong_revision_or_unready_storage(changes):
    with pytest.raises(ValueError):
        verify_health({**HEALTH, **changes}, SHA)


def valid_events():
    return [{"type": "answer", "generation_status": "completed", "block": {
        "content": {"text": "Reopen that material and try again."},
    }}, {"type": "DONE"}]


@pytest.mark.parametrize("failure", ["incomplete", "voice_incomplete", "error", "missing_done", "no_status", "artifact"])
def test_live_runner_rejects_false_positive_streams(failure):
    events = valid_events()
    if failure in {"incomplete", "no_status"}:
        events[0]["generation_status"] = "incomplete" if failure == "incomplete" else None
    elif failure == "missing_done":
        events.pop()
    else:
        events.insert(1, {"type": failure})
    with pytest.raises(AssertionError):
        completed_answer(events, expect_artifact=False)


def test_valid_completed_recovery_passes_only_with_done():
    events = valid_events()
    raw = "data: " + json.dumps(events[0]) + "\n\ndata: [DONE]\n\n"
    assert completed_answer(decode_sse(raw), expect_artifact=False) == events[0]
    verify_health(HEALTH, SHA)


@pytest.mark.parametrize("tail", ["data: [DONE]", 'data: {"type":', 'data: []\n\n'])
def test_truncated_or_malformed_frames_never_pass(tail):
    raw = "data: " + json.dumps(valid_events()[0]) + "\n\n" + tail
    with pytest.raises(ValueError):
        decode_sse(raw)


@pytest.mark.asyncio
async def test_revision_failure_stops_before_authentication_or_fixture_writes(monkeypatch, tmp_path):
    from scripts import validate_artifact_recovery_staging as gate

    calls = []

    def respond(request):
        calls.append((request.method, request.url.path))
        assert "authorization" not in request.headers
        return httpx.Response(200, json={**HEALTH, "commit_sha": "b" * 40})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(gate.httpx, "AsyncClient", lambda **kwargs: client)
    report_path = tmp_path / "report.json"
    result = await gate.run(SimpleNamespace(url="https://lyolaunchbackend-staging.up.railway.app", expected_sha=SHA,
                                          preflight_only=False, report=report_path))
    assert result == 2
    assert calls == [("GET", "/health")]
    report = json.loads(report_path.read_text())
    assert report["status"] == "blocked"
    assert report["before"]["commit_sha"] == "b" * 40
    assert report["checks"] == []


@pytest.mark.asyncio
async def test_history_verification_uses_the_public_message_contract():
    from scripts.validate_artifact_recovery_staging import verify_history

    answer = valid_events()[0]
    events = [{"type": "conversation", "conversation_id": "synthetic"}, answer]
    history = {"messages": [{"id": "saved-row", "role": "assistant", "generation_status": "completed",
                             "content": answer["block"]["content"]["text"]}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=history))) as client:
        await verify_history(client, "https://test.up.railway.app", "fixture-token", events, answer)
