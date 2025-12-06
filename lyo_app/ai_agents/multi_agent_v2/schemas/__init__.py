# Multi-Agent Course Creation Schemas
from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import (
    # Enums
    DifficultyLevel,
    ContentBlockType,
    QuestionType,
    LessonType,
    TeachingStyle,
    QualityLevel,
    
    # Step 1: Intent
    CourseIntent,
    
    # Step 2: Curriculum
    LessonOutline,
    ModuleOutline,
    CurriculumStructure,
    
    # Step 3: Content
    TextBlock,
    CodeBlock,
    ExerciseBlock,
    MediaBlock,
    ContentBlock,
    LessonContent,
    
    # Step 4: Assessments
    QuestionOption,
    MultipleChoiceQuestion,
    TrueFalseQuestion,
    FillBlankQuestion,
    TestCase,
    CodingQuestion,
    QuizQuestion,
    ModuleAssessment,
    FinalExam,
    CourseAssessments,
    
    # Step 5: QA
    QualityIssue,
    QualityCheck,
    PriorityImprovement,
    QualityReport,
    
    # Complete Course
    GeneratedCourse,
    
    # API Helpers
    CourseGenerationRequest,
    CourseGenerationStatus,
    RegenerationRequest,
)

__all__ = [
    # Enums
    "DifficultyLevel",
    "ContentBlockType",
    "QuestionType",
    "LessonType",
    "TeachingStyle",
    "QualityLevel",
    
    # Step 1: Intent
    "CourseIntent",
    
    # Step 2: Curriculum
    "LessonOutline",
    "ModuleOutline",
    "CurriculumStructure",
    
    # Step 3: Content
    "TextBlock",
    "CodeBlock",
    "ExerciseBlock",
    "MediaBlock",
    "ContentBlock",
    "LessonContent",
    
    # Step 4: Assessments
    "QuestionOption",
    "MultipleChoiceQuestion",
    "TrueFalseQuestion",
    "FillBlankQuestion",
    "TestCase",
    "CodingQuestion",
    "QuizQuestion",
    "ModuleAssessment",
    "FinalExam",
    "CourseAssessments",
    
    # Step 5: QA
    "QualityIssue",
    "QualityCheck",
    "PriorityImprovement",
    "QualityReport",
    
    # Complete Course
    "GeneratedCourse",
    
    # API Helpers
    "CourseGenerationRequest",
    "CourseGenerationStatus",
    "RegenerationRequest",
]
