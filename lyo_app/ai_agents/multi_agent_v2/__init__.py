"""
Multi-Agent Course Creation System v2 - MIT Architecture Engineering

This module provides a production-grade multi-agent system for AI-powered
course generation. It implements a deterministic pipeline architecture with:

- Specialized agents for each step (Orchestrator, Curriculum, Content, Assessment, QA)
- Validation gates between steps (non-AI, deterministic)
- Job persistence and resume capability
- Parallel lesson generation
- Automatic retry with fallback prompts
- Granular regeneration of failed components

## Architecture Overview

```
User Request
    │
    ▼
┌─────────────────────┐
│ Orchestrator Agent  │ → CourseIntent
└─────────────────────┘
    │
    ▼ Gate 1: Validate Intent
    │
┌─────────────────────┐
│ Curriculum Architect│ → CurriculumStructure
└─────────────────────┘
    │
    ▼ Gate 2: Validate Curriculum
    │
┌─────────────────────┐
│ Content Creator     │ → LessonContent[] (parallel)
│ (3 concurrent max)  │
└─────────────────────┘
    │
    ▼ Gate 3: Validate Content
    │
┌─────────────────────┐
│ Assessment Designer │ → CourseAssessments
└─────────────────────┘
    │
    ▼ Gate 4: Validate Assessments
    │
┌─────────────────────┐
│ QA Agent            │ → QualityReport
└─────────────────────┘
    │
    ▼ Gate 5: Validate QA
    │
┌─────────────────────┐
│ Finalize            │ → GeneratedCourse
└─────────────────────┘
```

## Usage

```python
from lyo_app.ai_agents.multi_agent_v2 import (
    CourseGenerationPipeline, 
    PipelineConfig
)

# Initialize pipeline
pipeline = CourseGenerationPipeline(
    config=PipelineConfig(
        max_retries_per_step=3,
        parallel_lesson_batch_size=3,
        qa_min_score=60
    )
)

# Generate a course
course = await pipeline.generate_course(
    user_request="Create a comprehensive Python programming course for beginners",
    user_context={
        "skill_level": "beginner",
        "learning_style": "hands-on"
    }
)

# Access results
print(f"Course: {course.curriculum.title}")
print(f"Modules: {course.curriculum.module_count}")
print(f"Lessons: {course.curriculum.lesson_count}")
print(f"QA Score: {course.qa_report.overall_score}")
```

## Key Features

1. **Deterministic Pipeline**: Non-AI gates validate each step before proceeding
2. **Fail-Proof**: Automatic retry, fallback prompts, granular regeneration
3. **Persistent**: Job queue stores progress for resume capability
4. **Parallel**: Content generation runs concurrently for speed
5. **Quality Assured**: QA agent reviews everything before finalization
6. **Typed**: Full Pydantic schema validation throughout
"""

# Schemas
from lyo_app.ai_agents.multi_agent_v2.schemas import (
    # Core schemas
    CourseIntent,
    CurriculumStructure,
    ModuleOutline,
    LessonOutline,
    LessonContent,
    CourseAssessments,
    QualityReport,
    GeneratedCourse,
    
    # Enums
    DifficultyLevel,
    LessonType,
    TeachingStyle,
    QualityLevel,
    
    # Content blocks
    ContentBlock,
    TextBlock,
    CodeBlock,
    ExerciseBlock,
    MediaBlock,
    
    # Questions
    QuizQuestion,
    MultipleChoiceQuestion,
    TrueFalseQuestion,
    FillBlankQuestion,
    CodingQuestion
)

# Agents
from lyo_app.ai_agents.multi_agent_v2.agents import (
    BaseAgent,
    AgentMetrics,
    OrchestratorAgent,
    CurriculumArchitectAgent,
    ContentCreatorAgent,
    AssessmentDesignerAgent,
    QualityAssuranceAgent,
    LessonGenerationContext,
    ReviewFocus,
    QAContext,
    # Model Management
    ModelManager,
    ModelConfig,
    ModelTier,
    QualityTier,
    TaskComplexity
)

# Pipeline
from lyo_app.ai_agents.multi_agent_v2.pipeline import (
    CourseGenerationPipeline,
    PipelineConfig,
    PipelineState,
    PipelineStep,
    StepResult,
    PipelineError,
    JobManager,
    JobStatus,
    CourseGenerationJob,
    PipelineGates,
    GateResult
)

__all__ = [
    # Schemas
    "CourseIntent",
    "CurriculumStructure", 
    "ModuleOutline",
    "LessonOutline",
    "LessonContent",
    "CourseAssessments",
    "QualityReport",
    "GeneratedCourse",
    "DifficultyLevel",
    "LessonType",
    "TeachingStyle",
    "QualityLevel",
    "ContentBlock",
    "TextBlock",
    "CodeBlock",
    "ExerciseBlock",
    "MediaBlock",
    "QuizQuestion",
    "MultipleChoiceQuestion",
    "TrueFalseQuestion",
    "FillBlankQuestion",
    "CodingQuestion",
    
    # Agents
    "BaseAgent",
    "AgentMetrics",
    "OrchestratorAgent",
    "CurriculumArchitectAgent",
    "ContentCreatorAgent",
    "AssessmentDesignerAgent",
    "QualityAssuranceAgent",
    "LessonGenerationContext",
    "ReviewFocus",
    "QAContext",
    
    # Model Management
    "ModelManager",
    "ModelConfig",
    "ModelTier",
    "QualityTier",
    "TaskComplexity",
    
    # Pipeline
    "CourseGenerationPipeline",
    "PipelineConfig",
    "PipelineState",
    "PipelineStep",
    "StepResult",
    "PipelineError",
    "JobManager",
    "JobStatus",
    "CourseGenerationJob",
    "PipelineGates",
    "GateResult"
]

__version__ = "2.1.0"  # Updated for multi-model support
