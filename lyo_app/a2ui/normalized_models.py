"""
A2UI Normalized Models — Validated intermediary between raw LLM output and A2UI rendering.
Every field has a default. No field is ever None without a fallback.
These models CANNOT fail to construct — they always produce valid structures.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from uuid import uuid4


@dataclass
class NormalizedQuizOption:
    text: str = ""
    is_correct: bool = False


@dataclass
class NormalizedQuiz:
    question: str = "Question"
    options: List[NormalizedQuizOption] = field(default_factory=lambda: [
        NormalizedQuizOption(text="Option A", is_correct=True),
        NormalizedQuizOption(text="Option B"),
    ])
    explanation: str = ""
    quiz_type: str = "mcq"  # mcq, true_false, fill_blank


@dataclass
class NormalizedLesson:
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = "Untitled Lesson"
    content: str = ""           # raw markdown or text
    description: str = ""
    lesson_type: str = "reading"  # reading, exercise, quiz
    quiz: Optional[NormalizedQuiz] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    duration_minutes: int = 10
    order: int = 0


@dataclass
class NormalizedModule:
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = "Module"
    description: str = ""
    lessons: List[NormalizedLesson] = field(default_factory=list)
    order: int = 0


@dataclass
class NormalizedCourse:
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = "Your Course"
    topic: str = ""
    description: str = ""
    modules: List[NormalizedModule] = field(default_factory=list)
    objectives: List[str] = field(default_factory=list)
    difficulty: str = "Beginner"
    duration: str = "~30 min"
    quality_score: Optional[float] = None

    @property
    def total_lessons(self) -> int:
        return sum(len(m.lessons) for m in self.modules)

    @property
    def flat_lessons(self) -> List[NormalizedLesson]:
        """All lessons across all modules, flattened."""
        lessons = []
        for module in self.modules:
            lessons.extend(module.lessons)
        return lessons


@dataclass
class NormalizedExplanation:
    topic: str = "Topic"
    content: str = ""  # markdown text
    key_points: List[str] = field(default_factory=list)
    related_topics: List[str] = field(default_factory=list)


@dataclass
class NormalizedStudyPlan:
    title: str = "Study Plan"
    description: str = ""
    milestones: List[str] = field(default_factory=list)
    duration: str = "2 weeks"
    daily_minutes: int = 30
