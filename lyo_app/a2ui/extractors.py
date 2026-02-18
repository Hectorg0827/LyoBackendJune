"""
A2UI Content Extractors — Deterministic extraction chains for each agent output type.

Each extractor tries progressively looser parsing strategies:
  1. Validate as typed dict → structured
  2. json.loads() + manual field extraction → partial
  3. Regex patterns for known fields → minimal
  4. Fallback: wrap raw text → always works

RULE: Extractors NEVER raise. They ALWAYS return a valid normalized model.
"""

import json
import re
import logging
from typing import Any, Dict, List, Optional

from lyo_app.a2ui.normalized_models import (
    NormalizedCourse,
    NormalizedModule,
    NormalizedLesson,
    NormalizedQuiz,
    NormalizedQuizOption,
    NormalizedExplanation,
    NormalizedStudyPlan,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Course Extractor
# ──────────────────────────────────────────────────────────────

def extract_course(raw: Any, fallback_topic: str = "Your Course") -> NormalizedCourse:
    """
    Extract a NormalizedCourse from raw LLM output.
    Handles: dict, JSON string, plain text, or garbage.
    NEVER raises.
    """
    try:
        data = _coerce_to_dict(raw)
        if data:
            return _extract_course_from_dict(data, fallback_topic)
    except Exception as e:
        logger.warning(f"[Extractor] Course dict extraction failed: {e}")

    # Fallback: try to parse as markdown outline
    try:
        text = _coerce_to_str(raw)
        if text:
            return _extract_course_from_text(text, fallback_topic)
    except Exception as e:
        logger.warning(f"[Extractor] Course text extraction failed: {e}")

    # Ultimate fallback
    return NormalizedCourse(
        title=f"Learn {fallback_topic}",
        topic=fallback_topic,
        description=f"A course about {fallback_topic}",
        objectives=[f"Understand the fundamentals of {fallback_topic}"],
    )


def _extract_course_from_dict(data: Dict[str, Any], fallback_topic: str) -> NormalizedCourse:
    """Extract course from a dict (might be messy LLM JSON)."""
    title = (
        data.get("title")
        or data.get("course_title")
        or data.get("name")
        or f"Learn {fallback_topic}"
    )
    topic = data.get("topic") or data.get("subject") or title
    description = data.get("description") or data.get("summary") or ""
    difficulty = (
        data.get("difficulty")
        or data.get("level")
        or data.get("skill_level")
        or "Beginner"
    )

    # Duration: handle various formats
    duration_raw = (
        data.get("duration")
        or data.get("estimated_duration")
        or data.get("estimated_hours")
    )
    if isinstance(duration_raw, (int, float)):
        duration = f"~{int(duration_raw * 60)} min" if duration_raw < 10 else f"~{int(duration_raw)} min"
    elif isinstance(duration_raw, str):
        duration = duration_raw
    else:
        duration = "~30 min"

    # Objectives
    objectives = (
        data.get("objectives")
        or data.get("learning_objectives")
        or data.get("goals")
        or []
    )
    if isinstance(objectives, str):
        objectives = [objectives]

    # Lessons / Modules
    modules = []
    raw_lessons = data.get("lessons") or data.get("sections") or []
    raw_modules = data.get("modules") or []

    if raw_modules:
        for i, mod_raw in enumerate(raw_modules):
            if isinstance(mod_raw, dict):
                mod_lessons_raw = mod_raw.get("lessons") or mod_raw.get("sections") or []
                mod_lessons = [_extract_lesson(l, j) for j, l in enumerate(mod_lessons_raw)]
                modules.append(NormalizedModule(
                    title=mod_raw.get("title") or f"Module {i + 1}",
                    description=mod_raw.get("description") or "",
                    lessons=mod_lessons,
                    order=i,
                ))
    elif raw_lessons:
        # Flat list of lessons → wrap in a single module
        lessons = [_extract_lesson(l, j) for j, l in enumerate(raw_lessons)]
        modules.append(NormalizedModule(
            title=title,
            lessons=lessons,
        ))

    # If no modules/lessons extracted, create a minimal structure
    if not modules:
        modules.append(NormalizedModule(
            title=title,
            lessons=[
                NormalizedLesson(title="Introduction", description=f"Getting started with {topic}"),
                NormalizedLesson(title="Core Concepts", description=f"Key ideas in {topic}", order=1),
                NormalizedLesson(title="Practice", description="Apply what you've learned", order=2),
            ],
        ))

    return NormalizedCourse(
        title=title,
        topic=topic,
        description=description,
        modules=modules,
        objectives=objectives,
        difficulty=difficulty,
        duration=duration,
    )


def _extract_lesson(raw: Any, index: int) -> NormalizedLesson:
    """Extract a single lesson from a dict or string."""
    if isinstance(raw, dict):
        title = raw.get("title") or raw.get("name") or f"Lesson {index + 1}"
        content = raw.get("content") or raw.get("text") or raw.get("body") or ""
        description = raw.get("description") or raw.get("summary") or ""
        lesson_type = raw.get("type") or raw.get("lesson_type") or "reading"
        dur_raw = raw.get("duration") or raw.get("duration_minutes")
        if isinstance(dur_raw, str):
            # Parse "15 min" → 15
            nums = re.findall(r"\d+", dur_raw)
            dur = int(nums[0]) if nums else 10
        elif isinstance(dur_raw, (int, float)):
            dur = int(dur_raw)
        else:
            dur = 10
        return NormalizedLesson(
            title=title,
            content=content,
            description=description,
            lesson_type=lesson_type,
            duration_minutes=dur,
            order=index,
        )
    elif isinstance(raw, str):
        return NormalizedLesson(title=raw, order=index)
    else:
        return NormalizedLesson(title=f"Lesson {index + 1}", order=index)


def _extract_course_from_text(text: str, fallback_topic: str) -> NormalizedCourse:
    """Extract a course from a markdown/text outline."""
    lines = text.strip().split("\n")
    title = fallback_topic
    lessons = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Heading → title
        if stripped.startswith("#"):
            candidate = stripped.lstrip("#").strip()
            if candidate and not title:
                title = candidate
        # Numbered or bullet items → lessons
        elif re.match(r"^[\d]+[\.\)]\s+|^[-*•]\s+", stripped):
            lesson_title = re.sub(r"^[\d]+[\.\)]\s+|^[-*•]\s+", "", stripped).strip()
            if lesson_title:
                lessons.append(NormalizedLesson(title=lesson_title, order=len(lessons)))

    if not lessons:
        lessons = [NormalizedLesson(title="Overview", content=text)]

    return NormalizedCourse(
        title=title or f"Learn {fallback_topic}",
        topic=fallback_topic,
        modules=[NormalizedModule(title=title or fallback_topic, lessons=lessons)],
    )


# ──────────────────────────────────────────────────────────────
# Explanation Extractor
# ──────────────────────────────────────────────────────────────

def extract_explanation(raw: Any, fallback_topic: str = "Topic") -> NormalizedExplanation:
    """Extract a NormalizedExplanation. NEVER raises."""
    try:
        data = _coerce_to_dict(raw)
        if data:
            return NormalizedExplanation(
                topic=data.get("topic") or data.get("title") or fallback_topic,
                content=data.get("content") or data.get("text") or data.get("explanation") or str(raw),
                key_points=data.get("key_points") or data.get("highlights") or [],
                related_topics=data.get("related_topics") or [],
            )
    except Exception:
        pass

    text = _coerce_to_str(raw)
    return NormalizedExplanation(
        topic=fallback_topic,
        content=text,
    )


# ──────────────────────────────────────────────────────────────
# Quiz Extractor
# ──────────────────────────────────────────────────────────────

def extract_quiz(raw: Any) -> NormalizedQuiz:
    """Extract a NormalizedQuiz. NEVER raises."""
    try:
        data = _coerce_to_dict(raw)
        if data:
            question = data.get("question") or data.get("text") or data.get("prompt") or "Question"
            raw_options = data.get("options") or data.get("choices") or data.get("answers") or []
            correct_idx = data.get("correct_answer_index") or data.get("correct") or data.get("answer") or 0

            options = []
            for i, opt in enumerate(raw_options):
                if isinstance(opt, dict):
                    options.append(NormalizedQuizOption(
                        text=opt.get("text") or opt.get("label") or str(opt),
                        is_correct=opt.get("is_correct") or opt.get("correct") or False,
                    ))
                elif isinstance(opt, str):
                    options.append(NormalizedQuizOption(
                        text=opt,
                        is_correct=(i == correct_idx if isinstance(correct_idx, int) else False),
                    ))

            if not options:
                options = [
                    NormalizedQuizOption(text="True", is_correct=True),
                    NormalizedQuizOption(text="False"),
                ]

            return NormalizedQuiz(
                question=question,
                options=options,
                explanation=data.get("explanation") or data.get("rationale") or "",
            )
    except Exception:
        pass

    return NormalizedQuiz()


# ──────────────────────────────────────────────────────────────
# Study Plan Extractor
# ──────────────────────────────────────────────────────────────

def extract_study_plan(raw: Any, fallback_topic: str = "Topic") -> NormalizedStudyPlan:
    """Extract a NormalizedStudyPlan. NEVER raises."""
    try:
        data = _coerce_to_dict(raw)
        if data:
            return NormalizedStudyPlan(
                title=data.get("title") or f"Study Plan: {fallback_topic}",
                description=data.get("description") or "",
                milestones=data.get("milestones") or data.get("goals") or data.get("steps") or [],
                duration=data.get("duration") or data.get("timeline") or "2 weeks",
                daily_minutes=data.get("daily_minutes") or 30,
            )
    except Exception:
        pass

    return NormalizedStudyPlan(title=f"Study Plan: {fallback_topic}")


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _coerce_to_dict(raw: Any) -> Optional[Dict[str, Any]]:
    """Try to get a dict from any input."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        # Try JSON parse
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Strip markdown code fences
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    if hasattr(raw, "__dict__"):
        return vars(raw)
    return None


def _coerce_to_str(raw: Any) -> str:
    """Get a string from any input."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # Try to get a text field
        for key in ("content", "text", "body", "description", "response", "message"):
            if key in raw and isinstance(raw[key], str):
                return raw[key]
        return json.dumps(raw, indent=2, default=str)
    return str(raw) if raw is not None else ""
