import logging

import pytest
from pydantic import ValidationError

from lyo_app.api.v1.chat_lyo2 import VoiceQualityEvent, report_voice_quality


def test_voice_quality_event_forbids_transcript_or_audio_fields() -> None:
    with pytest.raises(ValidationError):
        VoiceQualityEvent(
            session_id="qa-session",
            platform="web",
            event="first_audio",
            transcript="private learner speech",
        )

    with pytest.raises(ValidationError):
        VoiceQualityEvent(
            session_id="qa-session",
            platform="web",
            event="first_audio",
            audio="base64-audio",
        )


@pytest.mark.asyncio
async def test_voice_quality_event_logs_only_bounded_metadata(caplog) -> None:
    payload = VoiceQualityEvent(
        session_id="qa-session",
        turn_id="turn-1",
        conversation_id="conversation-1",
        platform="web",
        event="first_audio",
        locale="en-US",
        scenario="live_conversation",
        metrics={
            "submit_to_audio_ms": 812,
            "mic_to_audio_ms": 2410,
            **{f"extra_{index}": index for index in range(30)},
        },
    )

    class Guest:
        id = 0

    with caplog.at_level(logging.INFO):
        result = await report_voice_quality(payload, current_user=Guest())

    assert result == {"status": "recorded"}
    lines = [record.getMessage() for record in caplog.records if "VOICE_QUALITY" in record.getMessage()]
    assert len(lines) == 1
    assert "submit_to_audio_ms" in lines[0]
    assert "mic_to_audio_ms" in lines[0]
    assert "private learner speech" not in lines[0]
    # Endpoint caps arbitrary metric keys before emitting structured logs.
    assert "extra_29" not in lines[0]
