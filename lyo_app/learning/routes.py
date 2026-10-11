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

from lyo_app.learning.schemas import (
    CourseCreate, CourseRead, CourseUpdate, CourseListResponse,
    LessonCreate, LessonRead, LessonUpdate,
    CourseEnrollmentCreate, CourseEnrollmentRead,
    LessonCompletionCreate, LessonCompletionRead,
    UserProgressResponse, ProofRead
)
from lyo_app.learning.service import LearningService
from lyo_app.learning.proofs import ProofEngine
from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user, get_current_user_or_guest
from lyo_app.models.enhanced import User

logger = logging.getLogger(__name__)

router = APIRouter()
learning_service = LearningService()
proof_engine = ProofEngine()


# ── iOS-compatible flexible course creation ────────────────────────────────────

class _IosLesson(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[str] = None
    duration_minutes: Optional[int] = None
    content: Optional[str] = None

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


@router.post("/courses", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_course(
    course_data: _IosCourseCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Dict[str, Any]:
    """Persist the course and every supplied lesson in one database transaction.

    A failed commit must not return 201 or an invented local/UUID course ID.
    The authenticated principal, not the client's instructor_id, owns it.
    """
    from sqlalchemy.exc import SQLAlchemyError
    from lyo_app.learning.models import Course, Lesson

    topic = course_data.topic or course_data.subject or course_data.title or "Course"
    title = course_data.title or f"Introduction to {topic}"
    difficulty = (
        course_data.difficulty_level or course_data.difficulty or
        course_data.level or "beginner"
    ).lower()
    if difficulty not in {"beginner", "intermediate", "advanced"}:
        raise HTTPException(status_code=422, detail="Unsupported course difficulty")
    description = course_data.description or f"A structured course on {topic}"

    # Keep lessons in course order and save module boundaries alongside them.
    # UUIDs supplied by offline clients are not database identities.
    modules = []
    try:
        course = Course(
            title=title, description=description, topic=topic,
            difficulty_level=difficulty, instructor_id=current_user.id,
            status="draft", is_published=False,
            estimated_duration_hours=course_data.estimated_hours or 1,
        )
        db.add(course)
        await db.flush()
        order = 0
        for mod in course_data.modules or []:
            module = {
                "id": mod.id or str(uuid.uuid4()),
                "title": mod.title or "Module",
                "description": mod.description or "",
                "lessons": [],
            }
            for les in mod.lessons or []:
                order += 1
                lesson = Lesson(
                    title=les.title or "Lesson",
                    content=les.content or "",
                    content_type="text", course_id=course.id,
                    order_index=order,
                    duration_minutes=les.duration_minutes or 10,
                    is_published=False,
                )
                db.add(lesson)
                await db.flush()
                module["lessons"].append({
                    "id": str(lesson.id),
                    "title": lesson.title,
                    "duration": les.duration or f"{lesson.duration_minutes} min",
                    "duration_minutes": lesson.duration_minutes,
                    "content": lesson.content or "",
                })
            modules.append(module)
        course.generation_metadata = {"modules": modules}
        await db.commit()
        await db.refresh(course)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Course persistence failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Course was not saved. Please retry; no course was created.",
        ) from exc

    logger.info("Persisted course %s with %s lessons for user %s", course.id, order, current_user.id)
    return {
        "id": str(course.id), "title": course.title, "topic": topic,
        "description": description, "difficulty": difficulty,
        "difficulty_level": difficulty, "modules": modules or None,
        "instructor_id": str(current_user.id), "is_published": False,
        "created_at": course.created_at.isoformat(),
        "updated_at": course.updated_at.isoformat(),
        "learning_objectives": [
            f"Understand the fundamentals of {topic}",
            f"Apply {topic} concepts in practice",
        ],
        "estimated_hours": course.estimated_duration_hours,
        "lesson_count": order,
    }


@router.get("/courses", response_model=List[CourseRead])
async def get_published_courses(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Maximum number of records")
) -> List[CourseRead]:
    """
    Get published courses with pagination.
    
    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        
    Returns:
        List of published courses
    """
    courses = await learning_service.get_published_courses(db, skip=skip, limit=limit)
    return [CourseRead.model_validate(course) for course in courses]


@router.get("/courses/mine", response_model=List[CourseRead])
async def get_my_courses(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> List[CourseRead]:
    """Show a learner's saved drafts, including generated lessons."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from lyo_app.learning.models import Course

    result = await db.execute(
        select(Course)
        .where(Course.instructor_id == current_user.id)
        .options(selectinload(Course.lessons))
        .order_by(Course.created_at.desc())
        .limit(100)
    )
    return [
        CourseRead.model_validate(course).model_copy(
            update={"lesson_count": len(course.lessons)}
        )
        for course in result.scalars().all()
    ]


@router.get("/courses/{course_id}", response_model=CourseRead)
async def get_course(
    course_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_guest)],
) -> CourseRead:
    """
    Get course by ID.
    
    Args:
        course_id: Course ID to retrieve
        db: Database session
        
    Returns:
        Course data
        
    Raises:
        HTTPException: If course not found
    """
    course = await learning_service.get_course_by_id(db, course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found"
        )
    # Unpublished learner work must not be readable by guessing integer IDs.
    if not course.is_published and course.instructor_id != current_user.id:
        raise HTTPException(status_code=404, detail="Course not found")
    return CourseRead.model_validate(course).model_copy(
        update={
            "lesson_count": len(course.lessons),
            "modules": (course.generation_metadata or {}).get("modules"),
        }
    )


@router.post("/courses/{course_id}/publish", response_model=CourseRead)
async def publish_course(
    course_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CourseRead:
    """
    Publish a course (make it available for enrollment).
    
    Args:
        course_id: Course ID to publish
        db: Database session
        
    Returns:
        Updated course data
        
    Raises:
        HTTPException: If course not found
    """
    existing = await learning_service.get_course_by_id(db, course_id)
    if existing is None or existing.instructor_id != current_user.id:
        raise HTTPException(status_code=404, detail="Course not found")
    try:
        course = await learning_service.publish_course(db, course_id)
        return CourseRead.model_validate(course)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/instructors/{instructor_id}/courses", response_model=List[CourseRead])
async def get_instructor_courses(
    instructor_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_guest)],
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
    if current_user.id != instructor_id:
        courses = [course for course in courses if course.is_published]
    return [CourseRead.model_validate(course) for course in courses]


@router.post("/lessons", response_model=LessonRead, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    lesson_data: LessonCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
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
    course = await learning_service.get_course_by_id(db, lesson_data.course_id)
    if course is None or course.instructor_id != current_user.id:
        raise HTTPException(status_code=404, detail="Course not found")
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
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_guest)],
) -> List[LessonRead]:
    """
    Get all lessons for a course.
    
    Args:
        course_id: Course ID
        db: Database session
        
    Returns:
        List of lessons ordered by order_index
    """
    course = await learning_service.get_course_by_id(db, course_id)
    if course is None or (not course.is_published and course.instructor_id != current_user.id):
        raise HTTPException(status_code=404, detail="Course not found")
    lessons = await learning_service.get_lessons_by_course(db, course_id)
    return [LessonRead.model_validate(lesson) for lesson in lessons]


@router.post("/lessons/{lesson_id}/publish", response_model=LessonRead)
async def publish_lesson(
    lesson_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
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
    from sqlalchemy import select
    from lyo_app.learning.models import Lesson
    existing = (await db.execute(select(Lesson).where(Lesson.id == lesson_id))).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    course = await learning_service.get_course_by_id(db, existing.course_id)
    if course is None or course.instructor_id != current_user.id:
        raise HTTPException(status_code=404, detail="Lesson not found")
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
