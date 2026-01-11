"""
Course generation task implementation.
Handles AI-powered course creation using local Gemma model.
"""

import uuid
import logging
import asyncio
import json
from typing import Dict, Any, Callable, List, Optional
from datetime import datetime, timedelta

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from lyo_app.core.celery_app import celery_app
from lyo_app.core.redis_production import publish_task_progress
from lyo_app.models.production import Task, Course, Lesson, CourseItem, TaskState, CourseStatus
from lyo_app.models.loading import model_manager, generate_course_content
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

# Database setup for Celery tasks (sync connection)
DATABASE_URL = getattr(settings, "database_url", "sqlite+aiosqlite:///./lyo_app.db")
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sync_engine = create_engine(SYNC_DATABASE_URL)
SessionLocal = sessionmaker(bind=sync_engine)


def get_sync_db() -> Session:
    """Get synchronous database session for Celery tasks."""
    return SessionLocal()


class CourseGenerator:
    """AI-powered course content generator using local Gemma model."""
    
    def __init__(self):
        self.model_ready = True
    
    def ensure_model(self) -> bool:
        """Compatibility shim for Gemini."""
        return True
    
    async def generate_course_outline(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generate course outline using Gemini."""
        topic = payload.get("topic", "General Learning")
        interests = payload.get("interests", [])
        level = payload.get("level", "beginner")
        locale = payload.get("locale", "en")
        
        try:
            # Create detailed prompt for course generation
            prompt = self._build_course_prompt(topic, interests, level, locale)
            
            # Generate course outline using Gemini
            logger.info(f"Generating course outline for topic: {topic}")
            generated_content = await generate_course_content(
                prompt=prompt,
                max_new_tokens=1024,
                temperature=0.7,
                top_p=0.9
            )
            
            # Parse the generated content into structured format
            outline = self._parse_generated_outline(generated_content, topic, level)
            
            logger.info(f"✅ Generated course outline with {len(outline.get('lessons', []))} lessons")
            return outline
            
        except Exception as e:
            logger.error(f"Course generation failed: {e}")
            logger.warning("Falling back to template-based generation")
            return self._fallback_course_outline(topic, level)
    
    def _build_course_prompt(self, topic: str, interests: List[str], level: str, locale: str) -> str:
        """Build a comprehensive prompt for course generation."""
        interests_text = ", ".join(interests) if interests else "general learning"
        
        prompt = f"""Create a comprehensive learning course outline for the topic: {topic}

Course Requirements:
- Level: {level}
- Student interests: {interests_text}
- Language: {locale}

Please provide a detailed course outline in the following JSON format:
{{
    "title": "Course title",
    "description": "Brief course description",
    "estimated_duration": "Duration in minutes",
    "difficulty": "{level}",
    "prerequisites": ["List of prerequisites"],
    "learning_objectives": ["List of learning objectives"],
    "lessons": [
        {{
            "title": "Lesson title",
            "description": "Lesson description",
            "objectives": ["Lesson objectives"],
            "content_type": "text/video/interactive",
            "estimated_duration": "Duration in minutes",
            "key_concepts": ["Key concepts covered"],
            "practice_activities": ["Practice activities"]
        }}
    ],
    "final_project": "Description of final project or capstone",
    "assessment_methods": ["Assessment methods"],
    "resources": ["Additional resources"]
}}

Make sure the course is:
1. Appropriate for {level} level learners
2. Engaging and practical
3. Structured with clear progression
4. Includes hands-on activities
5. Relevant to the interests: {interests_text}

Generate the course outline:"""
        
        return prompt
    
    def _parse_generated_outline(self, generated_content: str, topic: str, level: str) -> Dict[str, Any]:
        """Parse AI-generated content into structured course outline."""
        try:
            # Try to extract JSON from the generated content
            start_idx = generated_content.find('{')
            end_idx = generated_content.rfind('}') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_content = generated_content[start_idx:end_idx]
                parsed_outline = json.loads(json_content)
                
                # Validate and enhance the parsed outline
                return self._validate_and_enhance_outline(parsed_outline, topic, level)
            else:
                # If no valid JSON found, parse text manually
                return self._parse_text_outline(generated_content, topic, level)
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from generated content: {e}")
            return self._parse_text_outline(generated_content, topic, level)
        except Exception as e:
            logger.error(f"Error parsing generated outline: {e}")
            return self._fallback_course_outline(topic, level)
    
    def _validate_and_enhance_outline(self, outline: Dict[str, Any], topic: str, level: str) -> Dict[str, Any]:
        """Validate and enhance the parsed outline."""
        # Ensure required fields are present
        outline.setdefault("title", f"Master {topic.title()}")
        outline.setdefault("description", f"A comprehensive course on {topic}")
        outline.setdefault("estimated_duration", 120)
        outline.setdefault("difficulty", level)
        outline.setdefault("lessons", [])
        
        # Ensure lessons have required structure
        for lesson in outline["lessons"]:
            lesson.setdefault("estimated_duration", 15)
            lesson.setdefault("objectives", [])
            lesson.setdefault("content_type", "text")
        
        # Add metadata
        outline["generated_at"] = datetime.utcnow().isoformat()
        outline["generator"] = "gemma-local"
        outline["topic"] = topic
        outline["level"] = level
        
        return outline
    
    def _parse_text_outline(self, content: str, topic: str, level: str) -> Dict[str, Any]:
        """Parse text content when JSON parsing fails."""
        logger.info("Parsing text-based course outline")
        
        # Simple text parsing logic
        lines = content.split('\n')
        lessons = []
        
        current_lesson = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Look for lesson indicators
            if any(indicator in line.lower() for indicator in ['lesson', 'chapter', 'module', 'unit']):
                if current_lesson:
                    lessons.append(current_lesson)
                
                current_lesson = {
                    "title": line,
                    "description": f"Learn about {line.lower()}",
                    "objectives": [],
                    "estimated_duration": 20,
                    "content_type": "text"
                }
            elif current_lesson and line.startswith('-'):
                # Add as objective
                current_lesson["objectives"].append(line[1:].strip())
        
        # Add the last lesson
        if current_lesson:
            lessons.append(current_lesson)
        
        return {
            "title": f"AI Generated: {topic.title()}",
            "description": f"A comprehensive course on {topic} generated using AI",
            "estimated_duration": len(lessons) * 20,
            "difficulty": level,
            "lessons": lessons,
            "generated_at": datetime.utcnow().isoformat(),
            "generator": "gemma-local-text",
            "topic": topic,
            "level": level
        }
    
    def _fallback_course_outline(self, topic: str, level: str) -> Dict[str, Any]:
        """Fallback course generation when AI is unavailable."""
        logger.info(f"Using fallback course generation for: {topic}")
        
        return {
            "title": f"Learn {topic.title()}",
            "description": f"A structured course on {topic} designed for {level} learners.",
            "estimated_duration": 90,
            "difficulty": level,
            "prerequisites": [],
            "learning_objectives": [
                f"Understand the fundamentals of {topic}",
                f"Apply {topic} concepts in practice",
                f"Build confidence with {topic}"
            ],
            "lessons": [
                {
                    "title": f"Introduction to {topic.title()}",
                    "description": f"Get started with {topic}",
                    "objectives": [
                        f"Identify key principles in {topic}",
                        f"Apply foundational knowledge"
                    ],
                    "items": [
                        {
                            "type": "video",
                            "title": f"What is {topic.title()}?",
                            "content": f"An introduction to {topic} and its applications.",
                            "source": "youtube",
                            "source_url": f"https://youtube.com/watch?v=example_{topic}",
                            "duration": 300
                        },
                        {
                            "type": "text",
                            "title": "Core Concepts",
                            "content": f"Key concepts you need to understand in {topic}:\n\n1. Fundamental principles\n2. Best practices\n3. Common applications",
                            "source": "generated",
                            "source_url": None,
                            "duration": 600
                        },
                        {
                            "type": "quiz",
                            "title": "Knowledge Check",
                            "content": f"Test your understanding of {topic} basics",
                            "source": "generated",
                            "source_url": None,
                            "duration": 300
                        }
                    ]
                },
                {
                    "title": f"Intermediate {topic.title()}",
                    "description": f"Dive deeper into {topic} concepts",
                    "objectives": [
                        f"Apply intermediate {topic} techniques",
                        f"Solve complex problems in {topic}",
                        f"Understand advanced patterns"
                    ],
                    "items": [
                        {
                            "type": "video",
                            "title": f"Advanced {topic.title()} Techniques",
                            "content": f"Learn advanced techniques in {topic}",
                            "source": "youtube",
                            "source_url": f"https://youtube.com/watch?v=advanced_{topic}",
                            "duration": 420
                        },
                        {
                            "type": "interactive",
                            "title": "Hands-on Practice",
                            "content": f"Interactive exercises to practice {topic}",
                            "source": "generated",
                            "source_url": None,
                            "duration": 900
                        }
                    ]
                },
                {
                    "title": f"Mastering {topic.title()}",
                    "description": f"Advanced concepts and real-world applications",
                    "objectives": [
                        f"Master advanced {topic} concepts",
                        f"Build real-world projects",
                        f"Optimize for performance"
                    ],
                    "items": [
                        {
                            "type": "text",
                            "title": "Best Practices",
                            "content": f"Industry best practices for {topic}",
                            "source": "generated",
                            "source_url": None,
                            "duration": 480
                        },
                        {
                            "type": "assessment",
                            "title": "Final Assessment",
                            "content": f"Comprehensive assessment of your {topic} knowledge",
                            "source": "generated",
                            "source_url": None,
                            "duration": 1200
                        }
                    ]
                }
            ]
        }
        
        return outline
    
    async def create_course_content(
        self, 
        db: Session, 
        user_id: str, 
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> str:
        """Create complete course with lessons and items."""
        
        if progress_callback:
            progress_callback(10, "Generating course outline...")
        
        # Generate course outline
        outline = await self.generate_course_outline(payload)
        
        if progress_callback:
            progress_callback(25, "Creating course structure...")
        
        # Create course record
        clean_user_id = user_id or 1

        course = Course(
            instructor_id=clean_user_id,
            title=outline["title"],
            description=outline["description"],
            status=CourseStatus.READY if not outline.get("lessons") else CourseStatus.GENERATING,
            topic=payload.get("topic"),
            interests=payload.get("interests", {}),
            difficulty_level=payload.get("level", "beginner"),
            target_duration_hours=float(payload.get("duration_hours", 0)),
            generation_metadata={
                "ai_model": "gemini-fallback",
                "generation_time": datetime.utcnow().isoformat(),
                "user_preferences": payload
            }
        )
        
        db.add(course)
        db.commit()
        db.refresh(course)
        
        if progress_callback:
            progress_callback(40, "Creating lessons...")
        
        # Create lessons and items
        total_items = 0
        for lesson_idx, lesson_data in enumerate(outline["lessons"]):
            lesson = Lesson(
                course_id=course.id,
                title=lesson_data["title"],
                description=lesson_data["description"],
                order_index=lesson_idx,
                summary=", ".join(lesson_data.get("objectives", [])) if lesson_data.get("objectives") else None,
                content_type=lesson_data.get("content_type", "text"),
                duration_minutes=int(lesson_data.get("estimated_duration", 15))
            )
            
            db.add(lesson)
            db.commit()
            db.refresh(lesson)
            
            # Create course items for this lesson
            for item_idx, item_data in enumerate(lesson_data.get("items", [])):
                item = CourseItem(
                    course_id=course.id,
                    lesson_id=lesson.id,
                    type=item_data.get("type", "text"),
                    title=item_data["title"],
                    description=item_data.get("content"), # Map content to description
                    source=item_data.get("source"),
                    source_url=item_data.get("source_url"),
                    duration_sec=int(item_data.get("duration", 0)),
                )
                
                db.add(item)
                total_items += 1
            
            db.commit()
            
            # Update progress
            progress = 40 + int((lesson_idx + 1) / len(outline["lessons"]) * 40)
            if progress_callback:
                progress_callback(progress, f"Created lesson: {lesson_data['title']}")
        
        # Update course with final counts
        course.status = CourseStatus.READY
        course.published_at = datetime.utcnow()
        
        db.commit()
        
        if progress_callback:
            progress_callback(90, "Finalizing course...")
        
        logger.info(f"Generated course '{course.title}' with {len(outline['lessons'])} lessons and {total_items} items")
        
        return str(course.id)


# Global course generator instance
course_generator = CourseGenerator()


@celery_app.task(bind=True)
def generate_course_task(self, task_id: str, user_id: str, payload: Dict[str, Any]):
    """
    Celery task to generate course content.
    Updates task progress in database and publishes real-time updates.
    """
    db = get_sync_db()
    
    try:
        # Get task record - handle both int and UUID task_ids
        try:
            task_id_clean = int(task_id)
            task = db.query(Task).filter(Task.id == task_id_clean).first()
        except ValueError:
            # Fallback if task_ids are UUID strings in some environments
            task = db.query(Task).filter(Task.id == task_id).first()

        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # Update task state to running
        task.state = TaskState.RUNNING
        task.started_at = datetime.utcnow()
        task.progress_pct = 5
        task.message = "Starting course generation..."
        db.commit()
        
        # Publish initial progress
        asyncio.run(publish_task_progress(task_id, {
            "state": TaskState.RUNNING.value,
            "progressPct": 5,
            "message": "Starting course generation..."
        }))
        
        # Progress callback
        def update_progress(pct: int, message: str):
            task.progress_pct = pct
            task.message = message
            db.commit()
            
            # Publish progress update
            asyncio.run(publish_task_progress(task_id, {
                "state": TaskState.RUNNING.value,
                "progressPct": pct,
                "message": message
            }))
        
        # Run async course generation
        course_id = asyncio.run(course_generator.create_course_content(
            db=db,
            user_id=user_id,
            payload=payload,
            progress_callback=update_progress
        ))
        
        # Update task to completed
        task.state = TaskState.DONE
        task.progress_pct = 100
        task.message = "Course generation completed"
        # Handle course_id as int if necessary
        try:
            task.result_course_id = int(course_id)
        except (ValueError, TypeError):
            task.result_course_id = course_id 
            
        task.completed_at = datetime.utcnow()
        db.commit()
        
        # Publish completion
        asyncio.run(publish_task_progress(task_id, {
            "state": TaskState.DONE.value,
            "progressPct": 100,
            "message": "Course generation completed",
            "resultId": course_id
        }))
        
        # Trigger course completion notification
        from lyo_app.tasks.notifications import notify_course_ready_task
        notify_course_ready_task.delay(user_id, course_id)
        
        logger.info(f"Course generation task {task_id} completed successfully")
        return course_id
        
    except Exception as e:
        logger.exception(f"Course generation task {task_id} failed")
        
        # Update task to error state
        try:
            task.state = TaskState.ERROR
            task.message = str(e)
            task.error_details = str(e)
            task.completed_at = datetime.utcnow()
            db.commit()
            
            # Publish error
            asyncio.run(publish_task_progress(task_id, {
                "state": TaskState.ERROR.value,
                "message": str(e)
            }))
        except Exception as db_error:
            logger.error(f"Failed to update task error state: {db_error}")
        
        raise
    
    finally:
        db.close()


def ensure_model_ready() -> bool:
    """Ensure AI model is ready for course generation."""
    return course_generator.ensure_model()
