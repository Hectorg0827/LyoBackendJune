"""
Generation Schemas - Pydantic models for constrained AI generation

These models are used:
1. As input/output types for Temporal activities
2. With Gemini's response_schema parameter to enforce structure
3. For validation of AI responses

Key principle: The AI cannot hallucinate structure - it MUST match these schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


# ==============================================================================
# MARK: - Enums
# ==============================================================================

class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ContentType(str, Enum):
    TEXT = "text"
    VIDEO = "video"
    INTERACTIVE = "interactive"
    QUIZ = "quiz"
    MIXED = "mixed"


# ==============================================================================
# MARK: - Curriculum Schemas
# ==============================================================================

class CurriculumParams(BaseModel):
    """Input parameters for curriculum generation activity."""
    topic: str = Field(..., min_length=1, max_length=500, description="Topic to generate curriculum for")
    user_id: Optional[str] = Field(None, description="User ID for personalization")
    difficulty: DifficultyLevel = Field(DifficultyLevel.BEGINNER, description="Target difficulty level")
    target_duration_hours: int = Field(10, ge=1, le=100, description="Target course duration in hours")
    language: str = Field("en", description="Content language (ISO code)")
    learning_objectives: Optional[List[str]] = Field(None, description="Specific learning objectives")

    class Config:
        use_enum_values = True


class LessonSpec(BaseModel):
    """Specification for a single lesson within a curriculum."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=1000)
    duration_minutes: int = Field(..., ge=5, le=120)
    learning_objectives: List[str] = Field(..., min_length=1, max_length=5)
    order: int = Field(..., ge=0)
    content_type: ContentType = Field(ContentType.MIXED)
    
    class Config:
        use_enum_values = True


class ModuleSpec(BaseModel):
    """Specification for a module (group of related lessons)."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=500)
    lessons: List[LessonSpec] = Field(..., min_length=1, max_length=10)
    order: int = Field(..., ge=0)


class CurriculumResult(BaseModel):
    """Output from curriculum generation activity."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=2000)
    difficulty: DifficultyLevel
    estimated_hours: int = Field(..., ge=1)
    modules: List[ModuleSpec] = Field(..., min_length=1, max_length=20)
    prerequisites: List[str] = Field(default_factory=list)
    target_audience: str = Field("")
    
    class Config:
        use_enum_values = True
    
    @property
    def total_lessons(self) -> int:
        return sum(len(module.lessons) for module in self.modules)


# ==============================================================================
# MARK: - Lesson Schemas
# ==============================================================================

class LessonParams(BaseModel):
    """Input parameters for lesson content generation activity."""
    lesson_spec: LessonSpec
    curriculum_context: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None
    include_assessment: bool = Field(True)
    

class QuizQuestion(BaseModel):
    """A single quiz question."""
    question: str = Field(..., min_length=10, max_length=500)
    options: List[str] = Field(..., min_length=2, max_length=6)
    correct_index: int = Field(..., ge=0)
    explanation: str = Field("", max_length=500)


class ContentBlock(BaseModel):
    """A block of lesson content."""
    type: str = Field(..., description="Block type: text, heading, code, image, video, etc.")
    content: str = Field(...)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LessonResult(BaseModel):
    """Output from lesson content generation activity."""
    title: str
    content_blocks: List[ContentBlock] = Field(..., min_length=1)
    key_points: List[str] = Field(default_factory=list)
    vocabulary: Dict[str, str] = Field(default_factory=dict, description="Term -> definition")
    quiz_questions: List[QuizQuestion] = Field(default_factory=list)
    estimated_read_time_minutes: int = Field(..., ge=1)


# ==============================================================================
# MARK: - Course Result (Full Workflow Output)
# ==============================================================================

class CourseResult(BaseModel):
    """Complete output from the course generation workflow."""
    course_id: str
    curriculum: CurriculumResult
    lessons: List[LessonResult]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generation_time_seconds: float = Field(0.0)
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ==============================================================================
# MARK: - Workflow Status (For Polling)
# ==============================================================================

class WorkflowStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowProgress(BaseModel):
    """Progress information for long-running workflows."""
    status: WorkflowStatus
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    progress_percentage: float = Field(0.0, ge=0, le=100)
    error_message: Optional[str] = None
    
    class Config:
        use_enum_values = True
