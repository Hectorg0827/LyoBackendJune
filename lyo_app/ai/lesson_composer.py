"""Compose a structured, learner-adapted chat lesson.

Chat previously answered every "teach me X" with free prose from a single
prompt. That had two consequences seen in production: the model graded a
learner's answer by vibes (it praised "9" as the square root of 49), and every
learner got the same wall of text regardless of what they already knew.

This module produces a *typed* lesson instead. The model fills a schema that is
validated before anything is shown, questions carry a real ``correct_index`` so
grading can happen server-side, and the lesson is assembled from what the
learner's own mastery record says they know and get wrong.

Two modes:

``probe``
    A hook plus exactly one calibration question. The answer decides where the
    real lesson starts, so a learner who already knows the basics is not walked
    through them. Always carries an explicit opt-out so a probe never becomes a
    gate in front of a straight answer.

``teach``
    The lesson itself, entered at the depth the probe (or stored mastery)
    selected, ending in a check whose result is recorded.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# The lesson generation budget. Higher than a plain chat turn because this
# produces the whole structured lesson in one call, but the pipeline is not
# token-streamed anyway (stream_lyo2 awaits the full executor result before
# emitting), so this is not additional perceived latency.
COMPOSE_TIMEOUT_SECONDS = 45.0

PROVIDER_ORDER = ["gemini-2.5-flash", "gpt-4o-mini"]


class SectionKind(str, Enum):
    """The beats of a lesson, in the order they are rendered.

    Each maps to a distinct block on the client, which is what makes the
    lesson scannable rather than a wall of prose.
    """

    hook = "hook"                      # the question the concept answers
    core = "core"                      # the idea itself, one sentence
    representation = "representation"  # a *second* way to see the same idea
    example = "example"                # worked instance
    trap = "trap"                      # common mistakes, pre-empted
    method = "method"                  # how to do it yourself
    reference = "reference"            # compact lookup table


class LessonSection(BaseModel):
    kind: SectionKind
    text: str
    # Set on `representation`/`example` when the idea is better shown than told.
    latex: Optional[str] = None
    # Set on `reference` only: a GitHub-flavored markdown table.
    table_markdown: Optional[str] = None


class CheckOption(BaseModel):
    text: str
    # For a distractor: the specific misconception picking it reveals. This is
    # what lets a wrong answer produce a targeted correction and a recorded
    # error pattern instead of a generic "not quite".
    reveals: Optional[str] = None


class CheckItem(BaseModel):
    question: str
    options: List[CheckOption]
    correct_index: int
    explanation: str
    hint: Optional[str] = None
    # Index of an "I'm not sure — just explain it" option, when present. It is
    # neither correct nor a misconception: selecting it skips grading entirely
    # and drops to the baseline lesson.
    bailout_index: Optional[int] = None

    @field_validator("options")
    @classmethod
    def _need_at_least_two_options(cls, v: List[CheckOption]) -> List[CheckOption]:
        if len(v) < 2:
            raise ValueError("a check needs at least two options")
        return v

    @field_validator("correct_index")
    @classmethod
    def _correct_index_in_range(cls, v: int, info) -> int:
        options = info.data.get("options") or []
        if options and not (0 <= v < len(options)):
            raise ValueError(f"correct_index {v} out of range for {len(options)} options")
        return v

    def is_bailout(self, index: int) -> bool:
        return self.bailout_index is not None and index == self.bailout_index

    def grade(self, index: int) -> bool:
        """Authoritative correctness. The client never decides this."""
        return index == self.correct_index

    def misconception_for(self, index: int) -> Optional[str]:
        if self.is_bailout(index) or self.grade(index):
            return None
        if 0 <= index < len(self.options):
            return self.options[index].reveals
        return None


class ChatLesson(BaseModel):
    topic: str
    skill_id: str
    is_probe: bool = False
    sections: List[LessonSection] = Field(default_factory=list)
    check: Optional[CheckItem] = None
    # Named follow-up directions, offered as chips. Concrete ("estimate
    # irrational roots"), never "want to know more?".
    next_directions: List[str] = Field(default_factory=list)

    def to_plain_text(self) -> str:
        """Flatten to prose for clients that do not render blocks yet.

        iOS and Android consume the existing plain-text `answer` event, so the
        lesson has to degrade to something readable rather than vanishing.
        """
        parts: List[str] = []
        for section in self.sections:
            parts.append(section.text)
            if section.latex:
                parts.append(f"$$\n{section.latex}\n$$")
            if section.table_markdown:
                parts.append(section.table_markdown)
        if self.check:
            options = "\n".join(
                f"{chr(65 + i)}. {opt.text}" for i, opt in enumerate(self.check.options)
            )
            parts.append(f"{self.check.question}\n{options}")
        return "\n\n".join(p for p in parts if p).strip()


def slugify_skill(topic: str) -> str:
    """Stable skill id so mastery accumulates across sessions for one concept.

    "Square Roots!" and "square roots" must land on the same LearnerMastery row
    or nothing ever accumulates.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", (topic or "").strip().lower()).strip("_")
    return slug[:80] or "general"


PEDAGOGY_RULES = """\
TEACHING DISCIPLINE (these override any instinct to be agreeable):
- Teach ONE idea per section. Never restate the same point in two sections.
- No filler praise. Never open with "Great question" or similar.
- Never ask a question and then answer it yourself in the same breath.
- A distractor must be a mistake a real learner actually makes, and its
  `reveals` field must name the specific confusion behind it — not "wrong".
- The trap section pre-empts errors before they happen. Name the error, then
  why it is tempting, then what is actually true.
- The representation section must show the SAME idea a genuinely different way
  (a geometric/visual/physical framing), not restate the core sentence.
- Write LaTeX in the `latex` field only. Never put $ or \\( delimiters in `text`.
"""


def _probe_prompt(topic: str, learner_context: str) -> str:
    return f"""You are Lyo, calibrating before teaching "{topic}".

Produce a JSON object with:
- "sections": EXACTLY ONE section, kind "hook" — one or two sentences framing
  the question this concept answers. Do NOT explain the concept yet.
- "check": ONE diagnostic question that separates a learner who already
  understands "{topic}" from one who does not. Include 3 real answer options
  plus a final option worded as an opt-out (e.g. "Not sure — just explain it").
  Set "bailout_index" to that final option's index. Set "correct_index" to the
  right answer. Each wrong option needs a "reveals" naming the confusion.
- "next_directions": []

{PEDAGOGY_RULES}
{learner_context}

Return ONLY the JSON object, matching this shape:
{{"sections":[{{"kind":"hook","text":"..."}}],
  "check":{{"question":"...","options":[{{"text":"...","reveals":null}}],
            "correct_index":0,"explanation":"...","hint":"...","bailout_index":3}},
  "next_directions":[]}}"""


def _teach_prompt(topic: str, learner_context: str, entry_note: str) -> str:
    return f"""You are Lyo, teaching "{topic}" to one specific learner.

{entry_note}

Produce a JSON object with "sections" in this order (omit a section only if it
genuinely does not apply to this topic):
1. kind "hook" — the question this concept answers.
2. kind "core" — the idea itself, ONE sentence.
3. kind "representation" — the same idea shown a different way (geometric,
   visual, or physical). Use the "latex" field if a formula helps.
4. kind "example" — one worked instance, with "latex" if useful.
5. kind "trap" — the mistakes learners actually make here. Be specific.
6. kind "method" — how the learner does this themselves, as ordered steps.
7. kind "reference" — a compact lookup table in "table_markdown"
   (GitHub-flavored markdown), if the topic has facts worth tabulating.

Then:
- "check": ONE retrieval question testing the idea just taught. Real options,
  a "reveals" on each distractor, an "explanation", and a "hint". No
  bailout_index here.
- "next_directions": 2-3 concrete named directions to go next.

{PEDAGOGY_RULES}
{learner_context}

Return ONLY the JSON object."""


async def _build_learner_context(
    db: Optional[AsyncSession], user_id: Optional[str], skill_id: str
) -> str:
    """Learner-specific prompt context, or '' when there is nothing known.

    Reuses the existing personalization prompt builder rather than inventing a
    parallel profile. Failures here must never block teaching.
    """
    if db is None or not user_id:
        return ""
    try:
        from lyo_app.personalization.service import personalization_engine

        context = await personalization_engine.build_prompt_context(
            db, str(user_id), current_skill=skill_id
        )
        if not context:
            return ""
        return (
            "\n--- WHAT YOU KNOW ABOUT THIS LEARNER ---\n"
            f"{context}\n"
            "Pitch the explanation at their reading level, skip what they have "
            "mastered, and aim the trap section at what they actually get wrong.\n"
            "--- END LEARNER CONTEXT ---\n"
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Learner context unavailable, teaching generically: {e}")
        return ""


def _entry_note(probe_result: Optional[Dict[str, Any]]) -> str:
    """Turn the probe outcome into an instruction about where to start."""
    if not probe_result:
        return "Start from the beginning; assume no prior knowledge."
    if probe_result.get("bailed_out"):
        return (
            "The learner opted out of the calibration question, so do not assume "
            "prior knowledge. Teach the baseline version, and do not mention the "
            "skipped question."
        )
    if probe_result.get("correct"):
        return (
            "The learner ANSWERED THE CALIBRATION QUESTION CORRECTLY. Do not "
            "re-teach the basics they just demonstrated. Open by acknowledging "
            "that briefly and specifically, then go deeper: edge cases, the "
            "non-obvious consequences, and the harder variant."
        )
    misconception = probe_result.get("misconception")
    detail = f" Their answer reveals this specific confusion: {misconception}." if misconception else ""
    return (
        "The learner ANSWERED THE CALIBRATION QUESTION INCORRECTLY."
        f"{detail} Start from the definition and address that confusion "
        "directly and early. Do not tell them they were right."
    )


async def _generate_json(prompt: str) -> Optional[Dict[str, Any]]:
    """One JSON-mode model call, or None if the model is unavailable."""
    try:
        from lyo_app.core.ai_resilience import ai_resilience_manager

        if not ai_resilience_manager.session:
            await ai_resilience_manager.initialize()

        response = await asyncio.wait_for(
            ai_resilience_manager.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                provider_order=PROVIDER_ORDER,
            ),
            timeout=COMPOSE_TIMEOUT_SECONDS,
        )
        text = (response.get("content") or "").strip()
        if not text:
            return None
        return json.loads(_strip_code_fence(text))
    except asyncio.TimeoutError:
        logger.error("Lesson composition timed out")
    except json.JSONDecodeError as e:
        logger.error(f"Lesson composition returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"Lesson composition failed: {e}", exc_info=True)
    return None


def _strip_code_fence(text: str) -> str:
    """Models wrap JSON in ``` fences despite instructions not to."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
    return stripped.rsplit("```", 1)[0].strip()


async def compose(
    topic: str,
    *,
    db: Optional[AsyncSession] = None,
    user_id: Optional[str] = None,
    mode: str = "probe",
    probe_result: Optional[Dict[str, Any]] = None,
) -> Optional[ChatLesson]:
    """Compose a lesson, or None to fall back to the existing prose path.

    Returning None rather than raising is deliberate: a composition failure
    should degrade chat to how it behaves today, never to an error.
    """
    skill_id = slugify_skill(topic)
    learner_context = await _build_learner_context(db, user_id, skill_id)

    if mode == "probe":
        prompt = _probe_prompt(topic, learner_context)
    else:
        prompt = _teach_prompt(topic, learner_context, _entry_note(probe_result))

    raw = await _generate_json(prompt)
    if raw is None:
        return None

    raw["topic"] = topic
    raw["skill_id"] = skill_id
    raw["is_probe"] = mode == "probe"

    try:
        lesson = ChatLesson.model_validate(raw)
    except Exception as e:
        # A malformed lesson is worse than no lesson: fall back to prose.
        logger.error(f"Composed lesson failed validation, falling back: {e}")
        return None

    if mode == "probe" and lesson.check is None:
        logger.warning("Probe lesson had no check question; falling back")
        return None

    return lesson
