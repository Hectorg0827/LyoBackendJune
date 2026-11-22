"""Canonical course route must not erase persisted modules or leak drafts."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from lyo_app.learning import progress_routes as route


def private_course():
    return SimpleNamespace(
        id=7,
        instructor_id=41,
        title="Algebra",
        topic="Algebra",
        description="",
        short_description="",
        category=None,
        difficulty_level="intermediate",
        estimated_duration_hours=1,
        thumbnail_url=None,
        is_published=False,
        is_featured=False,
        created_at=datetime(2026, 11, 22),
        updated_at=datetime(2026, 11, 22),
        generation_metadata={"modules": [{
            "title": "Equations",
            "lessons": [{"title": "Solve linear equations"}],
        }]},
        lessons=[],
    )


@pytest.mark.asyncio
async def test_owner_can_reload_authoritative_persisted_modules(monkeypatch):
    monkeypatch.setattr(route, "_course_with_lessons",
                        AsyncMock(return_value=private_course()))
    monkeypatch.setattr(route, "get_current_user",
                        AsyncMock(return_value=SimpleNamespace(id=41)))
    response = await route.canonical_course_detail(
        7, SimpleNamespace(), SimpleNamespace(credentials="synthetic"))
    assert response["modules"][0]["title"] == "Equations"
    assert response["modules"][0]["lessons"][0]["title"] == "Solve linear equations"


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_id", [None, 42])
async def test_private_course_is_hidden_from_guests_and_other_users(monkeypatch, owner_id):
    monkeypatch.setattr(route, "_course_with_lessons",
                        AsyncMock(return_value=private_course()))
    monkeypatch.setattr(route, "get_current_user",
                        AsyncMock(return_value=SimpleNamespace(id=owner_id)))
    bearer = None if owner_id is None else SimpleNamespace(credentials="synthetic")
    with pytest.raises(HTTPException) as error:
        await route.canonical_course_detail(7, SimpleNamespace(), bearer)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_private_course_progress_denied_for_other_student(monkeypatch):
    monkeypatch.setattr(route, "_course_with_lessons",
                        AsyncMock(return_value=private_course()))
    monkeypatch.setattr(route, "_ensure_enrollment", AsyncMock())
    with pytest.raises(HTTPException) as error:
        await route.canonical_course_progress(
            7, SimpleNamespace(id=42), SimpleNamespace())
    assert error.value.status_code == 404
    route._ensure_enrollment.assert_not_awaited()
