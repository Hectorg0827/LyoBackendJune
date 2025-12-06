"""
Strict Pydantic schemas for Multi-Agent Course Generation.
These schemas ENFORCE structure - AI cannot return malformed data.

MIT Architecture Engineering - Production Grade Schemas
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Union, Annotated, Any, Literal, Dict
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


class LessonType(str, Enum):
    """Types of lessons in a course"""
    CONCEPT = "concept"
    TUTORIAL = "tutorial"
    EXERCISE = "exercise"
    PROJECT = "project"
    QUIZ = "quiz"
    REVIEW = "review"


class TeachingStyle(str, Enum):
    """Teaching styles for course delivery"""
    INTERACTIVE = "interactive"
    PROJECT_BASED = "project-based"
    LECTURE = "lecture"
    HANDS_ON = "hands-on"


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
    teaching_style: TeachingStyle = Field(
        default=TeachingStyle.INTERACTIVE,
        description="Teaching approach"
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
    block_type: Literal["text"] = Field(default="text")
    title: str = Field(..., min_length=3, max_length=100)
    content: str = Field(..., min_length=50)
    format: str = Field(default="markdown", description="text, markdown, html")
    order: int = Field(..., ge=0)


class CodeBlock(BaseModel):
    """Code content block with syntax validation"""
    block_type: Literal["code"] = Field(default="code")
    title: str = Field(..., min_length=3, max_length=100)
    language: str = Field(
        ..., 
        pattern=r'^(python|javascript|java|cpp|sql|html|css|typescript|rust|go|bash|json|yaml)$'
    )
    code: str = Field(..., min_length=5)
    explanation: Optional[str] = Field(default=None)
    filename: Optional[str] = Field(default=None)
    order: int = Field(..., ge=0)


class ExerciseBlock(BaseModel):
    """Interactive exercise block"""
    block_type: Literal["exercise"] = Field(default="exercise")
    title: str = Field(..., min_length=3, max_length=100)
    instructions: str = Field(..., min_length=20)
    difficulty: str = Field(default="medium", pattern=r'^(easy|medium|hard)$')
    hints: List[str] = Field(default_factory=list, max_length=5)
    solution: str = Field(..., min_length=10)
    expected_output: Optional[str] = Field(default=None)
    order: int = Field(..., ge=0)


class MediaBlock(BaseModel):
    """Media content block for diagrams and images"""
    block_type: Literal["media"] = Field(default="media")
    title: str = Field(..., min_length=3, max_length=100)
    media_type: str = Field(..., pattern=r'^(diagram|image|video)$')
    url: str = Field(default="placeholder")
    alt_text: str = Field(..., min_length=5)
    caption: Optional[str] = Field(default=None)
    order: int = Field(..., ge=0)


# Union type for all content blocks - uses discriminated union on block_type
ContentBlock = Annotated[
    Union[TextBlock, CodeBlock, ExerciseBlock, MediaBlock],
    Field(discriminator="block_type")
]


class LessonContent(BaseModel):
    """Complete lesson content from Content Creator"""
    
    lesson_id: str = Field(..., pattern=r'^mod\d+_les\d+$')
    title: str = Field(..., min_length=5, max_length=200)
    lesson_type: LessonType = Field(default=LessonType.CONCEPT)
    introduction: str = Field(..., min_length=50)
    content_blocks: List[ContentBlock] = Field(..., min_length=1, max_length=25)
    summary: str = Field(..., min_length=20)
    key_takeaways: List[str] = Field(..., min_length=1, max_length=10)
    next_steps: Optional[str] = Field(default=None, description="What comes next")


# ============================================================
# STEP 4: Assessment Designer Output
# ============================================================

class QuestionOption(BaseModel):
    """Option for multiple choice question"""
    label: str = Field(..., pattern=r'^[A-D]$')
    text: str = Field(..., min_length=1)


class MultipleChoiceQuestion(BaseModel):
    """Multiple choice question with 4 options"""
    question_type: Literal["multiple_choice"] = Field(default="multiple_choice")
    question_id: str = Field(...)
    question: str = Field(..., min_length=10)
    options: List[QuestionOption] = Field(..., min_length=4, max_length=4)
    correct_answer: str = Field(..., pattern=r'^[A-D]$')
    explanation: str = Field(..., min_length=10)
    difficulty: str = Field(default="medium", pattern=r'^(easy|medium|hard)$')
    learning_objective: Optional[str] = Field(default=None)
    points: int = Field(default=10, ge=1)


class TrueFalseQuestion(BaseModel):
    """True/False question"""
    question_type: Literal["true_false"] = Field(default="true_false")
    question_id: str = Field(...)
    statement: str = Field(..., min_length=10)
    correct_answer: bool
    explanation: str = Field(..., min_length=10)
    difficulty: str = Field(default="easy", pattern=r'^(easy|medium|hard)$')
    learning_objective: Optional[str] = Field(default=None)
    points: int = Field(default=5, ge=1)


class FillBlankQuestion(BaseModel):
    """Fill in the blank question"""
    question_type: Literal["fill_blank"] = Field(default="fill_blank")
    question_id: str = Field(...)
    question_with_blank: str = Field(..., min_length=10)
    correct_answer: str = Field(...)
    acceptable_answers: List[str] = Field(default_factory=list)
    hint: Optional[str] = Field(default=None)
    difficulty: str = Field(default="medium", pattern=r'^(easy|medium|hard)$')
    learning_objective: Optional[str] = Field(default=None)
    points: int = Field(default=10, ge=1)


class TestCase(BaseModel):
    """Test case for coding question"""
    input: str = Field(...)
    expected_output: str = Field(...)


class CodingQuestion(BaseModel):
    """Coding question with test cases"""
    question_type: Literal["coding"] = Field(default="coding")
    question_id: str = Field(...)
    problem_statement: str = Field(..., min_length=20)
    starter_code: Optional[str] = Field(default=None)
    solution: str = Field(..., min_length=10)
    test_cases: List[TestCase] = Field(..., min_length=1)
    language: str = Field(default="python")
    difficulty: str = Field(default="medium", pattern=r'^(easy|medium|hard)$')
    learning_objective: Optional[str] = Field(default=None)
    points: int = Field(default=25, ge=1)


# Union type for all question types
QuizQuestion = Annotated[
    Union[MultipleChoiceQuestion, TrueFalseQuestion, FillBlankQuestion, CodingQuestion],
    Field(discriminator="question_type")
]


class ModuleAssessment(BaseModel):
    """Assessment for completing a module"""
    
    module_id: str = Field(...)
    title: str = Field(default="Module Assessment")
    passing_score: int = Field(default=70, ge=50, le=100)
    questions: List[QuizQuestion] = Field(..., min_length=3, max_length=20)


class FinalExam(BaseModel):
    """Final comprehensive exam"""
    
    title: str = Field(default="Final Exam")
    description: str = Field(default="Comprehensive course assessment")
    time_limit_minutes: int = Field(default=60, ge=15, le=180)
    passing_score: int = Field(default=70, ge=50, le=100)
    questions: List[QuizQuestion] = Field(..., min_length=10, max_length=50)
    weight_per_module: Dict[str, float] = Field(default_factory=dict)


class CourseAssessments(BaseModel):
    """All assessments for the course"""
    
    module_assessments: List[ModuleAssessment] = Field(default_factory=list)
    final_exam: Optional[FinalExam] = Field(default=None)


# ============================================================
# STEP 5: Quality Assurance Output
# ============================================================

class QualityLevel(str, Enum):
    """Quality assessment levels"""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    NEEDS_WORK = "needs_work"
    POOR = "poor"


class QualityIssue(BaseModel):
    """A quality issue found by QA Agent"""
    
    issue_id: str = Field(...)
    severity: str = Field(..., pattern=r'^(critical|major|minor)$')
    location: str = Field(..., description="e.g., lesson mod1_les2, assessment mod2_q3")
    description: str = Field(..., min_length=10)
    suggested_fix: Optional[str] = Field(default=None)
    regeneration_required: bool = Field(default=False)


class QualityCheck(BaseModel):
    """Single quality dimension check"""
    
    dimension: str = Field(..., description="accuracy, pedagogy, completeness, consistency, engagement, accessibility")
    score: int = Field(..., ge=0, le=100)
    level: QualityLevel
    issues_found: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class PriorityImprovement(BaseModel):
    """Priority improvement suggestion"""
    
    priority: int = Field(..., ge=1, le=10)
    improvement: str = Field(...)
    impact: str = Field(...)
    effort: str = Field(..., pattern=r'^(low|medium|high)$')


class QualityReport(BaseModel):
    """Quality assurance report from QA Agent"""
    
    quality_checks: List[QualityCheck] = Field(default_factory=list)
    critical_issues: List[QualityIssue] = Field(default_factory=list)
    overall_score: int = Field(..., ge=0, le=100)
    overall_level: QualityLevel = Field(default=QualityLevel.ACCEPTABLE)
    summary: str = Field(...)
    recommendation: str = Field(..., pattern=r'^(publish|publish_with_minor_fixes|fix_and_review|regenerate)$')
    priority_improvements: List[PriorityImprovement] = Field(default_factory=list)


# ============================================================
# COMPLETE COURSE OUTPUT
# ============================================================

class GeneratedCourse(BaseModel):
    """Complete generated course with all components"""
    
    course_id: str = Field(...)
    intent: CourseIntent
    curriculum: CurriculumStructure
    lessons: List[LessonContent]
    assessments: Optional[CourseAssessments] = Field(default=None)
    qa_report: Optional[QualityReport] = Field(default=None)
    
    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generation_duration_seconds: float = Field(default=0.0, ge=0)


# ============================================================
# HELPER SCHEMAS FOR API
# ============================================================

class CourseGenerationRequest(BaseModel):
    """API request to generate a new course"""
    
    prompt: str = Field(..., min_length=10, max_length=2000)
    difficulty: Optional[DifficultyLevel] = Field(default=None)
    max_duration_hours: Optional[int] = Field(default=None, ge=1, le=100)
    teaching_style: Optional[str] = Field(default="interactive")
    include_assessments: bool = Field(default=True)
    include_exercises: bool = Field(default=True)


class CourseGenerationStatus(BaseModel):
    """Status response for course generation job"""
    
    job_id: str
    status: str = Field(..., description="pending, running, completed, failed")
    progress_percent: int = Field(..., ge=0, le=100)
    current_step: str = Field(...)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    estimated_remaining_seconds: Optional[int] = Field(default=None)


class RegenerationRequest(BaseModel):
    """Request to regenerate a specific part of a course"""
    
    course_id: str
    target: str = Field(..., description="What to regenerate: lesson, module, quiz, etc.")
    target_id: str = Field(..., description="ID of the element to regenerate")
    feedback: Optional[str] = Field(default=None, description="User feedback for improvement")
