import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_study import clean_routes
from lyo_app.classroom import analytics as classroom_analytics


def test_production_app_mounts_classroom_analytics_route():
    source = Path("lyo_app/enhanced_main.py").read_text(encoding="utf-8")

    assert "from lyo_app.classroom.analytics import router as classroom_analytics_router" in source
    assert 'prefix="/api/v1/classroom/analytics"' in source


def test_classroom_analytics_accepts_current_unscoped_ui_events():
    event = classroom_analytics.LyoAnalyticsEvent(
        event_type="classroom_advance_tapped",
        courseId="course-123",
        card_count=4,
    )

    assert event.event_type == "classroom_advance_tapped"
    assert event.card_id is None
    dumped = event.model_dump()
    assert dumped["courseId"] == "course-123"
    assert dumped["card_count"] == 4


@pytest.mark.asyncio
async def test_unscoped_classroom_event_uses_system_telemetry(monkeypatch):
    system_event = AsyncMock()
    interaction = AsyncMock()
    monkeypatch.setattr(classroom_analytics.analytics_service, "track_system_event", system_event)
    monkeypatch.setattr(classroom_analytics.analytics_service, "track_interaction", interaction)

    event = classroom_analytics.LyoAnalyticsEvent(
        event_type="classroom_drawer_opened",
        courseId="course-123",
        narration_was_active=True,
    )
    result = await classroom_analytics.track_analytics_event(event)

    assert result["status"] == "success"
    interaction.assert_not_awaited()
    system_event.assert_awaited_once()
    event_name, properties = system_event.await_args.args
    assert event_name == "classroom_drawer_opened"
    assert properties["courseId"] == "course-123"
    assert properties["narration_was_active"] is True


@pytest.mark.asyncio
async def test_card_event_remains_a_durable_interaction(monkeypatch):
    system_event = AsyncMock()
    interaction = AsyncMock()
    monkeypatch.setattr(classroom_analytics.analytics_service, "track_system_event", system_event)
    monkeypatch.setattr(classroom_analytics.analytics_service, "track_interaction", interaction)

    event = classroom_analytics.LyoAnalyticsEvent(
        event_type="quiz_answered",
        card_id="quiz-1",
        topic="fractions",
        is_correct=True,
    )
    await classroom_analytics.track_analytics_event(event)

    system_event.assert_not_awaited()
    interaction.assert_awaited_once_with(
        event_type="quiz_answered",
        card_id="quiz-1",
        topic="fractions",
        duration_seconds=None,
        is_correct=True,
        word_count=None,
    )


@pytest.mark.asyncio
async def test_legacy_public_course_chat_returns_without_running_a2a(monkeypatch):
    chat_completion = AsyncMock(
        return_value={
            "content": (
                "Course Title: Fractions\n"
                "Module 1: Comparing fractions - Build common denominators."
            )
        }
    )
    monkeypatch.setattr(clean_routes.ai_resilience_manager, "session", object())
    monkeypatch.setattr(
        clean_routes.ai_resilience_manager,
        "chat_completion",
        chat_completion,
    )

    response = await asyncio.wait_for(
        clean_routes.public_chat_endpoint(
            clean_routes.ChatRequest(
                message="Create a course on comparing fractions",
                context="mode=course",
            )
        ),
        timeout=1.0,
    )

    assert chat_completion.await_count == 1
    assert response.response.startswith("Course Title: Fractions")
    assert any(block.type == "course_roadmap" for block in response.ui_component)

    endpoint_source = Path("lyo_app/ai_study/clean_routes.py").read_text(encoding="utf-8")
    public_chat_source = endpoint_source.split("@router.post(\"/chat\")", 1)[1].split(
        "# COURSE GENERATION ENDPOINT", 1
    )[0]
    assert "A2AOrchestrator" not in public_chat_source
    assert "orchestrator.generate_course" not in public_chat_source
