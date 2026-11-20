from pathlib import Path

from lyo_app.api.v1.stream_lyo2 import (
    _extract_course_level,
    _normalize_course_payload_for_stream,
    _resolve_course_topic,
)
from lyo_app.ai.schemas.lyo2 import ConversationTurn


def test_fast_course_preview_reflects_only_explicit_level():
    assert _extract_course_level("Create an advanced geometry course") == "advanced"
    assert _extract_course_level("Hazme un curso intermedio de geometría") == "intermediate"
    assert _extract_course_level("I want a beginner marketing course") == "beginner"
    assert _extract_course_level("Create a course on geometry") is None
    assert _extract_course_level("This is basically a geometry course") is None
    assert _extract_course_level("Compare beginner and advanced geometry") is None


def test_short_course_revision_keeps_the_existing_subject():
    history = [
        ConversationTurn(role="user", content="Create a course on math"),
        ConversationTurn(role="assistant", content="I built your course."),
    ]
    assert _resolve_course_topic("make it advanced", history) == "math"
    assert _resolve_course_topic("focus more on geometry", history) == "math"
    assert _resolve_course_topic("make it advanced", [], "Geometry") == "Geometry"


def test_explicit_course_topic_change_wins_over_history():
    history = [ConversationTurn(role="user", content="Create a course on math")]
    assert _resolve_course_topic("Adjust this course to Geometry. Make it advanced.", history) == "Geometry"
    assert _resolve_course_topic("change the topic to geometry", history) == "geometry"


def test_internal_proactive_context_never_mutates_learner_text():
    source = Path("lyo_app/api/v1/stream_lyo2.py").read_text()
    assert 'request.text = f"[Proactive Context:' not in source
    assert "routing_request = request.model_copy" in source
    assert '"proactive_context": proactive_context' in source


def test_course_stream_exposes_real_pipeline_milestones():
    source = Path("lyo_app/api/v1/stream_lyo2.py").read_text()
    for phase in ('"intent"', '"planning"', '"execution"', '"lessons"', '"finalizing"', '"ready"'):
        assert phase in source
    for progress in ('"progress": 10', '"progress": 30', '"progress": 45', '"progress": 82', '"progress": 95', '"progress": 100'):
        assert progress in source
    assert '"completed_lessons": _lesson_count' in source
    assert '"total_lessons": _lesson_count' in source
    assert '"outline": _outline' in source
    assert "'preview': True" in source
    preview_section = source[source.index("_preview_course = {"):source.index("_preview_oc =")]
    assert '"duration"' not in preview_section


def test_course_payload_normalization_drives_fallback_and_lesson_counts():
    direct = {
        "id": "course-1",
        "title": "Geometry",
        "topic": "geometry",
        "lessons": [
            {"title": "Angles", "description": "Learn angle relationships."},
            {"title": "Triangles", "description": "Apply triangle properties."},
        ],
    }
    normalized = _normalize_course_payload_for_stream(direct, "geometry")
    assert normalized == {"course": direct}
    assert len(normalized["course"]["lessons"]) == 2

    # A model failure is not an empty but supposedly completed course.
    assert _normalize_course_payload_for_stream(None, "geometry") is None
    assert _normalize_course_payload_for_stream({"course": {
        "topic": "geometry", "level": "beginner", "lessons": [],
    }}, "geometry") is None
    assert _normalize_course_payload_for_stream({"course": {
        "topic": "geometry", "modules": [
            {"title": "Unit", "lessons": [{"title": "Angles"}]},
        ],
    }}, "geometry") is not None


def test_stream_never_announces_ready_or_classroom_for_failed_generation():
    source = Path("lyo_app/api/v1/stream_lyo2.py").read_text()
    assert 'if _normalized_course_payload is None:' in source
    assert 'update={"open_classroom_payload": None}' in source
    assert '"phase": "failed"' in source
    assert 'if decision.intent == Intent.COURSE and execution_response.open_classroom_payload:' in source


def test_course_executor_never_promotes_hardcoded_syllabus_on_provider_failure():
    source = Path("lyo_app/ai/executor.py").read_text()
    course_part = source.split("async def _generate_course_data(", 1)[1].split(
        "async def _generate_lesson_content_data(", 1
    )[0]
    assert "Course generation provider unavailable" in course_part
    assert "Course generation did not produce validated JSON" in course_part
    assert "return None" in course_part
    assert "A comprehensive course about" not in course_part
