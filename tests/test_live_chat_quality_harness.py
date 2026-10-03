import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "live_chat_quality.py"
SPEC = importlib.util.spec_from_file_location("live_chat_quality", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


def test_parse_sse_ignores_done_and_preserves_events():
    events = module.parse_sse(
        'data: {"type":"interaction_contract","mode":"answer"}\n\n'
        'data: {"type":"answer","block":{"content":{"text":"Paris"}}}\n\n'
        'data: [DONE]\n\n'
    )
    assert [event["type"] for event in events] == [
        "interaction_contract",
        "answer",
    ]


def test_answer_text_reads_tutor_message_block():
    events = [
        {"type": "answer", "block": {"content": {"text": "Paris"}}},
        {"type": "sources", "sources": []},
    ]
    assert module.answer_text(events) == "Paris"


def test_contract_and_source_helpers_are_strict():
    events = [
        {"type": "interaction_contract", "mode": "compare"},
        {"type": "sources", "sources": [{"name": "Source"}]},
    ]
    assert module.contract_event(events)["mode"] == "compare"
    assert module.source_event(events)["sources"][0]["name"] == "Source"
    assert module.has_clarification(events) is False


def test_require_https_rejects_plain_http_by_default():
    try:
        module.require_https("http://example.com")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("plain HTTP should be rejected")
