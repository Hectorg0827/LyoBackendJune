"""Course generation task using Celery for async processing."""

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from celery import current_task
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from lyo_app.workers.celery_app import celery_app
from lyo_app.core.settings import settings
from lyo_app.models.enhanced import Task, Course, User, ContentItem, Lesson, TaskState
from lyo_app.models.loading import model_manager
from lyo_app.services.content_curator import ContentCurator
from lyo_app.services.websocket_manager import websocket_manager
from lyo_app.services.push_notifications import push_service

import logging

logger = logging.getLogger(__name__)

# Create database session factory for workers
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def publish_progress(task_id: str, state: str, progress: int, message: str, result_id: Optional[str] = None):
    """Publish task progress to WebSocket and update database."""
    
    # Update database
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.state = TaskState(state)
            task.progress_pct = progress
            task.message = message
            task.updated_at = datetime.utcnow()
            
            if state == "RUNNING" and not task.started_at:
                task.started_at = datetime.utcnow()
            elif state in ["DONE", "ERROR"]:
                task.completed_at = datetime.utcnow()
                if result_id:
                    task.result_course_id = result_id
            
            db.commit()
        
        # Publish WebSocket event
        websocket_manager.publish_task_progress(task_id, {
            "task_id": task_id,
            "state": state,
            "progress_pct": progress,
            "message": message,
            "result_id": result_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to publish progress: {e}")
        db.rollback()
    finally:
        db.close()


@celery_app.task(bind=True, name="lyo_app.workers.course_generation.generate_course")
def generate_course(
    self,
    task_id: str,
    user_id: str,
    topic: str,
    interests: List[str],
    difficulty_level: str = "beginner",
    target_duration_hours: Optional[float] = None,
    locale: str = "en"
) -> Dict[str, Any]:
    """
    Generate a complete course using Gemma 3 and content curation.
    
    This is the main async task that orchestrates course generation:
    1. Ensure model is available
    2. Research and curate content sources
    3. Generate course structure with AI
    4. Normalize and store content items
    5. Send push notification when complete
    
    Args:
        task_id: UUID of the task for progress tracking
        user_id: UUID of the user requesting the course
        topic: Main topic/subject for the course
        interests: List of related interests/keywords
        difficulty_level: "beginner", "intermediate", or "advanced"
        target_duration_hours: Desired course duration
        locale: Language/locale code
        
    Returns:
        Dict with course_id and generation metadata
    """
    db = SessionLocal()
    
    try:
        # Initialize progress
        publish_progress(task_id, "RUNNING", 5, "Preparing AI model...")
        
        # 1. Ensure Gemma 3 model is available
        try:
            model_info = model_manager.ensure_model()
            logger.info(f"Model available: {model_info.name}")
        except Exception as e:
            publish_progress(task_id, "ERROR", 0, f"Model loading failed: {str(e)}")
            raise
        
        publish_progress(task_id, "RUNNING", 15, "Researching content sources...")
        
        # 2. Initialize content curator
        curator = ContentCurator(
            model_manager=model_manager,
            youtube_api_key=settings.YOUTUBE_API_KEY,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        # 3. Research and curate content
        def progress_callback(percent: int, message: str):
            # Scale progress from 15-80% for curation phase
            scaled_progress = 15 + int((percent / 100) * 65)
            publish_progress(task_id, "RUNNING", scaled_progress, message)
        
        curation_result = curator.curate_course(
            topic=topic,
            interests=interests,
            difficulty_level=difficulty_level,
            target_duration_hours=target_duration_hours or 8.0,
            locale=locale,
            progress_callback=progress_callback
        )
        
        publish_progress(task_id, "RUNNING", 85, "Organizing course structure...")
        
        # 4. Create course in database
        course = Course(
            id=uuid.uuid4(),
            owner_user_id=user_id,
            title=curation_result["title"],
            topic=topic,
            summary=curation_result.get("summary"),
            description=curation_result.get("description"),
            interests=interests,
            difficulty_level=difficulty_level,
            target_duration_hours=target_duration_hours,
            tags=curation_result.get("tags", []),
            thumbnail_url=curation_result.get("thumbnail_url"),
            estimated_duration_hours=curation_result.get("estimated_duration_hours"),
            status="READY",
            generation_metadata={
                "model_name": model_info.name,
                "model_version": model_info.version,
                "generated_at": datetime.utcnow().isoformat(),
                "generation_time_seconds": 0,  # Will be updated
                "content_sources": curation_result.get("sources_summary", {}),
                "ai_parameters": {
                    "topic": topic,
                    "interests": interests,
                    "difficulty_level": difficulty_level,
                    "locale": locale
                }
            }
        )
        
        db.add(course)
        db.commit()
        
        publish_progress(task_id, "RUNNING", 90, "Creating lessons and content...")
        
        # 5. Create lessons
        for i, lesson_data in enumerate(curation_result.get("lessons", [])):
            lesson = Lesson(
                id=uuid.uuid4(),
                course_id=course.id,
                title=lesson_data["title"],
                summary=lesson_data.get("summary"),
                order=i + 1,
                objectives=lesson_data.get("objectives", []),
                estimated_duration_minutes=lesson_data.get("duration_minutes")
            )
            db.add(lesson)
        
        db.commit()
        
        # 6. Create content items
        for item_data in curation_result.get("content_items", []):
            content_item = ContentItem(
                id=uuid.uuid4(),
                course_id=course.id,
                lesson_id=item_data.get("lesson_id"),  # May be None for course-level content
                type=item_data["type"],
                title=item_data["title"],
                source=item_data.get("source"),
                source_url=item_data.get("source_url"),
                external_id=item_data.get("external_id"),
                thumbnail_url=item_data.get("thumbnail_url"),
                duration_sec=item_data.get("duration_sec"),
                pages=item_data.get("pages"),
                word_count=item_data.get("word_count"),
                summary=item_data.get("summary"),
                attribution=item_data.get("attribution"),
                tags=item_data.get("tags", []),
                difficulty_level=item_data.get("difficulty_level", difficulty_level),
                language=locale,
                quality_score=item_data.get("quality_score"),
                is_free=item_data.get("is_free", True),
                requires_subscription=item_data.get("requires_subscription", False),
                published_at=item_data.get("published_at")
            )
            db.add(content_item)
        
        db.commit()
        
        publish_progress(task_id, "RUNNING", 95, "Finalizing course...")
        
        # 7. Update generation metadata with final stats
        generation_end_time = datetime.utcnow()
        task_record = db.query(Task).filter(Task.id == task_id).first()
        generation_time = (generation_end_time - task_record.started_at).total_seconds()
        
        course.generation_metadata["generation_time_seconds"] = generation_time
        course.generation_metadata["content_items_count"] = len(curation_result.get("content_items", []))
        course.generation_metadata["lessons_count"] = len(curation_result.get("lessons", []))
        
        db.commit()
        
        # 8. Mark task as complete
        publish_progress(task_id, "DONE", 100, "Course generation completed!", str(course.id))
        
        # 9. Send push notification
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                push_service.send_course_completion_notification(
                    user=user,
                    course=course,
                    task_id=task_id
                )
        except Exception as e:
            logger.warning(f"Failed to send push notification: {e}")
        
        logger.info(f"Course generation completed: {course.id} for user {user_id}")
        
        return {
            "course_id": str(course.id),
            "title": course.title,
            "lessons_count": len(curation_result.get("lessons", [])),
            "content_items_count": len(curation_result.get("content_items", [])),
            "generation_time_seconds": generation_time
        }
        
    except Exception as e:
        logger.error(f"Course generation failed: {e}", exc_info=True)
        
        # Update task with error
        publish_progress(task_id, "ERROR", 0, f"Course generation failed: {str(e)}")
        
        # Store detailed error information
        task_record = db.query(Task).filter(Task.id == task_id).first()
        if task_record:
            task_record.error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "failed_at": datetime.utcnow().isoformat(),
                "task_params": {
                    "topic": topic,
                    "interests": interests,
                    "difficulty_level": difficulty_level
                }
            }
            db.commit()
        
        raise
    
    finally:
        db.close()


@celery_app.task(name="lyo_app.workers.course_generation.regenerate_course_section")
def regenerate_course_section(
    task_id: str,
    course_id: str,
    section_type: str,  # "lessons", "content_items", "summary"
    user_preferences: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Regenerate a specific section of an existing course.
    
    This allows users to refine parts of generated courses without
    regenerating the entire course.
    """
    db = SessionLocal()
    
    try:
        publish_progress(task_id, "RUNNING", 10, f"Regenerating {section_type}...")
        
        course = db.query(Course).filter(Course.id == course_id).first()
        if not course:
            raise ValueError(f"Course {course_id} not found")
        
        # Ensure model is available
        model_info = model_manager.ensure_model()
        
        # Initialize curator
        curator = ContentCurator(model_manager=model_manager)
        
        def progress_callback(percent: int, message: str):
            scaled_progress = 10 + int((percent / 100) * 80)
            publish_progress(task_id, "RUNNING", scaled_progress, message)
        
        # Regenerate based on section type
        if section_type == "lessons":
            new_lessons = curator.regenerate_lessons(
                course=course,
                preferences=user_preferences,
                progress_callback=progress_callback
            )
            
            # Replace existing lessons
            db.query(Lesson).filter(Lesson.course_id == course_id).delete()
            
            for lesson_data in new_lessons:
                lesson = Lesson(
                    id=uuid.uuid4(),
                    course_id=course.id,
                    title=lesson_data["title"],
                    summary=lesson_data.get("summary"),
                    order=lesson_data["order"],
                    objectives=lesson_data.get("objectives", [])
                )
                db.add(lesson)
        
        elif section_type == "content_items":
            new_items = curator.regenerate_content_items(
                course=course,
                preferences=user_preferences,
                progress_callback=progress_callback
            )
            
            # Update existing content items
            for item_data in new_items:
                if "id" in item_data:  # Update existing
                    item = db.query(ContentItem).filter(ContentItem.id == item_data["id"]).first()
                    if item:
                        item.title = item_data["title"]
                        item.summary = item_data.get("summary")
                        # Update other fields as needed
                else:  # Create new
                    item = ContentItem(
                        id=uuid.uuid4(),
                        course_id=course.id,
                        **item_data
                    )
                    db.add(item)
        
        db.commit()
        
        publish_progress(task_id, "DONE", 100, f"{section_type.title()} regenerated successfully!")
        
        return {
            "course_id": course_id,
            "section_type": section_type,
            "regenerated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Section regeneration failed: {e}")
        publish_progress(task_id, "ERROR", 0, f"Regeneration failed: {str(e)}")
        raise
    
    finally:
        db.close()
