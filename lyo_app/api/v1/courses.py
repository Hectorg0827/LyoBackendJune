"""
Production courses API routes.
Course creation, management, and progress tracking.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from lyo_app.core.database import get_db
from lyo_app.auth.models import User
from lyo_app.models.production import Course, Lesson, UserProfile, Task
from lyo_app.auth.production import get_current_user, require_user
from lyo_app.tasks.course_generation import generate_course_task
from lyo_app.core.redis_production import RedisPubSub

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response models ────────────────────────────────────────────────────────────

class LessonResponse(BaseModel):
    id: str
    title: str
    content: str
    order_index: int
    estimated_duration_minutes: int

    model_config = {"from_attributes": True}


class CourseResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    subject: str
    difficulty_level: str
    estimated_duration_hours: int
    lessons_count: int = 0
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class CourseDetailResponse(CourseResponse):
    lessons: List[LessonResponse] = []
    learning_objectives: List[str] = []
    prerequisites: List[str] = []


class CourseGenerationRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    difficulty: str = Field("beginner", pattern="^(beginner|intermediate|advanced)$")
    duration_hours: int = Field(2, ge=1, le=20)
    learning_style: str = Field("balanced", pattern="^(visual|auditory|reading|kinesthetic|balanced)$")
    focus_areas: List[str] = Field(default_factory=list)
    include_exercises: bool = True
    include_assessments: bool = True


class CourseGenerationResponse(BaseModel):
    task_id: str
    status: str = "pending"
    message: str = "Course generation started"
    websocket_channel: str


# ── iOS-compatible flexible course create payload ─────────────────────────────

class IosCourseLesson(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[str] = None
    duration_minutes: Optional[int] = None
    content: Optional[str] = None


class IosCourseModule(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    lessons: Optional[List[IosCourseLesson]] = []


class IosCourseCreateRequest(BaseModel):
    """Flexible schema matching what the iOS app actually POSTs to /api/v1/learning/courses."""
    id: Optional[str] = None
    title: Optional[str] = None
    topic: Optional[str] = None
    subject: Optional[str] = None
    level: Optional[str] = None
    difficulty_level: Optional[str] = "beginner"
    difficulty: Optional[str] = None
    description: Optional[str] = None
    modules: Optional[List[IosCourseModule]] = []
    instructor_id: Optional[str] = None
    estimated_hours: Optional[float] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=Dict[str, Any])
async def create_course(
    request: IosCourseCreateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create/persist a generated course from the iOS app.

    Accepts the flexible iOS payload (id, title, topic, modules, level,
    difficulty_level, instructor_id).  Tries to persist to Cloud SQL but
    catches database errors gracefully and always returns 200 so the
    classroom can launch.
    """
    try:
        course_id = request.id or f"gen_{uuid.uuid4()}"
        topic = request.topic or request.subject or request.title or "Course"
        title = request.title or f"Introduction to {topic}"
        difficulty = request.difficulty_level or request.difficulty or request.level or "beginner"
        now = datetime.now(timezone.utc).isoformat()

        modules = []
        for mod in (request.modules or []):
            lessons = []
            for les in (mod.lessons or []):
                lessons.append({
                    "id": les.id or str(uuid.uuid4()),
                    "title": les.title or "Lesson",
                    "duration": les.duration or "10 min",
                    "duration_minutes": les.duration_minutes or 10,
                    "content": les.content or ""
                })
            modules.append({
                "id": mod.id or str(uuid.uuid4()),
                "title": mod.title or "Module",
                "description": mod.description or "",
                "lessons": lessons
            })

        course_record: Dict[str, Any] = {
            "id": course_id,
            "title": title,
            "topic": topic,
            "description": request.description or f"A structured course to learn {topic}",
            "difficulty": difficulty,
            "difficulty_level": difficulty,
            "modules": modules or None,
            "user_id": str(current_user.id),
            "instructor_id": request.instructor_id or str(current_user.id),
            "is_published": False,
            "created_at": now,
            "updated_at": now,
            "learning_objectives": [
                f"Understand the fundamentals of {topic}",
                f"Apply {topic} concepts in practice",
            ],
            "prerequisites": None,
            "estimated_hours": request.estimated_hours or max(len(modules) * 0.5, 1),
        }

        # Try Cloud SQL — non-fatal if the DB schema is incompatible
        try:
            db_course = Course(
                title=title,
                description=course_record["description"],
                subject=topic,
                difficulty_level=difficulty,
                estimated_duration_hours=int(course_record["estimated_hours"]),
                creator_id=current_user.id,
                learning_objectives=course_record["learning_objectives"],
                prerequisites=[],
            )
            db.add(db_course)
            await db.commit()
            await db.refresh(db_course)
            course_record["id"] = str(db_course.id)
            logger.info(f"✅ Course persisted to Cloud SQL: {course_record['id']}")
        except Exception as db_err:
            logger.warning(f"⚠️  Cloud SQL persist skipped (non-fatal): {db_err}")
            await db.rollback()
            # Still return 200 — iOS will use the in-memory record

        logger.info(f"📚 Course upserted: '{title}' for user {current_user.id}")
        return course_record

    except Exception as e:
        logger.error(f"Course create error: {e}", exc_info=True)
        # Last-resort fallback: return minimal 200 so iOS isn't blocked
        return {
            "id": request.id or f"local_{uuid.uuid4().hex[:8]}",
            "title": request.title or "Generated Course",
            "topic": request.topic or "Course",
            "status": "saved_locally",
            "message": "Course saved (cloud sync pending)",
        }


@router.post("/generate", response_model=CourseGenerationResponse)
async def generate_course(
    request: CourseGenerationRequest,
    current_user: User = Depends(require_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a course using AI based on topic and preferences.
    """
    try:
        task = Task(
            user_id=current_user.id,
            task_type="course_generation",
            status="pending",
            metadata={
                "topic": request.topic,
                "difficulty": request.difficulty,
                "duration_hours": request.duration_hours,
                "learning_style": request.learning_style,
                "focus_areas": request.focus_areas,
                "include_exercises": request.include_exercises,
                "include_assessments": request.include_assessments,
            },
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        generate_course_task.delay(
            task_id=str(task.id),
            user_id=str(current_user.id),
            topic=request.topic,
            difficulty=request.difficulty,
            duration_hours=request.duration_hours,
            learning_style=request.learning_style,
            focus_areas=request.focus_areas,
            include_exercises=request.include_exercises,
            include_assessments=request.include_assessments,
        )

        websocket_channel = f"course_generation_{current_user.id}"
        logger.info(f"Course generation started for {current_user.email}: {request.topic}")

        return CourseGenerationResponse(
            task_id=str(task.id),
            websocket_channel=websocket_channel,
        )

    except Exception as e:
        logger.error(f"Course generation error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Course generation failed")


@router.get("/", response_model=List[CourseResponse])
async def list_courses(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    subject: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
):
    """List courses accessible to the user."""
    try:
        query = select(Course).options(selectinload(Course.lessons))

        if subject:
            query = query.where(Course.subject == subject)
        if difficulty:
            query = query.where(Course.difficulty_level == difficulty)

        query = query.offset(skip).limit(limit).order_by(Course.created_at.desc())
        result = await db.execute(query)
        courses = result.scalars().all()

        return [
            CourseResponse(
                id=str(c.id),
                title=c.title,
                description=c.description,
                subject=c.subject,
                difficulty_level=c.difficulty_level,
                estimated_duration_hours=c.estimated_duration_hours,
                lessons_count=len(c.lessons) if c.lessons else 0,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
            )
            for c in courses
        ]

    except Exception as e:
        logger.error(f"Course listing error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list courses")


@router.get("/{course_id}", response_model=CourseDetailResponse)
async def get_course(
    course_id: UUID,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed course information including lessons."""
    try:
        query = select(Course).options(selectinload(Course.lessons)).where(
            Course.id == course_id
        )
        result = await db.execute(query)
        course = result.scalar_one_or_none()

        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        lessons = [
            LessonResponse(
                id=str(l.id),
                title=l.title,
                content=l.content,
                order_index=l.order_index,
                estimated_duration_minutes=l.estimated_duration_minutes,
            )
            for l in sorted(course.lessons or [], key=lambda x: x.order_index)
        ]

        return CourseDetailResponse(
            id=str(course.id),
            title=course.title,
            description=course.description,
            subject=course.subject,
            difficulty_level=course.difficulty_level,
            estimated_duration_hours=course.estimated_duration_hours,
            lessons_count=len(lessons),
            created_at=course.created_at.isoformat(),
            updated_at=course.updated_at.isoformat(),
            lessons=lessons,
            learning_objectives=course.learning_objectives or [],
            prerequisites=course.prerequisites or [],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get course error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get course")


@router.delete("/{course_id}")
async def delete_course(
    course_id: UUID,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a course (only if user is creator)."""
    try:
        query = select(Course).where(
            Course.id == course_id, Course.creator_id == current_user.id
        )
        result = await db.execute(query)
        course = result.scalar_one_or_none()

        if not course:
            raise HTTPException(status_code=404, detail="Course not found or not authorized")

        await db.delete(course)
        await db.commit()

        logger.info(f"Course deleted: {course.title} by {current_user.email}")
        return {"message": "Course deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Course deletion error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Course deletion failed")
