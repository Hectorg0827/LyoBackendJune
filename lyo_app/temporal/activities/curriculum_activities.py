"""
Curriculum Activities - Temporal wrappers for CurriculumDesignAgent methods

These activities:
1. Make agent calls durable and retriable
2. Handle timeouts gracefully (Gemini can be slow)
3. Provide heartbeats for long-running generations
4. Use strict Pydantic schemas for input/output

Design principles:
- Activities are THIN wrappers - all business logic stays in agents
- Agents remain pure Python - can be tested without Temporal
- Activities handle infrastructure concerns (retry, timeout, heartbeat)
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional
from temporalio import activity
from temporalio.exceptions import ApplicationError

from lyo_app.temporal.schemas.generation_schemas import (
    CurriculumParams,
    CurriculumResult,
    LessonParams,
    LessonResult,
    ModuleSpec,
    LessonSpec,
    DifficultyLevel,
    ContentType,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# MARK: - Curriculum Generation Activity
# ==============================================================================

@activity.defn
async def generate_curriculum_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a curriculum outline for a given topic.
    
    This is a DURABLE activity - if the server crashes mid-generation,
    Temporal will retry this activity on a new worker.
    
    Args:
        params: CurriculumParams as dict (serialized for Temporal)
        
    Returns:
        CurriculumResult as dict
    """
    # Import inside activity to avoid circular imports
    from lyo_app.ai_agents.curriculum_agent import CurriculumDesignAgent
    from lyo_app.learning.models import DifficultyLevel as DBDifficultyLevel
    from lyo_app.ai_agents.orchestrator import LanguageCode
    
    logger.info(f"[Activity] Starting curriculum generation for topic: {params.get('topic')}")
    
    # Heartbeat to tell Temporal we're still alive (for long generations)
    activity.heartbeat("Starting curriculum generation")
    
    try:
        # Create agent instance
        agent = CurriculumDesignAgent()
        
        # Map params to agent method signature
        # Note: We don't have a real DB session in activity - agent handles this
        topic = params.get("topic", "")
        user_id = params.get("user_id")
        difficulty = params.get("difficulty", "beginner")
        target_duration = params.get("target_duration_hours", 10)
        language = params.get("language", "en")
        objectives = params.get("learning_objectives", [])
        
        # Map difficulty string to enum
        difficulty_map = {
            "beginner": DBDifficultyLevel.BEGINNER,
            "intermediate": DBDifficultyLevel.INTERMEDIATE,
            "advanced": DBDifficultyLevel.ADVANCED,
            "expert": DBDifficultyLevel.EXPERT,
        }
        db_difficulty = difficulty_map.get(difficulty.lower(), DBDifficultyLevel.BEGINNER)
        
        # Map language string to enum
        lang_map = {
            "en": LanguageCode.ENGLISH,
            "es": LanguageCode.SPANISH,
            "fr": LanguageCode.FRENCH,
            "de": LanguageCode.GERMAN,
        }
        lang_code = lang_map.get(language.lower(), LanguageCode.ENGLISH)
        
        # Heartbeat before AI call
        activity.heartbeat("Calling AI model for curriculum")
        
        # Call the agent (without DB for now - we'll add session injection later)
        result = await agent.generate_course_outline(
            title=topic,
            description=f"AI-generated curriculum for {topic}",
            target_audience="General learners",
            learning_objectives=objectives if objectives else [
                f"Understand the fundamentals of {topic}",
                f"Apply {topic} concepts in practical scenarios",
                f"Build proficiency in {topic}",
            ],
            difficulty_level=db_difficulty,
            estimated_duration_hours=target_duration,
            db=None,  # Activity runs without DB session - agent handles gracefully
            user_id=int(user_id) if user_id else None,
            language=lang_code,
        )
        
        activity.heartbeat("Curriculum generation complete")
        
        # Check for errors in result
        if "error" in result:
            raise ApplicationError(
                f"Curriculum generation failed: {result['error']}",
                non_retryable=False,  # Allow retry on failure
            )
        
        logger.info(f"[Activity] Curriculum generated successfully for: {topic}")
        return result
        
    except Exception as e:
        logger.error(f"[Activity] Curriculum generation failed: {e}")
        raise ApplicationError(
            f"Curriculum generation failed: {str(e)}",
            non_retryable=False,
        )


# ==============================================================================
# MARK: - Lesson Generation Activity
# ==============================================================================

@activity.defn
async def generate_lesson_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate content for a single lesson.
    
    Args:
        params: LessonParams as dict
        
    Returns:
        LessonResult as dict
    """
    from lyo_app.ai_agents.curriculum_agent import CurriculumDesignAgent
    from lyo_app.learning.models import DifficultyLevel as DBDifficultyLevel
    from lyo_app.learning.models import ContentType as DBContentType
    
    lesson_title = params.get("lesson_title", "Untitled Lesson")
    logger.info(f"[Activity] Starting lesson generation for: {lesson_title}")
    
    activity.heartbeat(f"Generating lesson: {lesson_title}")
    
    try:
        agent = CurriculumDesignAgent()
        
        # Map content type
        content_type_map = {
            "text": DBContentType.TEXT,
            "video": DBContentType.VIDEO,
            "interactive": DBContentType.INTERACTIVE,
            "quiz": DBContentType.QUIZ,
            "mixed": DBContentType.MIXED,
        }
        content_type = content_type_map.get(
            params.get("content_type", "mixed").lower(), 
            DBContentType.MIXED
        )
        
        # Map difficulty
        difficulty_map = {
            "beginner": DBDifficultyLevel.BEGINNER,
            "intermediate": DBDifficultyLevel.INTERMEDIATE,
            "advanced": DBDifficultyLevel.ADVANCED,
            "expert": DBDifficultyLevel.EXPERT,
        }
        difficulty = difficulty_map.get(
            params.get("difficulty", "beginner").lower(),
            DBDifficultyLevel.BEGINNER
        )
        
        activity.heartbeat("Calling AI for lesson content")
        
        result = await agent.generate_lesson_content(
            course_id=params.get("course_id", 0),
            lesson_title=lesson_title,
            lesson_description=params.get("lesson_description", ""),
            learning_objectives=params.get("learning_objectives", []),
            content_type=content_type,
            difficulty_level=difficulty,
            db=None,
            user_id=params.get("user_id"),
        )
        
        activity.heartbeat("Lesson generation complete")
        
        if "error" in result:
            raise ApplicationError(
                f"Lesson generation failed: {result['error']}",
                non_retryable=False,
            )
        
        logger.info(f"[Activity] Lesson generated successfully: {lesson_title}")
        return result
        
    except Exception as e:
        logger.error(f"[Activity] Lesson generation failed: {e}")
        raise ApplicationError(
            f"Lesson generation failed: {str(e)}",
            non_retryable=False,
        )


# ==============================================================================
# MARK: - Learning Path Activity
# ==============================================================================

@activity.defn
async def generate_learning_path_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a personalized learning path for a user.
    
    Args:
        params: Learning path parameters
        
    Returns:
        Learning path structure
    """
    from lyo_app.ai_agents.curriculum_agent import CurriculumDesignAgent
    from lyo_app.learning.models import DifficultyLevel as DBDifficultyLevel
    
    user_id = params.get("user_id")
    learning_goal = params.get("learning_goal", "")
    
    logger.info(f"[Activity] Generating learning path for user {user_id}: {learning_goal}")
    
    activity.heartbeat(f"Generating learning path: {learning_goal}")
    
    try:
        agent = CurriculumDesignAgent()
        
        difficulty_map = {
            "beginner": DBDifficultyLevel.BEGINNER,
            "intermediate": DBDifficultyLevel.INTERMEDIATE,
            "advanced": DBDifficultyLevel.ADVANCED,
            "expert": DBDifficultyLevel.EXPERT,
        }
        
        current_level = difficulty_map.get(
            params.get("current_skill_level", "beginner").lower(),
            DBDifficultyLevel.BEGINNER
        )
        target_level = difficulty_map.get(
            params.get("target_skill_level", "advanced").lower(),
            DBDifficultyLevel.ADVANCED
        )
        
        activity.heartbeat("Calling AI for learning path")
        
        result = await agent.generate_learning_path(
            user_id=int(user_id) if user_id else 0,
            learning_goal=learning_goal,
            current_skill_level=current_level,
            target_skill_level=target_level,
            time_constraint_hours=params.get("time_constraint_hours"),
            include_existing_courses=params.get("include_existing_courses", True),
            db=None,
        )
        
        activity.heartbeat("Learning path generation complete")
        
        if "error" in result:
            raise ApplicationError(
                f"Learning path generation failed: {result['error']}",
                non_retryable=False,
            )
        
        logger.info(f"[Activity] Learning path generated for: {learning_goal}")
        return result
        
    except Exception as e:
        logger.error(f"[Activity] Learning path generation failed: {e}")
        raise ApplicationError(
            f"Learning path generation failed: {str(e)}",
            non_retryable=False,
        )


# ==============================================================================
# MARK: - Activity Registration (for Worker)
# ==============================================================================

def get_all_curriculum_activities():
    """Return list of all curriculum activities for worker registration."""
    return [
        generate_curriculum_activity,
        generate_lesson_activity,
        generate_learning_path_activity,
    ]
