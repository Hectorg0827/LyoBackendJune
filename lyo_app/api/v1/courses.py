"""
Production courses API routes.
Course creation, management, and progress tracking.
"""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from lyo_app.core.database import get_db
from lyo_app.models.production import User, Course, Lesson, UserProfile, Task
from lyo_app.auth.production import get_current_user, require_user
from lyo_app.tasks.course_generation import generate_course_task
from lyo_app.core.redis_production import RedisPubSub

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models
class CourseCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(None, max_length=1000)
    subject: str = Field(..., min_length=1, max_length=100)
    difficulty_level: str = Field("beginner", pattern="^(beginner|intermediate|advanced)$")
    estimated_duration_hours: int = Field(1, ge=1, le=100)
    learning_objectives: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)


class LessonResponse(BaseModel):
    id: str
    title: str
    content: str
    order_index: int
    estimated_duration_minutes: int
    
    model_config = {
        "from_attributes": True
    }


class CourseResponse(BaseModel):
    id: str
    title: str
    description: str = None
    subject: str
    difficulty_level: str
    estimated_duration_hours: int
    lessons_count: int = 0
    created_at: str
    updated_at: str
    
    model_config = {
        "from_attributes": True
    }


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


@router.post("/", response_model=CourseResponse)
async def create_course(
    request: CourseCreateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new course manually.
    """
    try:
        course = Course(
            title=request.title,
            description=request.description,
            subject=request.subject,
            difficulty_level=request.difficulty_level,
            estimated_duration_hours=request.estimated_duration_hours,
            creator_id=current_user.id,
            learning_objectives=request.learning_objectives,
            prerequisites=request.prerequisites
        )
        
        db.add(course)
        await db.commit()
        await db.refresh(course)
        
        logger.info(f"Course created: {course.title} by {current_user.email}")
        
        return CourseResponse(
            id=str(course.id),
            title=course.title,
            description=course.description,
            subject=course.subject,
            difficulty_level=course.difficulty_level,
            estimated_duration_hours=course.estimated_duration_hours,
            created_at=course.created_at.isoformat(),
            updated_at=course.updated_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Course creation error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Course creation failed")


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
        # Create a task record
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
                "include_assessments": request.include_assessments
            }
        )
        
        db.add(task)
        await db.commit()
        await db.refresh(task)
        
        # Start background generation
        generate_course_task.delay(
            task_id=str(task.id),
            user_id=str(current_user.id),
            topic=request.topic,
            difficulty=request.difficulty,
            duration_hours=request.duration_hours,
            learning_style=request.learning_style,
            focus_areas=request.focus_areas,
            include_exercises=request.include_exercises,
            include_assessments=request.include_assessments
        )
        
        websocket_channel = f"course_generation_{current_user.id}"
        
        logger.info(f"Course generation started for {current_user.email}: {request.topic}")
        
        return CourseGenerationResponse(
            task_id=str(task.id),
            websocket_channel=websocket_channel
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
    difficulty: Optional[str] = Query(None)
):
    """
    List courses accessible to the user.
    """
    try:
        query = select(Course).options(
            selectinload(Course.lessons)
        )
        
        # Filter by subject if provided
        if subject:
            query = query.where(Course.subject == subject)
            
        # Filter by difficulty if provided  
        if difficulty:
            query = query.where(Course.difficulty_level == difficulty)
            
        query = query.offset(skip).limit(limit).order_by(Course.created_at.desc())
        
        result = await db.execute(query)
        courses = result.scalars().all()
        
        course_responses = []
        for course in courses:
            course_responses.append(CourseResponse(
                id=str(course.id),
                title=course.title,
                description=course.description,
                subject=course.subject,
                difficulty_level=course.difficulty_level,
                estimated_duration_hours=course.estimated_duration_hours,
                lessons_count=len(course.lessons) if course.lessons else 0,
                created_at=course.created_at.isoformat(),
                updated_at=course.updated_at.isoformat()
            ))
        
        return course_responses
        
    except Exception as e:
        logger.error(f"Course listing error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list courses")


@router.get("/{course_id}", response_model=CourseDetailResponse)
async def get_course(
    course_id: UUID,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed course information including lessons.
    """
    try:
        query = select(Course).options(
            selectinload(Course.lessons)
        ).where(Course.id == course_id)
        
        result = await db.execute(query)
        course = result.scalar_one_or_none()
        
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        
        lessons = []
        if course.lessons:
            for lesson in sorted(course.lessons, key=lambda l: l.order_index):
                lessons.append(LessonResponse(
                    id=str(lesson.id),
                    title=lesson.title,
                    content=lesson.content,
                    order_index=lesson.order_index,
                    estimated_duration_minutes=lesson.estimated_duration_minutes
                ))
        
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
            prerequisites=course.prerequisites or []
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
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a course (only if user is creator).
    """
    try:
        query = select(Course).where(
            Course.id == course_id,
            Course.creator_id == current_user.id
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
