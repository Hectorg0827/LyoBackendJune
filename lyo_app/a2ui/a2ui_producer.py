"""
A2UI Producer — The Single Chokepoint

Every path from agents/LLM to iOS MUST pass through this layer.
It converts chaotic LLM output into deterministic A2UIComponent trees.

Architecture:
  LLM (chaotic) → A2UIProducer (deterministic) → iOS (renders)
                   ├── ContentExtractor (parse what you can, fallback the rest)
                   ├── ContentValidator (defaults for every field, never raises)
                   └── ComponentRenderer (maps validated data → A2UI, never fails)

The producer is:
- Sub-millisecond (pure Python, no LLM calls)
- Unfailable (every code path ends in a valid A2UIComponent)
- The ONLY place that creates A2UI from LLM output
"""

import logging
from typing import Any, Dict, Optional, List
from uuid import uuid4

from lyo_app.a2ui.models import A2UIComponent, A2UIElementType, A2UIProps
from lyo_app.a2ui.a2ui_generator import A2UIGenerator
from lyo_app.a2ui.classroom_generator import ClassroomA2UIGenerator
from lyo_app.a2ui.normalized_models import (
    NormalizedCourse,
    NormalizedLesson,
    NormalizedModule,
    NormalizedExplanation,
    NormalizedQuiz,
    NormalizedStudyPlan,
)
from lyo_app.a2ui.extractors import (
    extract_course,
    extract_explanation,
    extract_quiz,
    extract_study_plan,
)

logger = logging.getLogger(__name__)


class A2UIProducer:
    """
    The single chokepoint between chaotic LLM output and deterministic A2UI.
    
    Every produce_* method:
    1. Extracts structured data from raw input (try/except cascade)
    2. Validates all fields have defaults (never None)
    3. Renders to A2UIComponent tree (pure Python, sub-ms)
    4. Falls back to error UI on ANY failure
    """

    def __init__(self):
        self.gen = A2UIGenerator()
        self.classroom = ClassroomA2UIGenerator()

    # ──────────────────────────────────────────────────────────
    # Course Production
    # ──────────────────────────────────────────────────────────

    def produce_course(self, raw: Any, topic: str = "") -> Dict[str, Any]:
        """
        Produce both:
        1. An A2UI component tree (rich card) for immediate rendering
        2. An iOS-compatible open_classroom payload for course proposal
        
        Returns: {
            "a2ui_component": A2UIComponent,      # renderable UI tree
            "open_classroom": { ... },             # iOS CoursePayload-compatible dict
        }
        """
        try:
            course = extract_course(raw, fallback_topic=topic or "Your Course")
            a2ui = self._render_course_card(course)
            ios_payload = self._course_to_ios_payload(course)
            return {
                "a2ui_component": a2ui,
                "open_classroom": ios_payload,
            }
        except Exception as e:
            logger.error(f"[A2UIProducer] produce_course failed: {e}", exc_info=True)
            return {
                "a2ui_component": self.produce_error("Course generation encountered an issue"),
                "open_classroom": {
                    "course": {
                        "id": str(uuid4()),
                        "title": topic or "Course",
                        "topic": topic or "General",
                        "level": "Beginner",
                        "duration": "~30 min",
                        "objectives": [],
                    }
                },
            }

    def produce_course_a2ui_only(self, raw: Any, topic: str = "") -> A2UIComponent:
        """Produce only the A2UI component for a course (no open_classroom trigger)."""
        try:
            course = extract_course(raw, fallback_topic=topic)
            return self._render_course_card(course)
        except Exception as e:
            logger.error(f"[A2UIProducer] produce_course_a2ui_only failed: {e}", exc_info=True)
            return self.produce_error("Course display unavailable")

    # ──────────────────────────────────────────────────────────
    # Lesson Production (for progressive streaming)
    # ──────────────────────────────────────────────────────────

    def produce_lesson(self, raw: Any, index: int = 0, total: int = 1) -> A2UIComponent:
        """Produce a full lesson UI using the classroom generator."""
        try:
            if isinstance(raw, NormalizedLesson):
                lesson = raw
            elif isinstance(raw, dict):
                from lyo_app.a2ui.extractors import _extract_lesson
                lesson = _extract_lesson(raw, index)
            else:
                lesson = NormalizedLesson(title=f"Lesson {index + 1}", content=str(raw))

            return self.classroom.generate_lesson_ui(
                lesson_title=lesson.title,
                lesson_content=lesson.content or lesson.description,
                module_title="",
                lesson_number=index + 1,
                total_lessons=total,
                has_next=(index < total - 1),
                has_previous=(index > 0),
            )
        except Exception as e:
            logger.error(f"[A2UIProducer] produce_lesson failed: {e}", exc_info=True)
            return self.produce_error(f"Lesson {index + 1} is loading...")

    # ──────────────────────────────────────────────────────────
    # Explanation Production
    # ──────────────────────────────────────────────────────────

    def produce_explanation(self, raw: Any, topic: str = "") -> A2UIComponent:
        """Produce an explanation UI with content, key points, and action buttons."""
        try:
            explanation = extract_explanation(raw, fallback_topic=topic)
            return self._render_explanation(explanation)
        except Exception as e:
            logger.error(f"[A2UIProducer] produce_explanation failed: {e}", exc_info=True)
            return self.produce_error("Explanation unavailable")

    # ──────────────────────────────────────────────────────────
    # Quiz Production
    # ──────────────────────────────────────────────────────────

    def produce_quiz(self, raw: Any) -> A2UIComponent:
        """Produce a quiz UI component."""
        try:
            quiz = extract_quiz(raw)
            return self._render_quiz(quiz)
        except Exception as e:
            logger.error(f"[A2UIProducer] produce_quiz failed: {e}", exc_info=True)
            return self.produce_error("Quiz unavailable")

    # ──────────────────────────────────────────────────────────
    # Study Plan Production
    # ──────────────────────────────────────────────────────────

    def produce_study_plan(self, raw: Any, topic: str = "") -> A2UIComponent:
        """Produce a study plan UI component."""
        try:
            plan = extract_study_plan(raw, fallback_topic=topic)
            return self._render_study_plan(plan)
        except Exception as e:
            logger.error(f"[A2UIProducer] produce_study_plan failed: {e}", exc_info=True)
            return self.produce_error("Study plan unavailable")

    # ──────────────────────────────────────────────────────────
    # Skeleton / Loading / Error
    # ──────────────────────────────────────────────────────────

    def produce_skeleton(self, topic: str = "") -> A2UIComponent:
        """Produce a loading skeleton UI — shown at time 0."""
        return self.gen.vstack([
            self.gen.text(
                content=f"✨ Preparing: {topic}" if topic else "✨ Preparing your content...",
                font_size=18,
                font_weight="semibold",
                color="#FFFFFF",
            ),
            self.gen.text(
                content="This will just take a moment",
                font_size=14,
                color="#AAAAAA",
            ),
            A2UIComponent(
                type=A2UIElementType.SKELETON,
                props=A2UIProps(text="Loading...", stream_id="skeleton_main"),
            ),
        ], spacing=12, padding_horizontal=20, padding_vertical=20)

    def produce_error(self, message: str = "Something went wrong") -> A2UIComponent:
        """Produce a friendly error UI. NEVER fails."""
        try:
            return self.gen.vstack([
                self.gen.text(
                    content="⚠️",
                    font_size=32,
                    alignment="center",
                ),
                self.gen.text(
                    content=message,
                    font_size=16,
                    color="#FF6B6B",
                    alignment="center",
                ),
                self.gen.button(
                    title="Try Again",
                    action="retry",
                    style="primary",
                ),
            ], spacing=16, padding_horizontal=20, padding_vertical=24)
        except Exception:
            # Nuclear fallback — if even the generator fails
            return A2UIComponent(
                type=A2UIElementType.TEXT,
                props=A2UIProps(text=message),
            )

    # ──────────────────────────────────────────────────────────
    # Generic Producer (auto-detect content type)
    # ──────────────────────────────────────────────────────────

    def produce_auto(self, raw: Any, ui_type: str = "explanation", topic: str = "") -> A2UIComponent:
        """
        Auto-detect content type and produce the appropriate A2UI.
        The universal entry point for when you don't know the exact type.
        """
        dispatch = {
            "course": lambda: self.produce_course_a2ui_only(raw, topic),
            "quiz": lambda: self.produce_quiz(raw),
            "study_plan": lambda: self.produce_study_plan(raw, topic),
            "explanation": lambda: self.produce_explanation(raw, topic),
        }
        producer_fn = dispatch.get(ui_type, dispatch["explanation"])
        try:
            return producer_fn()
        except Exception as e:
            logger.error(f"[A2UIProducer] produce_auto failed for {ui_type}: {e}")
            return self.produce_error(f"Content unavailable")

    # ══════════════════════════════════════════════════════════
    # PRIVATE RENDERERS — pure Python, no LLM, sub-ms
    # ══════════════════════════════════════════════════════════

    def _render_course_card(self, course: NormalizedCourse) -> A2UIComponent:
        """Render a course overview card with stats and lesson list."""
        children = []

        # Header
        children.append(self.gen.text(
            content=f"📚 {course.title}",
            font_size=22,
            font_weight="bold",
            color="#FFFFFF",
        ))

        if course.description:
            children.append(self.gen.text(
                content=course.description,
                font_size=14,
                color="#CCCCCC",
            ))

        # Stats row
        stats = self.gen.hstack([
            self._stat_pill("📖", f"{course.total_lessons} lessons"),
            self._stat_pill("⏱", course.duration),
            self._stat_pill("📊", course.difficulty),
        ], spacing=8)
        children.append(stats)

        # Objectives
        if course.objectives:
            obj_items = []
            obj_items.append(self.gen.text(
                content="Learning Objectives",
                font_size=16,
                font_weight="semibold",
                color="#FFFFFF",
            ))
            for obj in course.objectives[:5]:
                obj_items.append(self.gen.text(
                    content=f"✓ {obj}",
                    font_size=14,
                    color="#AADDAA",
                ))
            children.append(self.gen.vstack(obj_items, spacing=6))

        # Lesson list (first 6)
        flat_lessons = course.flat_lessons[:6]
        if flat_lessons:
            lesson_items = []
            lesson_items.append(self.gen.text(
                content="Lessons",
                font_size=16,
                font_weight="semibold",
                color="#FFFFFF",
            ))
            for i, lesson in enumerate(flat_lessons):
                lesson_items.append(self.gen.hstack([
                    self.gen.text(content=f"{i + 1}.", font_size=14, color="#888888"),
                    self.gen.text(content=lesson.title, font_size=14, color="#FFFFFF"),
                    self.gen.text(content=f"{lesson.duration_minutes}m", font_size=12, color="#888888"),
                ], spacing=8))
            children.append(self.gen.vstack(lesson_items, spacing=4))

        # Action buttons
        children.append(self.gen.hstack([
            self.gen.button(title="🚀 Start Learning", action="start_course", style="primary"),
            self.gen.button(title="Customize", action="customize_course", style="secondary"),
        ], spacing=12))

        inner = self.gen.vstack(children, spacing=16, padding_horizontal=20, padding_vertical=20)
        return A2UIComponent(type=A2UIElementType.CARD, props=A2UIProps(intent="open_classroom"), children=[inner])

    def _render_explanation(self, explanation: NormalizedExplanation) -> A2UIComponent:
        """Render an explanation with content, key points, and actions."""
        children = []

        # Topic header
        children.append(self.gen.text(
            content=f"💡 {explanation.topic}",
            font_size=20,
            font_weight="bold",
            color="#FFFFFF",
        ))

        # Content (rendered as markdown)
        if explanation.content:
            # Use the classroom generator's content parser for rich rendering
            content_blocks = self.classroom._parse_content_to_blocks(explanation.content)
            children.extend(content_blocks)

        # Key points
        if explanation.key_points:
            children.append(self.gen.text(
                content="Key Points",
                font_size=16,
                font_weight="semibold",
                color="#FFFFFF",
            ))
            for point in explanation.key_points[:5]:
                children.append(self.gen.text(
                    content=f"• {point}",
                    font_size=14,
                    color="#CCCCCC",
                ))

        # Action buttons
        children.append(self.gen.hstack([
            self.gen.button(title="📚 Create Course", action="create_course_from_topic", style="primary"),
            self.gen.button(title="🧠 Quiz Me", action="quiz_on_topic", style="secondary"),
            self.gen.button(title="🔍 Deep Dive", action="deep_dive", style="secondary"),
        ], spacing=8))

        inner = self.gen.vstack(children, spacing=14, padding_horizontal=16, padding_vertical=16)
        return A2UIComponent(type=A2UIElementType.CARD, props=A2UIProps(), children=[inner])

    def _render_quiz(self, quiz: NormalizedQuiz) -> A2UIComponent:
        """Render a quiz component."""
        children = []

        children.append(self.gen.text(
            content="🧠 Quiz",
            font_size=18,
            font_weight="bold",
            color="#FFFFFF",
        ))

        # Question
        children.append(self.gen.text(
            content=quiz.question,
            font_size=16,
            color="#FFFFFF",
        ))

        # Options as buttons
        option_buttons = []
        for i, opt in enumerate(quiz.options):
            option_buttons.append(self.gen.button(
                title=f"{chr(65 + i)}. {opt.text}",
                action=f"quiz_answer_{i}",
                style="outline",
            ))

        children.append(self.gen.vstack(option_buttons, spacing=8))

        inner = self.gen.vstack(children, spacing=12, padding_horizontal=16, padding_vertical=16)
        return A2UIComponent(type=A2UIElementType.CARD, props=A2UIProps(), children=[inner])

    def _render_study_plan(self, plan: NormalizedStudyPlan) -> A2UIComponent:
        """Render a study plan component."""
        children = []

        children.append(self.gen.text(
            content=f"📋 {plan.title}",
            font_size=20,
            font_weight="bold",
            color="#FFFFFF",
        ))

        if plan.description:
            children.append(self.gen.text(
                content=plan.description,
                font_size=14,
                color="#CCCCCC",
            ))

        # Stats
        children.append(self.gen.hstack([
            self._stat_pill("📅", plan.duration),
            self._stat_pill("⏰", f"{plan.daily_minutes} min/day"),
        ], spacing=8))

        # Milestones
        if plan.milestones:
            for i, milestone in enumerate(plan.milestones[:8]):
                children.append(self.gen.hstack([
                    self.gen.text(content=f"{'☑' if i == 0 else '☐'}", font_size=14, color="#888888"),
                    self.gen.text(content=str(milestone), font_size=14, color="#FFFFFF"),
                ], spacing=8))

        children.append(self.gen.button(
            title="📚 Start Studying",
            action="start_study_plan",
            style="primary",
        ))

        inner = self.gen.vstack(children, spacing=10, padding_horizontal=16, padding_vertical=16)
        return A2UIComponent(type=A2UIElementType.CARD, props=A2UIProps(), children=[inner])

    def _stat_pill(self, emoji: str, text: str) -> A2UIComponent:
        """Small pill-shaped stat indicator."""
        return self.gen.hstack([
            self.gen.text(content=emoji, font_size=12),
            self.gen.text(content=text, font_size=12, color="#AAAAAA"),
        ], spacing=4)

    def _course_to_ios_payload(self, course: NormalizedCourse) -> Dict[str, Any]:
        """
        Convert NormalizedCourse to iOS CoursePayload-compatible dict.
        
        iOS expects: {"course": {"id", "title", "topic", "level", "duration", "objectives"}}
        The "course" wrapper key is critical — tryDecodeOpenClassroom looks for it.
        """
        return {
            "course": {
                "id": course.id,
                "title": course.title,
                "topic": course.topic,
                "level": course.difficulty,
                "duration": course.duration,
                "objectives": course.objectives[:6],  # iOS displays max 6
                "thumbnail": course.thumbnail,
            }
        }


# Module-level singleton
a2ui_producer = A2UIProducer()
