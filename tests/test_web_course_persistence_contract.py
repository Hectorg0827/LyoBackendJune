"""Unit acceptance for authenticated, truthful course persistence (no external DB)."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from lyo_app.learning import routes as api


class DummyCourse:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = None
        self.created_at = datetime(2026, 11, 22)
        self.updated_at = datetime(2026, 11, 22)


class DummyLesson:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def make_session(objects, *, fail_commit=False):
    async def flush():
        objects[0].id = 123

    async def commit():
        if fail_commit:
            raise RuntimeError("simulated database outage")

    return SimpleNamespace(
        add=lambda obj: objects.append(obj),
        flush=AsyncMock(side_effect=flush),
        commit=AsyncMock(side_effect=commit),
        rollback=AsyncMock(),
        refresh=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_course_commits_owned_modules_and_lessons(monkeypatch):
    monkeypatch.setattr(api, "Course", DummyCourse)
    monkeypatch.setattr(api, "Lesson", DummyLesson)
    rows = []
    db = make_session(rows)
    request = api._IosCourseCreate(
        title="Intermediate Algebra QA", difficulty="intermediate",
        instructor_id=99999,  # malicious client-side owner override
        modules=[{
            "title": "Equations", "lessons": [{
                "title": "Linear equations", "content": "Solve x + 2 = 4",
                "duration_minutes": 12,
            }],
        }],
    )
    response = await api.create_course(request, db, SimpleNamespace(id=17))
    assert response["id"] == "123"
    assert response["instructor_id"] == "17"
    assert response["difficulty_level"] == "intermediate"
    assert response["modules"][0]["lessons"][0]["title"] == "Linear equations"
    assert rows[0].instructor_id == 17
    assert len(rows) == 2
    assert rows[1].course_id == 123
    assert rows[1].content == "Solve x + 2 = 4"
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_database_write_never_returns_fake_201(monkeypatch):
    monkeypatch.setattr(api, "Course", DummyCourse)
    monkeypatch.setattr(api, "Lesson", DummyLesson)
    rows = []
    db = make_session(rows, fail_commit=True)
    with pytest.raises(HTTPException) as caught:
        await api.create_course(api._IosCourseCreate(title="Must persist"),
                                db, SimpleNamespace(id=3))
    assert caught.value.status_code == 503
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_private_course_not_readable_by_another_student(monkeypatch):
    private = DummyCourse(
        title="Private Algebra", topic="Algebra", description="",
        difficulty_level="intermediate", instructor_id=17,
        is_published=False, estimated_duration_hours=1,
        generation_metadata={"modules": []},
    )
    private.id = 123
    monkeypatch.setattr(api.learning_service, "get_course_by_id",
                        AsyncMock(return_value=private))
    monkeypatch.setattr(api, "get_current_user",
                        AsyncMock(return_value=SimpleNamespace(id=18)))
    with pytest.raises(HTTPException) as caught:
        await api.get_course(123, SimpleNamespace(), SimpleNamespace(credentials="synthetic"))
    assert caught.value.status_code == 404
