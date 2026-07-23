from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_canonical_learning_routes_are_declared():
    source = _source("lyo_app/learning/progress_routes.py")
    assert '@router.get("/courses/{course_id}")' in source
    assert '@router.get("/users/me/courses/{course_id}/progress")' in source
    assert '@router.post("/completions"' in source
    assert "Depends(get_current_user)" in source


def test_canonical_routes_are_prepended_to_legacy_router():
    bootstrap = _source("lyo_app/learning/progress_bootstrap.py")
    assert "legacy_routes.router.routes = list(router.routes) + list(legacy_routes.router.routes)" in bootstrap


def test_versioned_router_mounts_canonical_learning_contract():
    api_v1 = _source("lyo_app/api/v1/__init__.py")
    assert "from lyo_app.learning.progress_bootstrap import router as learning_progress_router" in api_v1
    assert 'prefix="/learning"' in api_v1


def test_progress_contract_exposes_stable_resume_fields():
    source = _source("lyo_app/learning/progress_routes.py")
    for field in (
        '"total_lessons"',
        '"completed_lessons"',
        '"completed_lesson_ids"',
        '"progress_percent"',
        '"current_lesson_id"',
        '"last_accessed_at"',
        '"estimated_time_remaining"',
    ):
        assert field in source


def test_completion_contract_is_idempotent():
    source = _source("lyo_app/learning/progress_routes.py")
    assert "completion = existing_result.scalar_one_or_none()" in source
    assert "created = completion is None" in source
    assert '"created": created' in source
