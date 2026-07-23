from lyo_app.learning.progress_routes import (
    CanonicalLessonCompletionCreate,
    router as canonical_router,
)
from lyo_app.learning.progress_bootstrap import legacy_routes


def _route_pairs(router):
    return [
        (route.path, tuple(sorted(route.methods or [])))
        for route in router.routes
        if hasattr(route, "methods")
    ]


def test_canonical_learning_routes_are_declared():
    pairs = _route_pairs(canonical_router)
    assert ("/courses/{course_id}", ("GET",)) in pairs
    assert ("/users/me/courses/{course_id}/progress", ("GET",)) in pairs
    assert ("/completions", ("POST",)) in pairs


def test_canonical_routes_precede_legacy_duplicates():
    paths = [route.path for route in legacy_routes.router.routes]
    assert paths.index("/courses/{course_id}") < paths.index("/courses/{course_id}", 1)
    assert paths.index("/completions") < paths.index("/completions", 1)


def test_completion_payload_accepts_score_without_requiring_it():
    basic = CanonicalLessonCompletionCreate(lesson_id=42)
    assessed = CanonicalLessonCompletionCreate(lesson_id=42, score=85)
    assert basic.score is None
    assert assessed.score == 85
