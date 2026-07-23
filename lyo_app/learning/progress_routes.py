"""Canonical authenticated learning progress and course playback routes.

These routes are mounted before the legacy learning router so mobile and web clients
receive one stable contract for course detail, resume state, and lesson completion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.auth.dependencies import get_current_user
from lyo_app.auth.schemas import UserRead
from lyo_app.core.database import get_db
from lyo_app.learning.models import Course, CourseEnrollment, Lesson, LessonCompletion

router = APIRouter()


class CanonicalLessonCompletionCreate(BaseModel):
    lesson_id: int = Field(..., description="Canonical lesson ID")
    score: Optional[int] = Field(None, ge=0, le=100)
    time_spent_minutes: Optional[int] = Field(None, ge=0)


def _legacy_user_id(user: UserRead) -> int:
    """Return the integer user ID used by the existing learning tables."""
    try:
        return int(user.id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Learning progress is not yet available for this account identifier.",
        ) from exc


async def _course_with_lessons(db: AsyncSession, course_id: int) -> Course:
    result = await db.execute(
        select(Course)
        .options(selectinload(Course.lessons))
        .where(Course.id == course_id)
    )
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


async def _ensure_enrollment(
    db: AsyncSession,
    *,
    user_id: int,
    course_id: int,
) -> CourseEnrollment:
    result = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.user_id == user_id,
            CourseEnrollment.course_id == course_id,
        )
    )
    enrollment = result.scalar_one_or_none()
    if enrollment is not None:
        if not enrollment.is_active:
            enrollment.is_active = True
        return enrollment

    enrollment = CourseEnrollment(
        user_id=user_id,
        course_id=course_id,
        enrolled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        progress_percentage=0,
        is_active=True,
    )
    db.add(enrollment)
    await db.flush()
    return enrollment


async def _progress_payload(
    db: AsyncSession,
    *,
    user_id: int,
    course: Course,
    enrollment: CourseEnrollment,
) -> dict[str, Any]:
    lessons = sorted(course.lessons, key=lambda lesson: lesson.order_index)
    lesson_ids = [lesson.id for lesson in lessons]

    if lesson_ids:
        completion_result = await db.execute(
            select(LessonCompletion)
            .where(
                LessonCompletion.user_id == user_id,
                LessonCompletion.lesson_id.in_(lesson_ids),
            )
            .order_by(LessonCompletion.completed_at)
        )
        completions = list(completion_result.scalars().all())
    else:
        completions = []

    completed_ids = {completion.lesson_id for completion in completions}
    total_lessons = len(lessons)
    completed_lessons = len(completed_ids)
    progress_percent = (
        (completed_lessons / total_lessons) * 100.0 if total_lessons else 0.0
    )
    current_lesson = next(
        (lesson for lesson in lessons if lesson.id not in completed_ids),
        None,
    )
    remaining_minutes = sum(
        int(lesson.duration_minutes or lesson.estimated_duration_minutes or 0)
        for lesson in lessons
        if lesson.id not in completed_ids
    )

    enrollment.progress_percentage = int(round(progress_percent))
    if total_lessons and completed_lessons == total_lessons:
        enrollment.completed_at = enrollment.completed_at or datetime.now(timezone.utc).replace(tzinfo=None)
    elif completed_lessons < total_lessons:
        enrollment.completed_at = None

    last_accessed = (
        completions[-1].completed_at if completions else enrollment.enrolled_at
    )

    return {
        "course_id": str(course.id),
        "user_id": str(user_id),
        "total_lessons": total_lessons,
        "completed_lessons": completed_lessons,
        "completed_lesson_ids": [str(lesson_id) for lesson_id in sorted(completed_ids)],
        "progress_percent": progress_percent,
        "current_lesson_id": str(current_lesson.id) if current_lesson else None,
        "last_accessed_at": last_accessed.isoformat() if last_accessed else None,
        "estimated_time_remaining": remaining_minutes,
    }


@router.get("/courses/{course_id}")
async def canonical_course_detail(
    course_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Return a complete course payload with ordered playable lessons."""
    course = await _course_with_lessons(db, course_id)
    lessons = sorted(course.lessons, key=lambda lesson: lesson.order_index)
    return {
        "id": course.id,
        "title": course.title,
        "description": course.description or course.short_description or "",
        "subject": course.topic or course.category,
        "category": course.category,
        "difficulty": course.difficulty_level,
        "difficulty_level": course.difficulty_level,
        "estimated_duration_hours": course.estimated_duration_hours,
        "thumbnail_url": course.thumbnail_url,
        "is_published": course.is_published,
        "is_featured": course.is_featured,
        "created_at": course.created_at.isoformat() if course.created_at else None,
        "updated_at": course.updated_at.isoformat() if course.updated_at else None,
        "modules": [],
        "lessons": [
            {
                "id": lesson.id,
                "course_id": lesson.course_id,
                "title": lesson.title,
                "description": lesson.description,
                "content": lesson.content or lesson.summary or lesson.ai_summary or "",
                "content_type": lesson.content_type,
                "order_index": lesson.order_index,
                "duration_minutes": lesson.duration_minutes,
                "estimated_duration_minutes": lesson.estimated_duration_minutes,
                "video_url": lesson.video_url,
                "resources_url": lesson.resources_url,
                "is_published": lesson.is_published,
                "is_preview": lesson.is_preview,
            }
            for lesson in lessons
        ],
    }


@router.get("/users/me/courses/{course_id}/progress")
async def canonical_course_progress(
    course_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Hydrate the authenticated learner's canonical resume state."""
    user_id = _legacy_user_id(current_user)
    course = await _course_with_lessons(db, course_id)
    enrollment = await _ensure_enrollment(db, user_id=user_id, course_id=course_id)
    payload = await _progress_payload(
        db,
        user_id=user_id,
        course=course,
        enrollment=enrollment,
    )
    await db.commit()
    return payload


@router.post("/completions", status_code=status.HTTP_201_CREATED)
async def canonical_complete_lesson(
    completion_data: CanonicalLessonCompletionCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Persist lesson completion idempotently for the authenticated learner."""
    user_id = _legacy_user_id(current_user)

    lesson_result = await db.execute(
        select(Lesson).where(Lesson.id == completion_data.lesson_id)
    )
    lesson = lesson_result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    course = await _course_with_lessons(db, lesson.course_id)
    enrollment = await _ensure_enrollment(
        db,
        user_id=user_id,
        course_id=lesson.course_id,
    )

    existing_result = await db.execute(
        select(LessonCompletion).where(
            LessonCompletion.user_id == user_id,
            LessonCompletion.lesson_id == lesson.id,
        )
    )
    completion = existing_result.scalar_one_or_none()
    created = completion is None

    if completion is None:
        completion = LessonCompletion(
            user_id=user_id,
            lesson_id=lesson.id,
            completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
            time_spent_minutes=completion_data.time_spent_minutes,
        )
        db.add(completion)
        await db.flush()
    elif completion_data.time_spent_minutes is not None:
        completion.time_spent_minutes = completion_data.time_spent_minutes

    progress = await _progress_payload(
        db,
        user_id=user_id,
        course=course,
        enrollment=enrollment,
    )
    await db.commit()
    await db.refresh(completion)

    return {
        "id": str(completion.id),
        "user_id": str(user_id),
        "lesson_id": str(completion.lesson_id),
        "completed_at": completion.completed_at.isoformat(),
        "time_spent_minutes": completion.time_spent_minutes,
        "score": completion_data.score,
        "xp_awarded": 0,
        "created": created,
        "progress": progress,
    }
