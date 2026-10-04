"""Deterministic interaction contract for Lyo Chat.

The router classifies the domain/workflow.  This layer defines the *shape of
the interaction* the user explicitly requested and is authoritative over
pedagogical preferences, planner creativity, and proactive behavior.

It intentionally contains no model call.  A request such as "summarize this
PDF" must remain a summary even if a later model would prefer to quiz, while
"quiz me on this" must remain a quiz.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import List, Literal

from pydantic import BaseModel, Field

from lyo_app.ai.schemas.lyo2 import Intent, RouterDecision, RouterRequest


class InteractionMode(str, Enum):
    ANSWER = "answer"
    EXPLAIN = "explain"
    TEACH = "teach"
    QUIZ = "quiz"
    CREATE = "create"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    SEARCH = "search"
    CONTINUE = "continue"
    REVIEW = "review"
    CLARIFY = "clarify"


class InteractionContract(BaseModel):
    mode: InteractionMode
    depth: Literal["compact", "standard", "deep"] = "standard"
    representation: Literal[
        "prose", "visual", "table", "timeline", "steps", "document"
    ] = "prose"
    answer_first: bool = False
    fast_lane: bool = False
    requires_grounding: bool = False
    preserve_workflow: bool = False
    suggested_actions: List[str] = Field(default_factory=list)


_DEEP_RE = re.compile(
    r"\b(deep dive|deeper|more detail|in depth|in-depth|detailed|detail|comprehensive|thorough|"
    r"profundo|en detalle|detallad[oa])\b",
    re.IGNORECASE,
)
_COMPACT_RE = re.compile(
    r"\b(brief|briefly|short|quick|quickly|concise|simple answer|"
    r"breve|rápido|rapido|conciso)\b",
    re.IGNORECASE,
)
_COMPARE_RE = re.compile(
    r"\b(compare|comparison|versus|vs\.?|difference between|diferencia entre|compar[ae])\b",
    re.IGNORECASE,
)
_SUMMARY_RE = re.compile(
    r"\b(summar(?:y|ize|ise)|sum up|tl;?dr|resume|resumen|resumir)\b",
    re.IGNORECASE,
)
_TEACH_RE = re.compile(
    r"\b(teach me|walk me through|lesson on|tutor me|ens[eé][nñ]ame|dame una clase)\b",
    re.IGNORECASE,
)
_DIRECT_EXPLAIN_RE = re.compile(
    r"\b(explain|why does|how does|help me understand|expl[ií]ca|por qu[eé])\b",
    re.IGNORECASE,
)
_DIRECT_ANSWER_RE = re.compile(
    r"\b(what is|what are|who is|who are|when is|where is|which is|"
    r"what does|how much|how many|define|identify|"
    r"qu[eé] es|qui[eé]n es|cu[aá]nt[oa]s?|define|identifica)\b",
    re.IGNORECASE,
)
_CURRENT_RE = re.compile(
    r"\b(latest|today|current|currently|right now|recent|newest|"
    r"hoy|actual|actualmente|reciente|últim[oa]|ultimo|última)\b",
    re.IGNORECASE,
)
_CONTINUE_RE = re.compile(
    r"^\s*(continue|keep going|go on|next|resume|contin[uú]a|sigue|pr[oó]ximo)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_VISUAL_RE = re.compile(
    r"\b(show visually|visual|diagram|draw|graph|picture|image|"
    r"visualmente|diagrama|gr[aá]fic[oa]|imagen)\b",
    re.IGNORECASE,
)
_TABLE_RE = re.compile(r"\b(table|chart|tabla|cuadro)\b", re.IGNORECASE)
_TIMELINE_RE = re.compile(r"\b(timeline|chronolog|línea de tiempo|linea de tiempo)\b", re.IGNORECASE)
_STEPS_RE = re.compile(r"\b(step by step|steps|procedure|paso a paso|pasos)\b", re.IGNORECASE)
_ATTACHMENT_REF_RE = re.compile(
    r"\b(this|that|it|attached|attachment|file|document|pdf|image|photo|"
    r"esto|este|esta|archivo|documento|imagen|foto)\b",
    re.IGNORECASE,
)

_WORKFLOW_INTENTS = {
    Intent.COURSE,
    Intent.QUIZ,
    Intent.FLASHCARDS,
    Intent.STUDY_PLAN,
    Intent.TEST_PREP,
    Intent.SCHEDULE_REMINDERS,
    Intent.COMMUNITY,
    Intent.MODIFY_ARTIFACT,
}
_REVIEW_INTENTS = {Intent.REFLECT, Intent.WEEKLY_REVIEW}


def _depth(text: str) -> Literal["compact", "standard", "deep"]:
    if _DEEP_RE.search(text):
        return "deep"
    if _COMPACT_RE.search(text):
        return "compact"
    return "standard"


def _representation(text: str, *, has_media: bool) -> Literal[
    "prose", "visual", "table", "timeline", "steps", "document"
]:
    if _TABLE_RE.search(text) or _COMPARE_RE.search(text):
        return "table"
    if _TIMELINE_RE.search(text):
        return "timeline"
    if _STEPS_RE.search(text):
        return "steps"
    if _VISUAL_RE.search(text):
        return "visual"
    if has_media:
        return "document"
    return "prose"


def _actions(mode: InteractionMode, *, has_media: bool) -> list[str]:
    if mode in {InteractionMode.ANSWER, InteractionMode.EXPLAIN, InteractionMode.SUMMARIZE, InteractionMode.COMPARE}:
        if has_media:
            return [
                "Explain deeper",
                "Show visually",
                "Teach this in Classroom",
                "Quiz me",
                "I have a test on this",
            ]
        return ["Explain deeper", "Show visually", "Give example", "Teach this in Classroom", "Quiz me"]
    if mode is InteractionMode.TEACH:
        return ["Continue", "Show visually", "Give example", "Quiz me", "Open Classroom"]
    if mode is InteractionMode.QUIZ:
        return ["Explain answers", "Try harder", "Teach this in Classroom"]
    if mode is InteractionMode.REVIEW:
        return ["Review weak spots", "Quiz me", "Teach this in Classroom"]
    return ["Tell me more", "Teach this in Classroom", "Quiz me"]


def resolve_interaction_contract(
    request: RouterRequest,
    decision: RouterDecision,
    *,
    has_media: bool,
    has_current_media: bool,
) -> InteractionContract:
    text = (request.text or "").strip()
    intent = decision.intent
    depth = _depth(text)
    representation = _representation(text, has_media=has_media)

    # Explicit product workflows own the turn.  The interaction contract does
    # not replace them; it prevents later layers from silently changing them.
    if intent in _WORKFLOW_INTENTS:
        mode = InteractionMode.QUIZ if intent is Intent.QUIZ else InteractionMode.CREATE
        if intent is Intent.TEST_PREP:
            mode = InteractionMode.TEACH
        return InteractionContract(
            mode=mode,
            depth=depth,
            representation=representation,
            answer_first=False,
            fast_lane=False,
            requires_grounding=has_media,
            preserve_workflow=True,
            suggested_actions=_actions(mode, has_media=has_media),
        )

    if intent in _REVIEW_INTENTS:
        return InteractionContract(
            mode=InteractionMode.REVIEW,
            depth=depth,
            representation=representation,
            preserve_workflow=True,
            suggested_actions=_actions(InteractionMode.REVIEW, has_media=has_media),
        )

    if _CONTINUE_RE.search(text):
        mode = InteractionMode.CONTINUE
    elif _COMPARE_RE.search(text):
        mode = InteractionMode.COMPARE
    elif _SUMMARY_RE.search(text) or intent is Intent.SUMMARIZE_NOTES:
        mode = InteractionMode.SUMMARIZE
    elif _TEACH_RE.search(text):
        mode = InteractionMode.TEACH
    elif _CURRENT_RE.search(text):
        mode = InteractionMode.SEARCH
    elif _DIRECT_EXPLAIN_RE.search(text):
        mode = InteractionMode.EXPLAIN
    elif _DIRECT_ANSWER_RE.search(text) or has_current_media:
        mode = InteractionMode.ANSWER
    else:
        # EXPLAIN is the router's broad educational bucket.  If the learner
        # did not explicitly ask for a lesson, default to answering rather than
        # manufacturing instruction.
        mode = InteractionMode.EXPLAIN if intent is Intent.EXPLAIN else InteractionMode.ANSWER

    attachment_referential = bool(_ATTACHMENT_REF_RE.search(text))
    answer_first = mode in {
        InteractionMode.ANSWER,
        InteractionMode.EXPLAIN,
        InteractionMode.SUMMARIZE,
        InteractionMode.COMPARE,
        InteractionMode.SEARCH,
    }
    if has_media and (has_current_media or attachment_referential):
        answer_first = mode is not InteractionMode.TEACH

    fast_lane = (
        mode in {
            InteractionMode.ANSWER,
            InteractionMode.EXPLAIN,
            InteractionMode.SUMMARIZE,
            InteractionMode.COMPARE,
            InteractionMode.CONTINUE,
        }
        and not decision.is_reply_to_artifact
        and not decision.needs_clarification
    )

    requires_grounding = has_media or mode is InteractionMode.SEARCH

    return InteractionContract(
        mode=mode,
        depth=depth,
        representation=representation,
        answer_first=answer_first,
        fast_lane=fast_lane,
        requires_grounding=requires_grounding,
        preserve_workflow=False,
        suggested_actions=_actions(mode, has_media=has_media),
    )
