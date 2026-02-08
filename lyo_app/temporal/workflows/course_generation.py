"""
Course Generation Workflow - Durable AI Course Creation Pipeline

This workflow orchestrates the full course generation process:
1. Generate curriculum structure
2. Generate content for each lesson
3. Compile final course

Key features:
- Survives server crashes - resumes exactly where it left off
- Auto-retries failed AI calls with exponential backoff
- Provides progress updates via queries
- Versioned for safe deployment updates
"""

import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activity stubs (actual activities loaded by worker)
with workflow.unsafe.imports_passed_through():
    from lyo_app.temporal.schemas.generation_schemas import WorkflowStatus

logger = logging.getLogger(__name__)


# ==============================================================================
# MARK: - Workflow State
# ==============================================================================

@dataclass
class WorkflowState:
    """Tracks workflow progress for querying."""
    status: str = "PENDING"
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    error_message: Optional[str] = None
    lessons_completed: List[str] = field(default_factory=list)
    # Optimized Hydration
    append_items: List[Dict[str, Any]] = field(default_factory=list)
    replace_items: List[Dict[str, Any]] = field(default_factory=list)
    proxy_justification: Optional[str] = None


# ==============================================================================
# MARK: - Course Generation Workflow V1
# ==============================================================================

@workflow.defn
class CourseGenerationWorkflowV1:
    """
    Durable workflow for generating a complete AI course.
    
    This is V1 - when we need breaking changes, create V2 and keep V1 running
    for in-flight workflows.
    
    Usage:
        workflow_id = await client.start_workflow(
            CourseGenerationWorkflowV1.run,
            {"topic": "Python Basics", "difficulty": "beginner"},
            id="course-123",
            task_queue="lyo-ai-queue",
        )
    """
    
    def __init__(self):
        self._state = WorkflowState()
    
    # --------------------------------------------------------------------------
    # MARK: - Main Workflow Entry Point
    # --------------------------------------------------------------------------
    
    @workflow.run
    async def run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the full course generation pipeline.
        
        Args:
            params: Course generation parameters
                - topic: str (required)
                - difficulty: str (default: "beginner")
                - target_duration_hours: int (default: 10)
                - user_id: Optional[str]
                - language: str (default: "en")
                
        Returns:
            Complete course with curriculum and lessons
        """
        topic = params.get("topic", "Unknown Topic")
        workflow.logger.info(f"Starting course generation for: {topic}")
        
        # Initialize state
        self._state.status = "RUNNING"
        self._state.current_step = "Initializing"
        
        try:
            # Step 1: Generate Curriculum
            self._state.current_step = "Generating curriculum structure"
            curriculum = await self._generate_curriculum(params)
            
            if "error" in curriculum:
                raise Exception(curriculum["error"])
            
            # Calculate total steps (1 for curriculum + N lessons)
            lessons_in_outline = curriculum.get("outline", {}).get("lessons", [])
            self._state.total_steps = 1 + len(lessons_in_outline)
            self._state.completed_steps = 1
            
            # Step 1.2: OPTIMISTIC HYDRATION - Outline First
            # We immediately append all lessons from the outline as "placeholders"
            # The client will see the full course structure immediately.
            for i, lesson_spec in enumerate(lessons_in_outline):
                lesson_title = lesson_spec.get("title", f"Lesson {i+1}")
                self._state.append_items.append({
                    "type": "lesson",
                    "content": {
                        "title": lesson_title,
                        "description": lesson_spec.get("description", "Generating content..."),
                        "estimated_duration": lesson_spec.get("duration_minutes", 30),
                        "content_type": lesson_spec.get("content_type", "text"),
                        "target_id": f"placeholder-{i}", # Heuristic ID
                        "is_placeholder": True
                    }
                })
            
            # Step 1.5: Determine Proxy Justification (Bridge Intro)
            if params.get("difficulty") == "beginner" and len(lessons_in_outline) > 0:
                 self._state.proxy_justification = f"Starting with core concepts to build a foundation for {topic}..."
            
            # Step 2: Generate Each Lesson
            lessons = []
            for i, lesson_spec in enumerate(lessons_in_outline):
                lesson_title = lesson_spec.get("title", f"Lesson {i+1}")
                self._state.current_step = f"Generating lesson: {lesson_title}"
                
                lesson_content = await self._generate_lesson({
                    "lesson_title": lesson_title,
                    "lesson_description": lesson_spec.get("description", ""),
                    "learning_objectives": lesson_spec.get("learning_objectives", []),
                    "content_type": lesson_spec.get("content_type", "mixed"),
                    "difficulty": params.get("difficulty", "beginner"),
                    "course_id": 0,
                    "user_id": params.get("user_id"),
                })
                
                lessons.append(lesson_content)
                self._state.completed_steps += 1
                self._state.lessons_completed.append(lesson_title)
                
                # OPTIMISTIC HYDRATION: Block Replacement Strategy
                # We replace the placeholder we created in Step 1.2 with the final content.
                self._state.replace_items.append({
                    "target_id": f"placeholder-{i}",
                    "content": {
                        "type": "lesson",
                        "title": lesson_title,
                        "description": (lesson_content.get("description") or 
                                       lesson_spec.get("description", "")),
                        "content": lesson_content
                    }
                })
            
            # Step 3: Compile Final Result
            self._state.current_step = "Finalizing course"
            
            result = {
                "course_id": str(uuid.uuid4()),
                "topic": topic,
                "curriculum": curriculum,
                "lessons": lessons,
                "total_lessons": len(lessons),
                "status": "COMPLETED",
            }
            
            self._state.status = "COMPLETED"
            self._state.current_step = "Done"
            
            workflow.logger.info(f"Course generation complete: {topic} ({len(lessons)} lessons)")
            return result
            
        except Exception as e:
            self._state.status = "FAILED"
            self._state.error_message = str(e)
            workflow.logger.error(f"Course generation failed: {e}")
            
            return {
                "error": str(e),
                "status": "FAILED",
                "topic": topic,
            }
    
    # --------------------------------------------------------------------------
    # MARK: - Activity Calls
    # --------------------------------------------------------------------------
    
    async def _generate_curriculum(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call the curriculum generation activity."""
        return await workflow.execute_activity(
            "generate_curriculum_activity",
            params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(minutes=1),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )
    
    async def _generate_lesson(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call the lesson generation activity."""
        return await workflow.execute_activity(
            "generate_lesson_activity",
            params,
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )
    
    # --------------------------------------------------------------------------
    # MARK: - Queries (Check Progress)
    # --------------------------------------------------------------------------
    
    @workflow.query
    def get_status(self) -> Dict[str, Any]:
        """Query the current workflow status."""
        return {
            "status": self._state.status,
            "current_step": self._state.current_step,
            "total_steps": self._state.total_steps,
            "completed_steps": self._state.completed_steps,
            "progress_percentage": (
                (self._state.completed_steps / self._state.total_steps * 100)
                if self._state.total_steps > 0 else 0
            ),
            "lessons_completed": self._state.lessons_completed,
            "error_message": self._state.error_message,
            "append_items": self._state.append_items,
            "replace_items": self._state.replace_items,
            "proxy_justification": self._state.proxy_justification,
        }
    
    @workflow.query
    def get_progress_percentage(self) -> float:
        """Get just the progress percentage (lightweight query)."""
        if self._state.total_steps == 0:
            return 0.0
        return self._state.completed_steps / self._state.total_steps * 100


# ==============================================================================
# MARK: - Workflow Registration
# ==============================================================================

def get_all_workflows():
    """Return list of all workflows for worker registration."""
    return [
        CourseGenerationWorkflowV1,
    ]
