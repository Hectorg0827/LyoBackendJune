from lyo_app.ai.schemas.lyo2 import RouterRequest
from lyo_app.api.v1.stream_lyo2 import _speech_segments, _speech_text
from lyo_app.teaching_runtime.interaction_contract import interaction_contract_for_request


def test_voice_is_delivery_metadata_on_canonical_router_request() -> None:
    request = RouterRequest(
        text="Explain photosynthesis",
        delivery_mode="voice",
        voice_turn_id="turn-123",
    )

    assert request.delivery_mode == "voice"
    assert request.voice_turn_id == "turn-123"


def test_voice_does_not_change_interaction_contract() -> None:
    typed = interaction_contract_for_request(text="Explain photosynthesis")
    spoken = interaction_contract_for_request(text="Explain photosynthesis")

    assert spoken == typed
    assert spoken.mode.value == "explain"


def test_speech_text_keeps_meaning_but_removes_visual_markup() -> None:
    raw = (
        "## Rent summary\n"
        "**Monthly rent:** $2,100 【lease.pdf p. 1】\n"
        "- See [the document](/api/v1/media/file/chat/lease.pdf)."
    )

    spoken = _speech_text(raw)

    assert "Monthly rent: $2,100" in spoken
    assert "lease.pdf p. 1" not in spoken
    assert "##" not in spoken
    assert "**" not in spoken
    assert "/api/v1/media" not in spoken


def test_speech_text_preserves_fenced_code_contents() -> None:
    spoken = _speech_text("Use this:\n\n```python\nprint('hello')\n```")

    assert "print('hello')" in spoken
    assert "```" not in spoken
    assert "python" not in spoken


def test_speech_segments_are_interruptible_and_bounded() -> None:
    raw = " ".join(
        f"Sentence {index} explains one useful idea." for index in range(1, 80)
    )

    segments = _speech_segments(raw, max_chars=180)

    assert len(segments) > 1
    assert all(segment.strip() for segment in segments)
    assert all(len(segment) <= 180 for segment in segments)


def test_speech_segments_preserve_question_turns() -> None:
    segments = _speech_segments(
        "The answer is 12. Why? Because 3 times 4 equals 12. Want to try one?"
    )

    assert segments
    assert segments[-1].endswith("?")
