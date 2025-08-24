"""Learning API endpoints for course generation and management."""

import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from lyo_app.core.database import get_db
from lyo_app.core.problems import (
    ValidationProblem, ResourceNotFoundProblem, ConflictProblem
)
from lyo_app.models.enhanced import User, Course, Task, TaskState
from lyo_app.schemas import (
    CourseGenerationRequest, CourseGenerationResponse, CourseResponse,
    PaginationParams
)
from lyo_app.auth.jwt_auth import require_active_user
from lyo_app.workers.course_generation import generate_course

router = APIRouter(prefix="/courses", tags=["learning"])


@router.post(":generate", response_model=CourseGenerationResponse, status_code=202)
async def generate_course_async(
    request: Request,
    generation_request: CourseGenerationRequest,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db)
):
    """
    Generate a new course asynchronously using AI.
    
    This endpoint starts an async course generation task and returns immediately
    with a task_id. Client should use WebSocket or polling to track progress.
    
    Headers:
        Idempotency-Key: UUID to prevent duplicate course generation
        Prefer: respond-async (optional, for documentation)
    
    Returns:
        202 Accepted with task_id and provisional_course_id
        
    Raises:
        ValidationProblem: Invalid generation parameters
        ConflictProblem: Duplicate idempotency key
    """
    # Extract idempotency key
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        # Generate one if not provided (less ideal)
        idempotency_key = str(uuid.uuid4())
    
    try:
        uuid.UUID(idempotency_key)  # Validate UUID format
    except ValueError:
        raise ValidationProblem("Idempotency-Key must be a valid UUID")
    
    # Check for existing task with same idempotency key
    existing_task = db.query(Task).filter(
        and_(
            Task.idempotency_key == idempotency_key,
            Task.user_id == current_user.id
        )
    ).first()
    
    if existing_task:
        # Return existing task info - this is idempotent behavior
        return CourseGenerationResponse(
            task_id=str(existing_task.id),
            provisional_course_id=str(existing_task.provisional_course_id) if existing_task.provisional_course_id else None,
            estimated_completion_minutes=15
        )
    
    # Create provisional course record
    provisional_course = Course(
        id=uuid.uuid4(),
        owner_user_id=current_user.id,
        title=f"Generating: {generation_request.topic}",
        topic=generation_request.topic,
        summary="Course is being generated...",
        status="GENERATING",
        interests=generation_request.interests,
        difficulty_level=generation_request.difficulty_level,
        target_duration_hours=generation_request.target_duration_hours
    )
    
    db.add(provisional_course)
    db.flush()  # Get provisional_course.id
    
    # Create task record
    task = Task(
        id=uuid.uuid4(),
        user_id=current_user.id,
        idempotency_key=idempotency_key,
        task_type="course_generation",
        task_params={
            "topic": generation_request.topic,
            "interests": generation_request.interests,
            "difficulty_level": generation_request.difficulty_level,
            "target_duration_hours": generation_request.target_duration_hours,
            "locale": generation_request.locale
        },
        state=TaskState.QUEUED,
        provisional_course_id=provisional_course.id
    )
    
    db.add(task)
    db.commit()
    
    # Enqueue Celery task
    generate_course.delay(
        task_id=str(task.id),
        user_id=str(current_user.id),
        topic=generation_request.topic,
        interests=generation_request.interests,
        difficulty_level=generation_request.difficulty_level,
        target_duration_hours=generation_request.target_duration_hours,
        locale=generation_request.locale
    )
    
    return CourseGenerationResponse(
        task_id=str(task.id),
        provisional_course_id=str(provisional_course.id),
        estimated_completion_minutes=15
    )


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: str,
    current_user: Optional[User] = Depends(require_active_user),
    db: Session = Depends(get_db)
):
    """
    Get course details with normalized content structure.
    
    Returns complete course information including lessons and content items
    in the unified schema for one-screen UI consumption.
    
    Args:
        course_id: UUID of the course
        
    Returns:
        CourseResponse with complete course data
        
    Raises:
        ResourceNotFoundProblem: Course not found
    """
    try:
        course_uuid = uuid.UUID(course_id)
    except ValueError:
        raise ValidationProblem("Invalid course ID format")
    
    course = db.query(Course).filter(Course.id == course_uuid).first()
    
    if not course:
        raise ResourceNotFoundProblem("course", course_id)
    
    # Check access permissions (for now, all courses are public)
    # TODO: Implement proper access control based on course visibility settings
    
    return CourseResponse.from_orm(course)


@router.get("", response_model=List[CourseResponse])
async def list_courses(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=50, description="Number of courses to return"),
    offset: int = Query(0, ge=0, description="Number of courses to skip"),
    own_only: bool = Query(False, description="Show only user's own courses")
):
    """
    List courses with filtering and pagination.
    
    Returns:
        List of CourseResponse objects
    """
    query = db.query(Course)
    
    # Apply filters
    if own_only:
        query = query.filter(Course.owner_user_id == current_user.id)
    
    if topic:
        query = query.filter(Course.topic.ilike(f"%{topic}%"))
    
    if status:
        query = query.filter(Course.status == status)
    
    # Order by creation date (newest first)
    query = query.order_by(desc(Course.created_at))
    
    # Apply pagination
    courses = query.offset(offset).limit(limit).all()
    
    return [CourseResponse.from_orm(course) for course in courses]


@router.delete("/{course_id}", status_code=204)
async def delete_course(
    course_id: str,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a course (only by owner).
    
    Args:
        course_id: UUID of the course to delete
        
    Raises:
        ResourceNotFoundProblem: Course not found
        AuthorizationProblem: Not course owner
    """
    try:
        course_uuid = uuid.UUID(course_id)
    except ValueError:
        raise ValidationProblem("Invalid course ID format")
    
    course = db.query(Course).filter(Course.id == course_uuid).first()
    
    if not course:
        raise ResourceNotFoundProblem("course", course_id)
    
    if course.owner_user_id != current_user.id:
        from lyo_app.core.problems import AuthorizationProblem
        raise AuthorizationProblem("You can only delete your own courses")
    
    # Soft delete by setting status (or hard delete based on requirements)
    course.status = "DELETED"
    course.updated_at = datetime.utcnow()
    
    db.commit()
    
    return None


@router.post("/{course_id}/favorite", status_code=204)
async def favorite_course(
    course_id: str,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db)
):
    """
    Add course to user's favorites.
    
    TODO: Implement favorites/bookmarks table and logic
    """
    try:
        course_uuid = uuid.UUID(course_id)
    except ValueError:
        raise ValidationProblem("Invalid course ID format")
    
    course = db.query(Course).filter(Course.id == course_uuid).first()
    if not course:
        raise ResourceNotFoundProblem("course", course_id)
    
    # TODO: Implement favorites table
    # For now, just return success
    
    return None


@router.delete("/{course_id}/favorite", status_code=204)
async def unfavorite_course(
    course_id: str,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db)
):
    """
    Remove course from user's favorites.
    """
    # TODO: Implement unfavorite logic
    return None


@router.post("/{course_id}/share", status_code=204)
async def share_course(
    course_id: str,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db)
):
    """
    Share course to community feed.
    
    TODO: Create feed item for course sharing
    """
    try:
        course_uuid = uuid.UUID(course_id)
    except ValueError:
        raise ValidationProblem("Invalid course ID format")
    
    course = db.query(Course).filter(Course.id == course_uuid).first()
    if not course:
        raise ResourceNotFoundProblem("course", course_id)
    
    # TODO: Create feed item
    # from lyo_app.models.enhanced import FeedItem
    # feed_item = FeedItem(
    #     user_id=current_user.id,
    #     item_type="course_shared",
    #     title=f"{current_user.full_name} shared a course",
    #     course_id=course.id,
    #     metadata={"course_title": course.title}
    # )
    # db.add(feed_item)
    # db.commit()
    
    return None


@router.get("/{course_id}/progress")
async def get_course_progress(
    course_id: str,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db)
):
    """
    Get user's progress through a course.
    
    TODO: Implement progress tracking tables and logic
    
    Returns:
        Progress information including completed lessons, time spent, etc.
    """
    try:
        course_uuid = uuid.UUID(course_id)
    except ValueError:
        raise ValidationProblem("Invalid course ID format")
    
    course = db.query(Course).filter(Course.id == course_uuid).first()
    if not course:
        raise ResourceNotFoundProblem("course", course_id)
    
    # TODO: Implement progress tracking
    return {
        "course_id": course_id,
        "user_id": str(current_user.id),
        "progress_percent": 0,
        "completed_lessons": [],
        "current_lesson_id": None,
        "time_spent_minutes": 0,
        "started_at": None,
        "last_accessed_at": None
    }
