"""
Learning routes for course and lesson management.
Provides FastAPI endpoints for the learning module.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Annotated, List, Optional, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from lyo_app.learning.schemas import (
    CourseCreate, CourseRead, CourseUpdate, CourseListResponse,
    LessonCreate, LessonRead, LessonUpdate,
    CourseEnrollmentCreate, CourseEnrollmentRead,
    LessonCompletionCreate, LessonCompletionRead,
    UserProgressResponse, ProofRead
)
from lyo_app.learning.service import LearningService
from lyo_app.learning.models import Course, Lesson
from lyo_app.learning.proofs import ProofEngine
from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user
from lyo_app.auth.schemas import UserRead
from lyo_app.models.enhanced import User

logger = logging.getLogger(__name__)

router = APIRouter()
learning_service = LearningService()
proof_engine = ProofEngine()
_optional_course_bearer = HTTPBearer(auto_error=False)


# ── iOS-compatible flexible course creation ────────────────────────────────────

class _IosLesson(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[str] = None
    duration_minutes: Optional[int] = None
    content: Optional[Any] = None

class _IosModule(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    lessons: Optional[List[_IosLesson]] = []

class _IosCourseCreate(BaseModel):
    """Flexible schema matching what the iOS app actually POSTs."""
    id: Optional[str] = None
    title: Optional[str] = None
    topic: Optional[str] = None
    subject: Optional[str] = None
    level: Optional[str] = None
    difficulty_level: Optional[str] = None
    difficulty: Optional[str] = None
    description: Optional[str] = None
    modules: Optional[List[_IosModule]] = []
    instructor_id: Optional[Any] = None  # accepts int, str, UUID
    estimated_hours: Optional[float] = None


@router.get("/proofs", response_model=List[ProofRead])
async def get_my_proofs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[ProofRead]:
    """Get all proofs of learning for the current user."""
    return await proof_engine.get_user_proofs(db, current_user.id)


def _persisted_course_payload(course: Course) -> Dict[str, Any]:
    """Return only values actually committed to the database."""
    metadata = course.generation_metadata or {}
    modules = metadata.get("modules") if isinstance(metadata, dict) else []
    return {
        "id": str(course.id),
        "title": course.title,
        "topic": course.topic or course.title,
        "description": course.description,
        "difficulty": course.difficulty_level,
        "difficulty_level": course.difficulty_level,
        "modules": modules if isinstance(modules, list) else [],
        "instructor_id": str(course.instructor_id),
        "is_published": bool(course.is_published),
        "created_at": course.created_at.isoformat() if course.created_at else None,
        "updated_at": course.updated_at.isoformat() if course.updated_at else None,
        "estimated_duration_hours": course.estimated_duration_hours,
    }


@router.post("/courses", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_course(
    course_data: _IosCourseCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[UserRead, Depends(get_current_user)],
) -> Dict[str, Any]:
    """Atomically save an authenticated learner's course and lesson content.

    Never return HTTP 201 if persistence fails. Client-supplied instructor
    identifiers are intentionally ignored, preventing ownership spoofing.
    """
    topic = (course_data.topic or course_data.subject or course_data.title or "").strip()
    title = (course_data.title or topic or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="Course title or topic required")
    difficulty = (
        course_data.difficulty_level or course_data.difficulty
        or course_data.level or "beginner"
    ).lower()
    if difficulty not in {"beginner", "intermediate", "advanced"}:
        raise HTTPException(status_code=422, detail="Invalid difficulty")
    if len(title) > 200 or len(topic) > 200:
        raise HTTPException(status_code=422, detail="Course title or topic too long")

    modules = [module.model_dump(mode="json") for module in (course_data.modules or [])]
    try:
        course = Course(
            title=title,
            topic=topic or title,
            description=course_data.description or f"A structured course on {topic or title}",
            difficulty_level=difficulty,
            instructor_id=current_user.id,
            is_published=False,
            status="draft",
            estimated_duration_hours=course_data.estimated_hours or max(len(modules) * 0.5, 1),
            generation_metadata={"modules": modules},
        )
        db.add(course)
        await db.flush()
        index = 0
        for module in (course_data.modules or []):
            for lesson in (module.lessons or []):
                index += 1
                body = lesson.content
                # The reader uses structured blocks while the SQL lesson column
                # is TEXT. Persist JSON for non-string content, preserving the
                # original structure in course.generation_metadata.
                if not isinstance(body, (str, type(None))):
                    import json
                    body = json.dumps(body)
                db.add(Lesson(
                    course_id=course.id,
                    title=lesson.title or f"Lesson {index}",
                    content=body or "",
                    content_type="text",
                    order_index=index,
                    duration_minutes=lesson.duration_minutes or 10,
                    topic=topic or title,
                    is_published=False,
                ))
        await db.commit()
        await db.refresh(course)
        logger.info("Course committed to staging database id=%s owner=%s", course.id, current_user.id)
        return _persisted_course_payload(course)
    except Exception:
        await db.rollback()
        logger.exception("Authenticated course persistence failed")
        raise HTTPException(
            status_code=503,
            detail="Course could not be saved. Please retry; no success was recorded.",
        )


@router.get("/courses", response_model=List[Dict[str, Any]])
async def get_published_courses(
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_course_bearer),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
) -> List[Dict[str, Any]]:
    """Published courses for guests, plus the authenticated learner's drafts.

    Invalid supplied bearer credentials are rejected, not silently treated as
    guest access. Drafts belonging to a different user never appear.
    """
    owner_id = None
    if credentials is not None:
        owner = await get_current_user(credentials, db)
        owner_id = owner.id
    conditions = [Course.is_published.is_(True)]
    if owner_id is not None:
        conditions.append(Course.instructor_id == owner_id)
    rows = await db.execute(
        select(Course).where(or_(*conditions))
        .order_by(Course.created_at.desc()).offset(skip).limit(limit)
    )
    return [_persisted_course_payload(course) for course in rows.scalars().all()]


@router.get("/courses/{course_id}", response_model=Dict[str, Any])
async def get_course(
    course_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_course_bearer),
) -> Dict[str, Any]:
    course = await learning_service.get_course_by_id(db, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if not course.is_published:
        if credentials is None:
            raise HTTPException(status_code=404, detail="Course not found")
        user = await get_current_user(credentials, db)
        if course.instructor_id != user.id:
            raise HTTPException(status_code=404, detail="Course not found")
    return _persisted_course_payload(course)


@router.post("/courses/{course_id}/publish", response_model=CourseRead)
async def publish_course(
    course_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[UserRead, Depends(get_current_user)],
) -> CourseRead:
    course = await learning_service.get_course_by_id(db, course_id)
    if course is None or course.instructor_id != current_user.id:
        raise HTTPException(status_code=404, detail="Course not found")
    course = await learning_service.publish_course(db, course_id)
    return CourseRead.model_validate(course)


@router.get("/instructors/{instructor_id}/courses", response_model=List[CourseRead])
async def get_instructor_courses(
    instructor_id: int,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[CourseRead]:
    """
    Get all courses by instructor ID.
    
    Args:
        instructor_id: Instructor user ID
        db: Database session
        
    Returns:
        List of courses by the instructor
    """
    courses = await learning_service.get_courses_by_instructor(db, instructor_id)
    return [CourseRead.model_validate(course) for course in courses]


@router.post("/lessons", response_model=LessonRead, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    lesson_data: LessonCreate,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> LessonRead:
    """
    Create a new lesson.
    
    Args:
        lesson_data: Lesson creation data
        db: Database session
        
    Returns:
        Created lesson data
        
    Raises:
        HTTPException: If creation fails
    """
    try:
        lesson = await learning_service.create_lesson(db, lesson_data)
        return LessonRead.model_validate(lesson)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/courses/{course_id}/lessons", response_model=List[LessonRead])
async def get_course_lessons(
    course_id: int,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[LessonRead]:
    """
    Get all lessons for a course.
    
    Args:
        course_id: Course ID
        db: Database session
        
    Returns:
        List of lessons ordered by order_index
    """
    lessons = await learning_service.get_lessons_by_course(db, course_id)
    return [LessonRead.model_validate(lesson) for lesson in lessons]


@router.post("/lessons/{lesson_id}/publish", response_model=LessonRead)
async def publish_lesson(
    lesson_id: int,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> LessonRead:
    """
    Publish a lesson (make it available for students).
    
    Args:
        lesson_id: Lesson ID to publish
        db: Database session
        
    Returns:
        Updated lesson data
        
    Raises:
        HTTPException: If lesson not found
    """
    try:
        lesson = await learning_service.publish_lesson(db, lesson_id)
        return LessonRead.model_validate(lesson)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/enrollments", response_model=CourseEnrollmentRead, status_code=status.HTTP_201_CREATED)
async def enroll_in_course(
    enrollment_data: CourseEnrollmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    # TODO: Get current user from JWT token
    current_user_id: int = Query(..., description="Current user ID (temporary)")
) -> CourseEnrollmentRead:
    """
    Enroll in a course.
    
    Args:
        enrollment_data: Enrollment data
        db: Database session
        current_user_id: Current user ID (will be extracted from JWT token later)
        
    Returns:
        Created enrollment data
        
    Raises:
        HTTPException: If enrollment fails
    """
    try:
        enrollment = await learning_service.enroll_in_course(
            db, current_user_id, enrollment_data
        )
        return CourseEnrollmentRead.model_validate(enrollment)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/completions", response_model=LessonCompletionRead, status_code=status.HTTP_201_CREATED)
async def complete_lesson(
    completion_data: LessonCompletionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    # TODO: Get current user from JWT token
    current_user_id: int = Query(..., description="Current user ID (temporary)")
) -> LessonCompletionRead:
    """
    Mark a lesson as completed.
    
    Args:
        completion_data: Lesson completion data
        db: Database session
        current_user_id: Current user ID (will be extracted from JWT token later)
        
    Returns:
        Created completion data
        
    Raises:
        HTTPException: If completion fails
    """
    try:
        completion = await learning_service.complete_lesson(
            db, current_user_id, completion_data
        )
        return LessonCompletionRead.model_validate(completion)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/users/{user_id}/courses/{course_id}/progress", response_model=CourseEnrollmentRead)
async def get_user_course_progress(
    user_id: int,
    course_id: int,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CourseEnrollmentRead:
    """
    Get user's progress in a specific course.
    
    Args:
        user_id: User ID
        course_id: Course ID
        db: Database session
        
    Returns:
        Course enrollment with progress data
        
    Raises:
        HTTPException: If enrollment not found
    """
    progress = await learning_service.get_user_course_progress(db, user_id, course_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found"
        )
    return CourseEnrollmentRead.model_validate(progress)
