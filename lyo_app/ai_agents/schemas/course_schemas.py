"""
Strict Pydantic schemas for Multi-Agent Course Generation.
These schemas ENFORCE structure - AI cannot return malformed data.

MIT Architecture Engineering - Production Grade Schemas
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Union, Annotated, Any
from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime


# ============================================================
# ENUMS
# ============================================================

class DifficultyLevel(str, Enum):
    """Course difficulty levels"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ContentBlockType(str, Enum):
    """Types of content blocks in a lesson"""
    TEXT = "text"
    CODE = "code"
    IMAGE = "image"
    VIDEO = "video"
    EXERCISE = "exercise"
    QUIZ_PREVIEW = "quiz_preview"


class QuestionType(str, Enum):
    """Types of quiz questions"""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    CODE_COMPLETION = "code_completion"


# ============================================================
# STEP 1: Orchestrator Output - CourseIntent
# ============================================================

class CourseIntent(BaseModel):
    """
    Output from Orchestrator Agent - parsed user intent.
    This is the foundation that all other agents build upon.
    """
    
    job_id: UUID = Field(default_factory=uuid4, description="Unique job identifier")
    topic: str = Field(..., min_length=3, max_length=200, description="Main course topic")
    target_audience: DifficultyLevel = Field(..., description="Target difficulty level")
    estimated_duration_hours: int = Field(..., ge=1, le=100, description="Estimated total hours")
    learning_objectives: List[str] = Field(
        ..., 
        min_length=3, 
        max_length=10,
        description="Specific, measurable learning objectives"
    )
    prerequisites: List[str] = Field(
        default_factory=list,
        description="Required prior knowledge"
    )
    tags: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Categorization tags"
    )
    teaching_style: str = Field(
        default="interactive",
        description="Teaching approach: interactive, lecture, project-based"
    )
    
    @field_validator('learning_objectives')
    @classmethod
    def objectives_not_empty(cls, v: List[str]) -> List[str]:
        """Ensure learning objectives are meaningful"""
        for obj in v:
            if len(obj.strip()) < 10:
                raise ValueError(f"Learning objective too short: {obj}")
        return v
    
    @field_validator('topic')
    @classmethod
    def topic_not_generic(cls, v: str) -> str:
        """Ensure topic is specific enough"""
        weak_topics = ["course", "learn", "study", "thing", "stuff", "something"]
        if v.lower().strip() in weak_topics:
            raise ValueError(f"Topic '{v}' is too vague")
        return v


# ============================================================
# STEP 2: Curriculum Architect Output
# ============================================================

class LessonOutline(BaseModel):
    """Outline for a single lesson within a module"""
    
    id: str = Field(..., pattern=r'^les_\d+_\d+$', description="Lesson ID (e.g., les_1_1)")
    title: str = Field(..., min_length=5, max_length=100)
    description: str = Field(..., min_length=20, max_length=500)
    estimated_minutes: int = Field(..., ge=5, le=60)
    learning_outcomes: List[str] = Field(..., min_length=1, max_length=5)
    
    @field_validator('learning_outcomes')
    @classmethod
    def outcomes_have_content(cls, v: List[str]) -> List[str]:
        for outcome in v:
            if len(outcome.strip()) < 10:
                raise ValueError(f"Learning outcome too short: {outcome}")
        return v


class ModuleOutline(BaseModel):
    """Outline for a course module containing multiple lessons"""
    
    id: str = Field(..., pattern=r'^mod_\d+$', description="Module ID (e.g., mod_1)")
    title: str = Field(..., min_length=5, max_length=100)
    description: str = Field(..., min_length=20, max_length=500)
    lessons: List[LessonOutline] = Field(..., min_length=2, max_length=7)
    prerequisites: List[str] = Field(
        default_factory=list,
        description="Module IDs that must be completed first"
    )
    learning_outcomes: List[str] = Field(..., min_length=1, max_length=5)
    
    @field_validator('prerequisites')
    @classmethod
    def valid_prerequisite_format(cls, v: List[str]) -> List[str]:
        for prereq in v:
            if prereq and not prereq.startswith('mod_'):
                raise ValueError(f"Invalid prerequisite format: {prereq}")
        return v


class CurriculumStructure(BaseModel):
    """Complete curriculum structure from Curriculum Architect"""
    
    course_title: str = Field(..., min_length=5, max_length=150)
    course_description: str = Field(..., min_length=50, max_length=1000)
    modules: List[ModuleOutline] = Field(..., min_length=3, max_length=12)
    total_estimated_hours: float = Field(..., ge=1, le=100)
    
    @model_validator(mode='after')
    def validate_prerequisite_dag(self) -> 'CurriculumStructure':
        """Ensure prerequisites form a valid DAG (no cycles)"""
        module_ids = {m.id for m in self.modules}
        
        for module in self.modules:
            for prereq in module.prerequisites:
                if prereq not in module_ids:
                    raise ValueError(f"Unknown prerequisite: {prereq}")
                if prereq == module.id:
                    raise ValueError(f"Module cannot be its own prerequisite: {module.id}")
        
        # Check for cycles using DFS
        def has_cycle() -> bool:
            visited = set()
            rec_stack = set()
            
            def dfs(mod_id: str) -> bool:
                visited.add(mod_id)
                rec_stack.add(mod_id)
                
                mod = next((m for m in self.modules if m.id == mod_id), None)
                if mod:
                    for prereq in mod.prerequisites:
                        if prereq not in visited:
                            if dfs(prereq):
                                return True
                        elif prereq in rec_stack:
                            return True
                
                rec_stack.remove(mod_id)
                return False
            
            for module in self.modules:
                if module.id not in visited:
                    if dfs(module.id):
                        return True
            return False
        
        if has_cycle():
            raise ValueError("Prerequisites contain a cycle")
        
        return self


# ============================================================
# STEP 3: Content Creator Output
# ============================================================

class TextBlock(BaseModel):
    """Text content block for explanations"""
    type: str = Field(default="text", frozen=True)
    content: str = Field(..., min_length=50)
    format: str = Field(default="markdown", description="text, markdown, html")


class CodeBlock(BaseModel):
    """Code content block with syntax validation"""
    type: str = Field(default="code", frozen=True)
    language: str = Field(
        ..., 
        pattern=r'^(python|javascript|java|cpp|sql|html|css|typescript|rust|go)$'
    )
    code: str = Field(..., min_length=10)
    explanation: Optional[str] = Field(default=None)
    runnable: bool = Field(default=True)
    expected_output: Optional[str] = Field(default=None)


class ExerciseBlock(BaseModel):
    """Interactive exercise block"""
    type: str = Field(default="exercise", frozen=True)
    prompt: str = Field(..., min_length=20)
    starter_code: Optional[str] = Field(default=None)
    solution: str = Field(..., min_length=10)
    hints: List[str] = Field(default_factory=list, max_length=3)
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.INTERMEDIATE)
    test_cases: List[str] = Field(default_factory=list, description="Test cases for validation")


class ContentBlock(BaseModel):
    """Wrapper for any content block type"""
    block: Union[TextBlock, CodeBlock, ExerciseBlock] = Field(
        ..., 
        discriminator='type'
    )
    order: int = Field(..., ge=0)


class LessonContent(BaseModel):
    """Complete lesson content from Content Creator"""
    
    lesson_id: str = Field(..., pattern=r'^les_\d+_\d+$')
    title: str = Field(..., min_length=5, max_length=100)
    content_blocks: List[ContentBlock] = Field(..., min_length=3, max_length=25)
    key_takeaways: List[str] = Field(..., min_length=2, max_length=5)
    estimated_minutes: int = Field(..., ge=5, le=60)
    next_lesson_preview: Optional[str] = Field(default=None, description="Teaser for next lesson")
    
    @model_validator(mode='after')
    def has_variety(self) -> 'LessonContent':
        """Ensure lesson has variety of content types"""
        types = {b.block.type for b in self.content_blocks}
        if len(types) < 2:
            raise ValueError("Lesson must have at least 2 different content types")
        return self


# ============================================================
# STEP 4: Assessment Designer Output
# ============================================================

class MultipleChoiceQuestion(BaseModel):
    """Multiple choice question with 4 options"""
    type: str = Field(default="multiple_choice", frozen=True)
    question: str = Field(..., min_length=20)
    options: List[str] = Field(..., min_length=4, max_length=4)
    correct_answer: int = Field(..., ge=0, le=3, description="Index of correct option (0-3)")
    explanation: str = Field(..., min_length=20)
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.INTERMEDIATE)
    
    @field_validator('options')
    @classmethod
    def options_unique(cls, v: List[str]) -> List[str]:
        if len(set(v)) != len(v):
            raise ValueError("All options must be unique")
        return v


class TrueFalseQuestion(BaseModel):
    """True/False question"""
    type: str = Field(default="true_false", frozen=True)
    statement: str = Field(..., min_length=20)
    correct_answer: bool
    explanation: str = Field(..., min_length=20)
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.BEGINNER)


class CodeQuestion(BaseModel):
    """Code completion/debugging question"""
    type: str = Field(default="code_completion", frozen=True)
    prompt: str = Field(..., min_length=20)
    language: str = Field(default="python")
    starter_code: str = Field(...)
    expected_output: str = Field(...)
    solution: str = Field(..., min_length=10)
    test_cases: List[str] = Field(..., min_length=1, max_length=5)
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.INTERMEDIATE)


class QuizQuestion(BaseModel):
    """Union of all question types"""
    question: Union[MultipleChoiceQuestion, TrueFalseQuestion, CodeQuestion] = Field(
        ...,
        discriminator='type'
    )


class LessonQuiz(BaseModel):
    """Quiz for a single lesson"""
    
    lesson_id: str = Field(..., pattern=r'^les_\d+_\d+$')
    questions: List[QuizQuestion] = Field(..., min_length=3, max_length=10)
    passing_score: float = Field(default=0.7, ge=0.5, le=1.0)
    time_limit_minutes: Optional[int] = Field(default=None, ge=5, le=30)
    
    @model_validator(mode='after')
    def validate_answer_distribution(self) -> 'LessonQuiz':
        """Check that MC answers aren't all the same"""
        mc_answers = []
        for q in self.questions:
            if hasattr(q.question, 'correct_answer') and isinstance(q.question.correct_answer, int):
                mc_answers.append(q.question.correct_answer)
        
        # If all answers are the same (and there are more than 2), flag it
        if mc_answers and len(set(mc_answers)) == 1 and len(mc_answers) > 2:
            raise ValueError("All multiple choice answers are the same option - vary them")
        
        return self


class ModuleAssessment(BaseModel):
    """Assessment for completing a module"""
    
    module_id: str = Field(..., pattern=r'^mod_\d+$')
    title: str = Field(default="Module Assessment")
    questions: List[QuizQuestion] = Field(..., min_length=5, max_length=20)
    passing_score: float = Field(default=0.7, ge=0.5, le=1.0)
    time_limit_minutes: Optional[int] = Field(default=None, ge=10, le=60)


class CourseAssessments(BaseModel):
    """All assessments for the course"""
    
    lesson_quizzes: List[LessonQuiz] = Field(...)
    module_assessments: List[ModuleAssessment] = Field(...)
    final_exam: Optional[ModuleAssessment] = Field(default=None)


# ============================================================
# STEP 5: Quality Assurance Output
# ============================================================

class QualityIssue(BaseModel):
    """A quality issue found by QA Agent"""
    
    location: str = Field(..., description="e.g., mod_1.les_1_1.content_block_3")
    severity: str = Field(..., pattern=r'^(critical|high|medium|low)$')
    issue_type: str = Field(..., description="e.g., accuracy, clarity, completeness")
    description: str = Field(..., min_length=10)
    suggested_fix: Optional[str] = Field(default=None)


class QualityReport(BaseModel):
    """Quality assurance report from QA Agent"""
    
    overall_score: float = Field(..., ge=0, le=10)
    content_accuracy_score: float = Field(..., ge=0, le=10)
    pedagogical_score: float = Field(..., ge=0, le=10)
    engagement_score: float = Field(..., ge=0, le=10)
    issues: List[QualityIssue] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    approved: bool = Field(default=False)
    
    @model_validator(mode='after')
    def auto_approve_logic(self) -> 'QualityReport':
        """Auto-approve if score >= 7 and no critical issues"""
        has_critical = any(i.severity == "critical" for i in self.issues)
        # Only auto-set approved if it wasn't explicitly set
        if self.overall_score >= 7.0 and not has_critical:
            object.__setattr__(self, 'approved', True)
        elif has_critical:
            object.__setattr__(self, 'approved', False)
        return self


# ============================================================
# COMPLETE COURSE OUTPUT
# ============================================================

class GeneratedCourse(BaseModel):
    """Complete generated course with all components"""
    
    job_id: UUID
    intent: CourseIntent
    curriculum: CurriculumStructure
    lessons: List[LessonContent]
    assessments: CourseAssessments
    quality_report: QualityReport
    
    # Metadata
    generation_time_seconds: float = Field(..., ge=0)
    total_tokens_used: int = Field(..., ge=0)
    ai_provider: str = Field(default="gemini-1.5-flash")
    version: str = Field(default="2.0.0")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Status
    is_published: bool = Field(default=False)
    is_approved: bool = Field(default=False)
    
    @model_validator(mode='after')
    def set_approval_status(self) -> 'GeneratedCourse':
        """Set course approval based on QA report"""
        object.__setattr__(self, 'is_approved', self.quality_report.approved)
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "intent": {"topic": "Python Programming"},
                "curriculum": {"modules": []},
                "lessons": [],
                "assessments": {"lesson_quizzes": [], "module_assessments": []},
                "quality_report": {"overall_score": 8.5, "approved": True}
            }
        }


# ============================================================
# HELPER SCHEMAS FOR API
# ============================================================

class CourseGenerationRequest(BaseModel):
    """API request to generate a new course"""
    
    prompt: str = Field(..., min_length=10, max_length=1000)
    difficulty: Optional[DifficultyLevel] = Field(default=None)
    max_duration_hours: Optional[int] = Field(default=None, ge=1, le=100)
    teaching_style: Optional[str] = Field(default="interactive")
    include_assessments: bool = Field(default=True)
    include_exercises: bool = Field(default=True)


class CourseGenerationStatus(BaseModel):
    """Status response for course generation job"""
    
    job_id: UUID
    status: str = Field(..., description="pending, running, completed, failed")
    progress_percent: int = Field(..., ge=0, le=100)
    current_step: str = Field(...)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    estimated_remaining_seconds: Optional[int] = Field(default=None)


class RegenerationRequest(BaseModel):
    """Request to regenerate a specific part of a course"""
    
    course_id: UUID
    target: str = Field(..., description="What to regenerate: lesson, module, quiz, etc.")
    target_id: str = Field(..., description="ID of the element to regenerate")
    feedback: Optional[str] = Field(default=None, description="User feedback for improvement")
