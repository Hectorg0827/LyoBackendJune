"""
Lyo Course Schemas (v2)
Defines the structure for AI-generated courses, matching LyoCourseProtocol.swift.
"""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum

# MARK: - Enums

class ArtifactType(str, Enum):
    CONCEPT_EXPLAINER = "concept_explainer"
    NOTES = "notes"
    FLASHCARDS = "flashcards"
    QUIZ = "quiz"
    PROBLEM_SET = "problem_set"
    READING = "reading"

class RenderTarget(str, Enum):
    NATIVE = "native"
    CINEMATIC = "cinematic"
    EXTERNAL = "external"

# MARK: - Artifact Payloads

class ConceptExplainerPayload(BaseModel):
    markdown: str
    hook: Optional[str] = None
    visual_prompt: Optional[str] = None
    key_takeaways: List[str] = []

class Flashcard(BaseModel):
    front: str
    back: str
    hint: Optional[str] = None

class FlashcardsPayload(BaseModel):
    topic: str
    cards: List[Flashcard]

class QuizOption(BaseModel):
    id: str
    text: str

class QuizQuestion(BaseModel):
    id: str
    text: str
    type: str = "single_choice" # single_choice, multiple_choice, true_false
    options: List[QuizOption]
    correct_option_id: str
    explanation: Optional[str] = None

class QuizArtifactPayload(BaseModel):
    questions: List[QuizQuestion]

class NoteSection(BaseModel):
    title: str
    content: str
    is_callout: bool = False

class NotesPayload(BaseModel):
    title: str
    sections: List[NoteSection]

class ReadingPayload(BaseModel):
    title: str
    content: str
    read_time: int
    source_url: Optional[str] = None

# MARK: - Core Artifact Model

class ArtifactAIMetadata(BaseModel):
    generated_by: str = "LyoAI"
    confidence: float
    reasoning: Optional[str] = None

class LyoArtifact(BaseModel):
    artifact_id: str
    type: ArtifactType
    render_target: RenderTarget = RenderTarget.NATIVE
    content: Dict[str, Any] # Contains one of the payloads above
    ai_metadata: Optional[ArtifactAIMetadata] = None

# MARK: - Hierarchy Models

class LyoLesson(BaseModel):
    lesson_id: str
    title: str
    goal: str
    artifacts: List[LyoArtifact]
    duration_minutes: int

class LyoModule(BaseModel):
    module_id: str
    title: str
    goal: str
    lessons: List[LyoLesson]

class LyoCourse(BaseModel):
    course_id: str
    title: str
    target_audience: str
    learning_objectives: List[str]
    modules: List[LyoModule]
    generation_source: str = "ai"
    version: str = "1.0"
    metadata: Optional[Dict[str, str]] = None
