"""
A2UI Compiler — v2 Thin Deterministic Layer

Replaces the role of A2UIProducer for v2 output.
Converts normalized models → 22-primitive component trees with semantic variants.

Architecture:
  NormalizedModel → A2UICompiler → A2UIComponent (with variant set)
                                    ↓
                    iOS v2 bridge → LyoUIComponent → LyoPrimitiveRenderer

The compiler is:
- Sub-millisecond (pure Python, no LLM calls)
- Unfailable (every code path ends in a valid component)
- Uses the 22-primitive vocabulary with variants
- Sets `variant` field on every component (enables iOS v2 renderer routing)

Primitives (22):
  text, media, divider, input, button,
  container, card, list, nav,
  quiz, quizResult, course, flashcard, plan, tracker, assignment, document,
  progress, aiBubble, social, alert, skeleton
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from lyo_app.a2ui.models import (
    A2UIComponent,
    A2UIElementType,
    A2UIProps,
    A2UIAction,
    A2UIMetadata,
)
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
from lyo_app.ai.schemas.lyo2_v2 import (
    validate_lyo_response,
    validate_lyo_component,
    get_lyo_response_json_schema,
    LyoResponseSchema,
    LyoUIComponentSchema,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Primitive type mapping (A2UIElementType → v2 primitive name)
# iOS reads component.variant to decide v2 rendering.
# ══════════════════════════════════════════════════════════════

_PRIM_TEXT = "text"
_PRIM_CARD = "card"
_PRIM_VSTACK = "container"
_PRIM_HSTACK = "container"
_PRIM_BUTTON = "button"
_PRIM_DIVIDER = "divider"
_PRIM_SKELETON = "skeleton"
_PRIM_QUIZ = "quiz"
_PRIM_PROGRESS = "progress"


class A2UICompiler:
    """
    v2 compiler: converts normalized models to A2UIComponent trees
    with semantic `variant` fields set on every node.

    The variant field is what triggers iOS v2 rendering path:
      A2UIRenderer.renderRoot() checks `component.variant != nil`
      → converts via LyoUIComponent.from(legacy:) → LyoPrimitiveRenderer
    """

    # ──────────────────────────────────────────────────────────
    # Primitive helpers — every node gets a variant
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _text(content: str, variant: str = "plain", **kwargs) -> A2UIComponent:
        """Create a text primitive with variant."""
        props = A2UIProps(text=content, **kwargs)
        return A2UIComponent(type=_PRIM_TEXT, variant=variant, props=props)

    @staticmethod
    def _heading(content: str, level: int = 1, **kwargs) -> A2UIComponent:
        """Create a heading text (variant=heading)."""
        size = {1: 24, 2: 20, 3: 18}.get(level, 16)
        props = A2UIProps(
            text=content,
            font_size=size,
            font_weight="bold",
            foreground_color=kwargs.pop("color", "#FFFFFF"),
            **kwargs,
        )
        return A2UIComponent(type=_PRIM_TEXT, variant="heading", props=props)

    @staticmethod
    def _markdown(content: str, **kwargs) -> A2UIComponent:
        """Create a markdown text primitive."""
        props = A2UIProps(text=content, **kwargs)
        return A2UIComponent(type=_PRIM_TEXT, variant="markdown", props=props)

    @staticmethod
    def _button(label: str, action: str, variant: str = "primary", **kwargs) -> A2UIComponent:
        """Create a button primitive."""
        props = A2UIProps(label=label, action_id=action, variant=variant, **kwargs)
        return A2UIComponent(type=_PRIM_BUTTON, variant=variant, props=props)

    @staticmethod
    def _card(children: List[A2UIComponent], variant: str = "default", **kwargs) -> A2UIComponent:
        """Create a card primitive wrapping children."""
        props = A2UIProps(**kwargs)
        return A2UIComponent(type=_PRIM_CARD, variant=variant, props=props, children=children)

    @staticmethod
    def _container(
        children: List[A2UIComponent],
        variant: str = "stack",
        axis: str = "vertical",
        spacing: float = 12,
        **kwargs,
    ) -> A2UIComponent:
        """Create a container primitive (stack/grid/scroll/section)."""
        el_type = _PRIM_VSTACK if axis == "vertical" else _PRIM_HSTACK
        props = A2UIProps(spacing=spacing, **kwargs)
        return A2UIComponent(type=el_type, variant=variant, props=props, children=children)

    @staticmethod
    def _divider(**kwargs) -> A2UIComponent:
        props = A2UIProps(**kwargs)
        return A2UIComponent(type=_PRIM_DIVIDER, variant="plain", props=props)

    @staticmethod
    def _skeleton(text: str = "Loading...", **kwargs) -> A2UIComponent:
        props = A2UIProps(text=text, **kwargs)
        return A2UIComponent(type=_PRIM_SKELETON, variant="pulse", props=props)

    @staticmethod
    def _progress(value: float = 0.0, label: str = "", **kwargs) -> A2UIComponent:
        props = A2UIProps(text=label, **kwargs)
        # store progress value in extra fields (Pydantic extra="allow")
        c = A2UIComponent(type=_PRIM_PROGRESS, variant="bar", props=props)
        return c

    # ──────────────────────────────────────────────────────────
    # Course compilation
    # ──────────────────────────────────────────────────────────

    def compile_course(self, raw: Any, topic: str = "") -> Dict[str, Any]:
        """
        Compile a course into v2 component tree + open_classroom payload.

        Returns: {
            "a2ui_component": A2UIComponent (with variants set),
            "open_classroom": dict (iOS CoursePayload-compatible),
        }
        """
        try:
            course = extract_course(raw, fallback_topic=topic or "Your Course")
            component = self._build_course_card(course)
            ios_payload = self._course_to_ios_payload(course)
            return {
                "a2ui_component": component,
                "open_classroom": ios_payload,
            }
        except Exception as e:
            logger.error(f"[A2UICompiler] compile_course failed: {e}", exc_info=True)
            return {
                "a2ui_component": self.compile_error("Course generation encountered an issue"),
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

    def _build_course_card(self, course: NormalizedCourse) -> A2UIComponent:
        """Build a course overview card using v2 primitives."""
        children: List[A2UIComponent] = []

        # Title
        children.append(self._heading(f"📚 {course.title}", level=1))

        # Description
        if course.description:
            children.append(self._text(course.description, variant="plain",
                                       font_size=14, foreground_color="#CCCCCC"))

        # Stats row
        stats = self._container([
            self._stat_pill("📖", f"{course.total_lessons} lessons"),
            self._stat_pill("⏱", course.duration),
            self._stat_pill("📊", course.difficulty),
        ], variant="stack", axis="horizontal", spacing=8)
        children.append(stats)

        # Objectives
        if course.objectives:
            obj_children = [self._heading("Learning Objectives", level=3)]
            for obj in course.objectives[:5]:
                obj_children.append(self._text(f"✓ {obj}", variant="plain",
                                               font_size=14, foreground_color="#AADDAA"))
            children.append(self._container(obj_children, variant="section", spacing=6))

        # Lesson list (first 6)
        flat_lessons = course.flat_lessons[:6]
        if flat_lessons:
            lesson_children = [self._heading("Lessons", level=3)]
            for i, lesson in enumerate(flat_lessons):
                row = self._container([
                    self._text(f"{i + 1}.", variant="plain", font_size=14, foreground_color="#888888"),
                    self._text(lesson.title, variant="plain", font_size=14, foreground_color="#FFFFFF"),
                    self._text(f"{lesson.duration_minutes}m", variant="plain", font_size=12, foreground_color="#888888"),
                ], variant="stack", axis="horizontal", spacing=8)
                lesson_children.append(row)
            children.append(self._container(lesson_children, variant="section", spacing=4))

        # Actions
        children.append(self._container([
            self._button("🚀 Start Learning", "start_course", "primary"),
            self._button("Customize", "customize_course", "secondary"),
        ], variant="stack", axis="horizontal", spacing=12))

        # Wrap in card
        inner = self._container(children, variant="section", spacing=16,
                                padding_horizontal=20, padding_vertical=20)
        return self._card([inner], variant="course")

    # ──────────────────────────────────────────────────────────
    # Explanation compilation
    # ──────────────────────────────────────────────────────────

    def compile_explanation(self, raw: Any, topic: str = "") -> A2UIComponent:
        """Compile an explanation into v2 component tree."""
        try:
            explanation = extract_explanation(raw, fallback_topic=topic)
            return self._build_explanation(explanation)
        except Exception as e:
            logger.error(f"[A2UICompiler] compile_explanation failed: {e}", exc_info=True)
            return self.compile_error("Explanation unavailable")

    def _build_explanation(self, explanation: NormalizedExplanation) -> A2UIComponent:
        """Build explanation card using v2 primitives."""
        children: List[A2UIComponent] = []

        # Title
        children.append(self._heading(f"💡 {explanation.topic}", level=1))

        # Content as markdown
        if explanation.content:
            children.append(self._markdown(explanation.content,
                                           font_size=15, foreground_color="#DDDDDD"))

        # Key points
        if explanation.key_points:
            children.append(self._heading("Key Points", level=3))
            for point in explanation.key_points[:5]:
                children.append(self._text(f"• {point}", variant="plain",
                                           font_size=14, foreground_color="#CCCCCC"))

        # Actions
        children.append(self._container([
            self._button("📚 Create Course", "create_course_from_topic", "primary"),
            self._button("🧠 Quiz Me", "quiz_on_topic", "secondary"),
            self._button("🔍 Deep Dive", "deep_dive", "secondary"),
        ], variant="stack", axis="horizontal", spacing=8))

        inner = self._container(children, variant="section", spacing=14,
                                padding_horizontal=16, padding_vertical=16)
        return self._card([inner], variant="explanation")

    # ──────────────────────────────────────────────────────────
    # Quiz compilation
    # ──────────────────────────────────────────────────────────

    def compile_quiz(self, raw: Any) -> A2UIComponent:
        """Compile a quiz into v2 component tree."""
        try:
            quiz = extract_quiz(raw)
            return self._build_quiz(quiz)
        except Exception as e:
            logger.error(f"[A2UICompiler] compile_quiz failed: {e}", exc_info=True)
            return self.compile_error("Quiz unavailable")

    def _build_quiz(self, quiz: NormalizedQuiz) -> A2UIComponent:
        """Build quiz component using v2 primitives."""
        correct_index = next(
            (i for i, opt in enumerate(quiz.options) if opt.is_correct), 0
        )
        option_dicts = [
            {"id": str(i), "text": opt.text, "is_correct": opt.is_correct}
            for i, opt in enumerate(quiz.options)
        ]
        props = A2UIProps(
            question=quiz.question or "Which of the following is correct?",
            options=option_dicts,
            correct_answer=correct_index,
            correct_answer_index=correct_index,
            title="Quick Check",
            body=quiz.explanation or "",
            explanation=quiz.explanation or "",
        )
        return A2UIComponent(type=_PRIM_QUIZ, variant="mcq", props=props)

    # ──────────────────────────────────────────────────────────
    # Study plan compilation
    # ──────────────────────────────────────────────────────────

    def compile_study_plan(self, raw: Any, topic: str = "") -> A2UIComponent:
        """Compile a study plan into v2 component tree."""
        try:
            plan = extract_study_plan(raw, fallback_topic=topic)
            return self._build_study_plan(plan)
        except Exception as e:
            logger.error(f"[A2UICompiler] compile_study_plan failed: {e}", exc_info=True)
            return self.compile_error("Study plan unavailable")

    def _build_study_plan(self, plan: NormalizedStudyPlan) -> A2UIComponent:
        """Build study plan card using v2 primitives."""
        children: List[A2UIComponent] = []

        children.append(self._heading(f"📋 {plan.title}", level=1))

        if plan.description:
            children.append(self._text(plan.description, variant="plain",
                                       font_size=14, foreground_color="#CCCCCC"))

        # Stats
        children.append(self._container([
            self._stat_pill("📅", plan.duration),
            self._stat_pill("⏰", f"{plan.daily_minutes} min/day"),
        ], variant="stack", axis="horizontal", spacing=8))

        # Milestones
        if plan.milestones:
            for i, milestone in enumerate(plan.milestones[:8]):
                icon = "☑" if i == 0 else "☐"
                row = self._container([
                    self._text(icon, variant="plain", font_size=14, foreground_color="#888888"),
                    self._text(str(milestone), variant="plain", font_size=14, foreground_color="#FFFFFF"),
                ], variant="stack", axis="horizontal", spacing=8)
                children.append(row)

        children.append(self._button("📚 Start Studying", "start_study_plan", "primary"))

        inner = self._container(children, variant="section", spacing=10,
                                padding_horizontal=16, padding_vertical=16)
        return self._card([inner], variant="plan")

    # ──────────────────────────────────────────────────────────
    # Lesson compilation (progressive streaming)
    # ──────────────────────────────────────────────────────────

    def compile_lesson(self, raw: Any, index: int = 0, total: int = 1) -> A2UIComponent:
        """Compile a single lesson into v2 component tree."""
        try:
            if isinstance(raw, NormalizedLesson):
                lesson = raw
            elif isinstance(raw, dict):
                from lyo_app.a2ui.extractors import _extract_lesson
                lesson = _extract_lesson(raw, index)
            else:
                lesson = NormalizedLesson(title=f"Lesson {index + 1}", content=str(raw))

            return self._build_lesson(lesson, index, total)
        except Exception as e:
            logger.error(f"[A2UICompiler] compile_lesson failed: {e}", exc_info=True)
            return self.compile_error(f"Lesson {index + 1} is loading...")

    def _build_lesson(self, lesson: NormalizedLesson, index: int, total: int) -> A2UIComponent:
        """Build lesson card using v2 primitives."""
        children: List[A2UIComponent] = []

        # Progress
        children.append(self._text(
            f"Lesson {index + 1} of {total}",
            variant="plain", font_size=12, foreground_color="#888888"
        ))
        children.append(self._progress(value=(index + 1) / max(total, 1)))

        # Title
        children.append(self._heading(lesson.title, level=2))

        # Content
        content = lesson.content or lesson.description or ""
        if content:
            children.append(self._markdown(content, font_size=15, foreground_color="#DDDDDD"))

        # Navigation
        nav_buttons: List[A2UIComponent] = []
        if index > 0:
            nav_buttons.append(self._button("← Previous", "previous_lesson", "secondary"))
        if index < total - 1:
            nav_buttons.append(self._button("Next →", "next_lesson", "primary"))
        else:
            nav_buttons.append(self._button("✅ Complete", "complete_course", "primary"))

        if nav_buttons:
            children.append(self._container(nav_buttons, variant="stack", axis="horizontal", spacing=12))

        inner = self._container(children, variant="section", spacing=12,
                                padding_horizontal=16, padding_vertical=16)
        return self._card([inner], variant="lesson")

    # ──────────────────────────────────────────────────────────
    # Skeleton / Error
    # ──────────────────────────────────────────────────────────

    def compile_skeleton(self, topic: str = "") -> A2UIComponent:
        """Produce a loading skeleton — shown at time 0."""
        children = [
            self._text(
                f"✨ Preparing: {topic}" if topic else "✨ Preparing your content...",
                variant="plain", font_size=18, font_weight="semibold", foreground_color="#FFFFFF",
            ),
            self._text(
                "This will just take a moment",
                variant="plain", font_size=14, foreground_color="#AAAAAA",
            ),
            self._skeleton("Loading..."),
        ]
        return self._container(children, variant="section", spacing=12,
                               padding_horizontal=20, padding_vertical=20)

    def compile_error(self, message: str = "Something went wrong") -> A2UIComponent:
        """Produce a friendly error UI. NEVER fails."""
        try:
            children = [
                self._text("⚠️", variant="plain", font_size=32, alignment="center"),
                self._text(message, variant="plain", font_size=16,
                           foreground_color="#FF6B6B", alignment="center"),
                self._button("Try Again", "retry", "primary"),
            ]
            return self._container(children, variant="section", spacing=16,
                                   padding_horizontal=20, padding_vertical=24)
        except Exception:
            return A2UIComponent(
                type=_PRIM_TEXT,
                variant="plain",
                props=A2UIProps(text=message),
            )

    # ──────────────────────────────────────────────────────────
    # Generic auto-dispatch
    # ──────────────────────────────────────────────────────────

    def compile_auto(self, raw: Any, ui_type: str = "explanation", topic: str = "") -> A2UIComponent:
        """Auto-detect content type and compile to v2 primitives."""
        dispatch = {
            "course": lambda: self.compile_course(raw, topic).get(
                "a2ui_component", self.compile_error("Course unavailable")
            ),
            "quiz": lambda: self.compile_quiz(raw),
            "study_plan": lambda: self.compile_study_plan(raw, topic),
            "explanation": lambda: self.compile_explanation(raw, topic),
        }
        producer_fn = dispatch.get(ui_type, dispatch["explanation"])
        try:
            return producer_fn()
        except Exception as e:
            logger.error(f"[A2UICompiler] compile_auto failed for {ui_type}: {e}")
            return self.compile_error("Content unavailable")

    # ──────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────

    def _stat_pill(self, emoji: str, text: str) -> A2UIComponent:
        """Small pill-shaped stat indicator."""
        return self._container([
            self._text(emoji, variant="plain", font_size=12),
            self._text(text, variant="plain", font_size=12, foreground_color="#AAAAAA"),
        ], variant="stack", axis="horizontal", spacing=4)

    def _course_to_ios_payload(self, course: NormalizedCourse) -> Dict[str, Any]:
        """Convert NormalizedCourse to iOS CoursePayload-compatible dict."""
        return {
            "course": {
                "id": course.id,
                "title": course.title,
                "topic": course.topic,
                "level": course.difficulty,
                "duration": course.duration,
                "objectives": course.objectives[:6],
                "thumbnail": course.thumbnail,
            }
        }


# ──────────────────────────────────────────────────────────────
# LyoResponse builder — constructs the unified v2 response envelope
# ──────────────────────────────────────────────────────────────

class LyoResponseBuilder:
    """
    Builds the unified LyoResponse envelope for v2 SSE events.

    Matches the iOS LyoResponse struct:
        version, requestId, message, ui, command, suggestions, conversationId
    """

    @staticmethod
    def build(
        *,
        message: Optional[str] = None,
        ui: Optional[A2UIComponent] = None,
        command: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[Dict[str, str]]] = None,
        request_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a complete LyoResponse dict."""
        response: Dict[str, Any] = {
            "version": "2.0",
            "requestId": request_id or str(uuid4()),
        }
        if message is not None:
            response["message"] = message
        if ui is not None:
            # Shift to v2 format for LyoResponse envelopes
            response["ui"] = ui.to_v2_dict() if hasattr(ui, "to_v2_dict") else ui.to_dict()
        if command is not None:
            response["command"] = command
        if suggestions is not None:
            response["suggestions"] = suggestions
        if conversation_id is not None:
            response["conversationId"] = conversation_id
        return response

    @staticmethod
    def build_command(action: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build a LyoCommand dict."""
        cmd: Dict[str, Any] = {"action": action}
        if payload:
            cmd["payload"] = payload
        return cmd


# ──────────────────────────────────────────────────────────────
# LLM Structured Output Helpers
# ──────────────────────────────────────────────────────────────

def validate_llm_response(raw: Dict[str, Any]) -> Optional[LyoResponseSchema]:
    """
    Validate a raw LLM structured-output dict against the v2 schema.
    Returns the validated model or None if validation fails.
    """
    try:
        return validate_lyo_response(raw)
    except Exception as e:
        logger.warning("LLM v2 response validation failed: %s", e)
        return None


def validate_llm_component(raw: Dict[str, Any]) -> Optional[LyoUIComponentSchema]:
    """
    Validate a raw LLM component dict against the v2 schema.
    Returns the validated model or None if validation fails.
    """
    try:
        return validate_lyo_component(raw)
    except Exception as e:
        logger.warning("LLM v2 component validation failed: %s", e)
        return None


def get_v2_system_prompt_schema() -> str:
    """
    Returns a compact JSON Schema string suitable for injection into
    the LLM system prompt.  This tells the LLM exactly what shape
    to return when producing structured UI.
    """
    import json
    schema = get_lyo_response_json_schema()
    return json.dumps(schema, indent=2)


def get_v2_system_prompt_fragment() -> str:
    """
    Returns a natural-language + schema fragment to inject into the
    LLM system prompt for A2UI v2 structured output.
    """
    import json
    schema = get_lyo_response_json_schema()
    compact = json.dumps(schema, separators=(",", ":"))

    return f"""
## A2UI v2 Structured Output

When the user asks to learn something, create a course, take a quiz, study,
or any other educational task, respond with a JSON object matching this schema:

{compact}

### Key Rules:
1. `message` is ALWAYS required — a plain-text response renderable standalone.
2. `ui` is optional — add it when structured UI helps (courses, quizzes, plans).
3. Use the 22-primitive type system: text, media, divider, input, button,
   container, card, list, nav, quiz, quizResult, course, flashcard, plan,
   tracker, assignment, document, progress, aiBubble, social, alert, skeleton.
4. `variant` narrows the type (e.g. type=text, variant=heading).
5. Keep component trees shallow — max 4 levels of nesting.
6. Use `content` for text/labels, `data` for domain payloads (quiz options, etc.).
7. `children` are only for layout/container/card/list primitives.
"""


# Module-level singleton
a2ui_compiler = A2UICompiler()
lyo_response_builder = LyoResponseBuilder()
