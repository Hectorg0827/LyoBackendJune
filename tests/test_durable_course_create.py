"""Regression: generated courses must survive reload, and never claim a phantom save."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from lyo_app.learning.models import Course, Lesson
from lyo_app.learning.routes import (
    _IosCourseCreate, _IosModule, _IosLesson, create_course, get_my_courses,
)


def sample_course():
    return _IosCourseCreate(
        title="Fractions", topic="Fractions", instructor_id="999999",
        modules=[_IosModule(
            title="Parts of a whole",
            lessons=[_IosLesson(title="Halves", duration_minutes=8, content="1/2 is one of two equal parts")],
        )],
    )


@pytest.mark.asyncio
async def test_generated_course_and_lessons_are_durable_and_owned(db_session):
    from lyo_app.auth.models import User
    from lyo_app.tenants.models import Organization

    org = await db_session.get(Organization, 1)
    if org is None:
        db_session.add(Organization(id=1, name="Lyo Test", slug="lyo-durable-course-test"))
    user = User(email="durable-course@example.test", username="durable-course", hashed_password="unused")
    db_session.add(user)
    await db_session.commit()
    user_id = user.id
    response = await create_course(sample_course(), db_session, user)

    assert response["id"].isdigit() and response["instructor_id"] == str(user.id)
    assert response["lesson_count"] == 1
    assert response["modules"][0]["lessons"][0]["id"].isdigit()
    saved_id = int(response["id"])

    db_session.expire_all()  # Simulate a fresh request reading durable rows.
    saved = await db_session.get(Course, saved_id)
    assert saved is not None and saved.title == "Fractions" and saved.instructor_id == user_id
    lesson = (await db_session.execute(select(Lesson).where(Lesson.course_id == saved_id))).scalar_one()
    assert str(lesson.id) == response["modules"][0]["lessons"][0]["id"]
    assert lesson.content == "1/2 is one of two equal parts"
    assert saved.generation_metadata["modules"][0]["lessons"][0]["id"] == str(lesson.id)

    mine = await get_my_courses(current_user=SimpleNamespace(id=user_id), db=db_session)
    assert any(item.id == saved_id and item.lesson_count == 1 for item in mine)


@pytest.mark.asyncio
async def test_database_failure_never_returns_a_successful_local_course():
    db = SimpleNamespace(
        add=Mock(),
        flush=AsyncMock(side_effect=SQLAlchemyError("database unavailable")),
        commit=AsyncMock(),
        refresh=AsyncMock(),
        rollback=AsyncMock(),
    )
    with pytest.raises(HTTPException) as exc:
        await create_course(sample_course(), db, SimpleNamespace(id=42))
    assert exc.value.status_code == 503
    assert "not saved" in exc.value.detail
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
