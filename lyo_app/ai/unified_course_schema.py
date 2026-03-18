"""
Unified Course Schema — single source of truth for course data across all pipelines.

Every course generation pipeline (A2A, Multi-Agent v2, Lyo 2.0 Executor) must
ultimately produce or convert to this representation.  Two thin output adapters
transform it into:

  - UIBlock dict  → returned to iOS / frontend clients
  - GraphCourse dict → stored in the ai_classroom DB tables

This eliminates the `translate_artifact_to_ui_component` hack in chat.py and
prevents schema drift between pipelines.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class UnifiedLesson(BaseModel):
    """A single lesson within a module."""
    title: str
    description: str = ""
    lesson_type: str = "reading"          # reading | video | quiz | exercise
    duration_minutes: int = 15
    content_blocks: List[Dict[str, Any]] = Field(default_factory=list)
    key_points: List[str] = Field(default_factory=list)
    quiz_questions: List[Dict[str, Any]] = Field(default_factory=list)


class UnifiedModule(BaseModel):
    """A group of lessons (chapter / unit)."""
    title: str
    description: str = ""
    lessons: List[UnifiedLesson] = Field(default_factory=list)

    @property
    def total_duration_minutes(self) -> int:
        return sum(l.duration_minutes for l in self.lessons)


class UnifiedCourse(BaseModel):
    """
    Canonical course representation shared by all pipelines.

    Build via factory methods:
        UnifiedCourse.from_a2a_artifacts(artifacts)
        UnifiedCourse.from_generated_course(generated_course)
        UnifiedCourse.from_executor_dict(executor_dict)

    Render via adapter methods:
        course.to_ui_block()          → dict for iOS/frontend
        course.to_graph_course_dict() → dict for ai_classroom DB
        course.to_chat_response_text() → human-readable summary string
    """

    course_id: str = ""
    title: str
    description: str = ""
    subject: str = ""
    difficulty: str = "intermediate"      # beginner | intermediate | advanced
    estimated_minutes: int = 60
    learning_objectives: List[str] = Field(default_factory=list)
    modules: List[UnifiedModule] = Field(default_factory=list)
    # Quality metadata (populated when available)
    qa_score: Optional[float] = None
    pipeline_used: str = "unknown"

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def total_lessons(self) -> int:
        return sum(len(m.lessons) for m in self.modules)

    @property
    def total_duration_minutes(self) -> int:
        return sum(m.total_duration_minutes for m in self.modules) or self.estimated_minutes

    # ------------------------------------------------------------------
    # Factory methods — convert from pipeline-specific formats
    # ------------------------------------------------------------------

    @classmethod
    def from_a2a_artifacts(cls, artifacts: list, topic: str = "") -> "UnifiedCourse":
        """
        Build a UnifiedCourse from the list of A2A Artifacts produced by
        A2AOrchestrator.generate_course().
        """
        from lyo_app.ai_agents.a2a.schemas import ArtifactType

        title = f"Learn {topic.title()}" if topic else "Generated Course"
        description = ""
        modules: List[UnifiedModule] = []
        objectives: List[str] = []

        for artifact in artifacts:
            if artifact.type == ArtifactType.CURRICULUM_STRUCTURE and artifact.data:
                data = artifact.data if isinstance(artifact.data, dict) else {}
                title = data.get("title", title)
                description = data.get("description", "")
                objectives = data.get("learning_objectives", objectives)
                for mod in data.get("modules", []):
                    lessons = [
                        UnifiedLesson(
                            title=les.get("title", "Lesson"),
                            description=les.get("description", ""),
                            lesson_type=les.get("type", "reading"),
                            duration_minutes=int(les.get("duration_minutes", 15)),
                        )
                        for les in mod.get("lessons", [])
                    ]
                    modules.append(UnifiedModule(
                        title=mod.get("title", "Module"),
                        description=mod.get("description", ""),
                        lessons=lessons,
                    ))

            elif artifact.type == ArtifactType.LEARNING_OBJECTIVES and artifact.data:
                data = artifact.data if isinstance(artifact.data, dict) else {}
                objectives = data.get("objectives", objectives) or objectives

            elif artifact.type == ArtifactType.ASSESSMENT and artifact.data:
                # Attach quiz questions to the last lesson of the last module
                if modules and modules[-1].lessons:
                    data = artifact.data if isinstance(artifact.data, dict) else {}
                    modules[-1].lessons[-1].quiz_questions = data.get("questions", [])

        return cls(
            title=title,
            description=description,
            subject=topic,
            learning_objectives=objectives,
            modules=modules,
            pipeline_used="a2a",
        )

    @classmethod
    def from_generated_course(cls, generated: Any) -> "UnifiedCourse":
        """
        Build a UnifiedCourse from a Multi-Agent v2 GeneratedCourse object.
        """
        try:
            curriculum = generated.curriculum
            title = getattr(curriculum, "title", "Generated Course")
            description = getattr(curriculum, "description", "")
            objectives = getattr(curriculum, "learning_objectives", [])
            difficulty = getattr(curriculum, "difficulty_level", "intermediate")
            if hasattr(difficulty, "value"):
                difficulty = difficulty.value

            modules: List[UnifiedModule] = []
            for mod in getattr(curriculum, "modules", []):
                # Collect lessons for this module from generated.lessons
                mod_lessons = []
                for lesson in getattr(generated, "lessons", []):
                    if getattr(lesson, "module_id", None) == getattr(mod, "id", None):
                        content_blocks = []
                        for block in getattr(lesson, "content_blocks", []):
                            content_blocks.append({
                                "type": getattr(block, "block_type", "text"),
                                "content": getattr(block, "content", ""),
                            })
                        quiz_qs = []
                        if hasattr(lesson, "practice_exercises"):
                            for ex in lesson.practice_exercises or []:
                                quiz_qs.append({
                                    "question": getattr(ex, "question", ""),
                                    "options": getattr(ex, "options", []),
                                    "correct_answer": getattr(ex, "correct_answer", ""),
                                })
                        mod_lessons.append(UnifiedLesson(
                            title=getattr(lesson, "title", "Lesson"),
                            description=getattr(lesson, "description", ""),
                            lesson_type=getattr(lesson, "lesson_type", "reading"),
                            duration_minutes=getattr(lesson, "estimated_duration_minutes", 15),
                            content_blocks=content_blocks,
                            key_points=getattr(lesson, "key_points", []),
                            quiz_questions=quiz_qs,
                        ))

                modules.append(UnifiedModule(
                    title=getattr(mod, "title", "Module"),
                    description=getattr(mod, "description", ""),
                    lessons=mod_lessons,
                ))

            qa_score = None
            if hasattr(generated, "qa_report") and generated.qa_report:
                qa_score = getattr(generated.qa_report, "overall_score", None)

            return cls(
                course_id=getattr(generated, "course_id", ""),
                title=title,
                description=description,
                subject=getattr(curriculum, "subject", ""),
                difficulty=str(difficulty),
                learning_objectives=objectives if isinstance(objectives, list) else [],
                modules=modules,
                qa_score=qa_score,
                pipeline_used="multi_agent_v2",
            )
        except Exception as e:
            logger.error(f"UnifiedCourse.from_generated_course failed: {e}")
            return cls(title="Generated Course", pipeline_used="multi_agent_v2")

    @classmethod
    def from_executor_dict(cls, data: Dict[str, Any]) -> "UnifiedCourse":
        """
        Build a UnifiedCourse from the freeform dict produced by Lyo 2.0 Executor
        (_generate_course_data return value).
        """
        lessons_raw = data.get("lessons", [])
        # Group all lessons into a single module (executor doesn't produce modules)
        lessons = [
            UnifiedLesson(
                title=les.get("title", "Lesson"),
                description=les.get("description", ""),
                lesson_type=les.get("type", "reading"),
                duration_minutes=int(les.get("duration", "15 min").split()[0]) if les.get("duration") else 15,
            )
            for les in lessons_raw
        ]
        module = UnifiedModule(
            title=data.get("title", "Course Content"),
            description=data.get("description", ""),
            lessons=lessons,
        )
        return cls(
            title=data.get("title", "Generated Course"),
            description=data.get("description", ""),
            subject=data.get("topic", data.get("subject", "")),
            difficulty=data.get("difficulty", "intermediate"),
            learning_objectives=data.get("objectives", []),
            modules=[module] if lessons else [],
            pipeline_used="executor",
        )

    # ------------------------------------------------------------------
    # Output adapters — render to downstream formats
    # ------------------------------------------------------------------

    def to_ui_block(self) -> Dict[str, Any]:
        """
        Render as an iOS/frontend UI component dict (course_roadmap type).

        Replaces translate_artifact_to_ui_component() for the
        CURRICULUM_STRUCTURE artifact type.
        """
        formatted_modules = []
        for mod in self.modules:
            formatted_modules.append({
                "title": mod.title,
                "description": mod.description,
                "lessons": [
                    {
                        "title": les.title,
                        "duration": f"{les.duration_minutes} min",
                        "type": les.lesson_type,
                    }
                    for les in mod.lessons
                ],
            })

        return {
            "type": "course_roadmap",
            "course_roadmap": {
                "course_id": self.course_id,
                "title": self.title,
                "topic": self.subject or self.title,
                "level": self.difficulty,
                "description": self.description,
                "estimated_minutes": self.total_duration_minutes,
                "learning_objectives": self.learning_objectives,
                "modules": formatted_modules,
            },
        }

    def to_graph_course_dict(self) -> Dict[str, Any]:
        """
        Render as a dict compatible with ai_classroom GraphCourse storage.

        Each lesson becomes a LearningNode candidate; modules become
        grouping metadata.
        """
        nodes = []
        sequence = 0
        for mod_idx, mod in enumerate(self.modules):
            for les_idx, les in enumerate(mod.lessons):
                sequence += 1
                nodes.append({
                    "sequence_order": sequence,
                    "node_type": les.lesson_type,
                    "title": les.title,
                    "module_title": mod.title,
                    "module_index": mod_idx,
                    "content": {
                        "title": les.title,
                        "description": les.description,
                        "key_points": les.key_points,
                        "content_blocks": les.content_blocks,
                        "quiz_questions": les.quiz_questions,
                        "narration": les.description,
                    },
                    "estimated_duration_minutes": les.duration_minutes,
                })

        return {
            "course_id": self.course_id,
            "title": self.title,
            "description": self.description,
            "subject": self.subject,
            "difficulty": self.difficulty,
            "estimated_minutes": self.total_duration_minutes,
            "learning_objectives": self.learning_objectives,
            "total_nodes": len(nodes),
            "nodes": nodes,
        }

    def to_chat_response_text(self) -> str:
        """Produce a human-readable chat message summarising the course."""
        lesson_count = self.total_lessons
        duration = self.total_duration_minutes
        hours = duration // 60
        mins = duration % 60
        time_str = f"{hours}h {mins}m" if hours else f"{mins} min"

        lines = [
            f"🎓 **Course Created: {self.title}**",
            "",
            self.description or f"A comprehensive course covering {self.subject or self.title}.",
            "",
            f"📚 **{len(self.modules)} modules** · **{lesson_count} lessons** · ⏱ {time_str}",
        ]
        if self.learning_objectives:
            lines += ["", "**What you'll learn:**"]
            lines += [f"• {obj}" for obj in self.learning_objectives[:4]]

        lines += ["", "✨ *Tap below to start your personalised learning journey*"]
        return "\n".join(lines)
