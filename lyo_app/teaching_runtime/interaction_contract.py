"""Deterministic chat interaction contract.

This module answers one question before pedagogy, planning, memory, or model
selection is allowed to act: what did the learner ask Lyo to *do*?

The contract is intentionally small and deterministic. Downstream layers may
realize the request well, but they may not silently transform an ANSWER into a
quiz, a SUMMARIZE into a lesson, or a QUIZ into a lecture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from lyo_app.ai.schemas.lyo2 import Intent


class InteractionMode(str, Enum):
    ANSWER = "answer"
    EXPLAIN = "explain"
    ANALYZE = "analyze"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    TEACH = "teach"
    QUIZ = "quiz"
    CREATE = "create"
    SEARCH = "search"
    CONTINUE = "continue"
    CLARIFY = "clarify"
    WORKFLOW = "workflow"


class ResponseDepth(str, Enum):
    CONCISE = "concise"
    STANDARD = "standard"
    DEEP = "deep"


class DeliveryMode(str, Enum):
    TEXT = "text"
    VOICE = "voice"


@dataclass(frozen=True)
class InteractionContract:
    mode: InteractionMode
    depth: ResponseDepth
    fast_lane: bool
    delivery_mode: DeliveryMode = DeliveryMode.TEXT
    workflow_intent: Optional[Intent] = None
    attachment_authoritative: bool = False
    reason_code: str = "general"
    directives: tuple[str, ...] = ()
    voice_interrupted_previous_turn: bool = False


_DEEP_RE = re.compile(
    r"\b(?:deep dive|go deeper|more detail|detailed|in depth|thorough|"
    r"explain deeply|profundiza|m[aá]s detalle)\b",
    re.IGNORECASE,
)
_CONCISE_RE = re.compile(
    r"\b(?:brief|briefly|short answer|concise|quickly|in one sentence|"
    r"tldr|tl;dr|resumen corto|breve)\b",
    re.IGNORECASE,
)
_QUIZ_RE = re.compile(
    r"\b(?:quiz me|test me|give me a quiz|practice questions?|"
    r"hazme (?:un )?(?:quiz|examen)|ponme a prueba)\b",
    re.IGNORECASE,
)
_TEST_PREP_RE = re.compile(
    r"\b(?:i have (?:a|an|my) (?:test|exam)|prepare me for (?:a|my) (?:test|exam)|"
    r"use (?:this|it|the (?:file|document|pdf)) for test prep|"
    r"study for (?:a|my) (?:test|exam)|tengo (?:un )?examen|prep[aá]rame para (?:el|un) examen)\b",
    re.IGNORECASE,
)
_COACH_RE = re.compile(
    r"\b(?:what should i (?:study|work on|do next)|what do i need to work on|"
    r"what(?:'s| is) my mission(?: today)?|my mission today|"
    r"how ready am i|am i ready|show me my readiness|"
    r"i have \d{1,3} (?:min|mins|minutes)|i have (?:half an hour|an hour|one hour))\b",
    re.IGNORECASE,
)
_COURSE_RE = re.compile(
    r"\b(?:create|make|build) (?:me )?(?:a )?course\b|"
    r"\bteach (?:this|it) in (?:the )?(?:ai )?classroom\b|"
    r"\bturn (?:this|it) into (?:a )?(?:class|course|lesson)\b|"
    r"\bopen (?:this|it) in (?:the )?(?:ai )?classroom\b",
    re.IGNORECASE,
)
_FLASHCARD_RE = re.compile(
    r"\b(?:make|create|give me) (?:some )?flashcards?\b|\bflashcards? (?:from|on)\b",
    re.IGNORECASE,
)
_SUMMARY_RE = re.compile(
    r"\b(?:summari[sz]e|summary|tl;dr|key points|main points|"
    r"resume|resumen|resumir)\b",
    re.IGNORECASE,
)
_COMPARE_RE = re.compile(
    r"\b(?:compare|comparison|versus|vs\.?|difference between|pros and cons|"
    r"compara|diferencia entre)\b",
    re.IGNORECASE,
)
_SEARCH_RE = re.compile(
    r"\b(?:search (?:the )?(?:web|internet)|look (?:this|it) up|find current|"
    r"latest|today's|current price|current news|busca en internet)\b",
    re.IGNORECASE,
)
_TEACH_RE = re.compile(
    r"\b(?:teach me|walk me through|lesson on|help me learn|"
    r"ens[eé][nñ]ame|quiero aprender)\b",
    re.IGNORECASE,
)
_EXPLAIN_RE = re.compile(
    r"\b(?:explain|why does|how does|how do|what does .* mean|"
    r"expl[ií]ca|por qu[eé]|c[oó]mo funciona)\b",
    re.IGNORECASE,
)
_ANALYZE_RE = re.compile(
    r"\b(?:analy[sz]e|analize|review this|inspect|interpret|identify|"
    r"what is this|what are these|what does this (?:say|show)|"
    r"analiza|revisa|interpreta|qu[eé] es esto|qu[eé] dice esto)\b",
    re.IGNORECASE,
)
_CONTINUE_RE = re.compile(
    r"^\s*(?:continue|keep going|go on|next|more|go deeper|tell me more|show an example|show visually|sigue|contin[uú]a|pr[oó]ximo)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_DIRECT_ANSWER_RE = re.compile(
    r"\b(?:just answer|just tell me|give me the answer|answer directly|"
    r"what is|who is|when is|where is|define|dime directamente|solo dime)\b",
    re.IGNORECASE,
)


def _depth_for(text: str) -> ResponseDepth:
    if _DEEP_RE.search(text):
        return ResponseDepth.DEEP
    if _CONCISE_RE.search(text):
        return ResponseDepth.CONCISE
    return ResponseDepth.STANDARD


def interaction_contract_for_request(
    *,
    text: str,
    routed_intent: Optional[Intent] = None,
    has_media: bool = False,
    has_current_media: bool = False,
    voice_mode: bool = False,
    voice_interrupted_previous_turn: bool = False,
) -> InteractionContract:
    """Return the learner's authoritative interaction contract.

    Explicit workflow language wins first. Then attachment verbs, explicit
    interaction verbs, and finally the router's coarse intent are considered.
    """
    text = (text or "").strip()
    depth = _depth_for(text)
    delivery_mode = DeliveryMode.VOICE if voice_mode else DeliveryMode.TEXT
    delivery_metadata = {
        "delivery_mode": delivery_mode,
        "voice_interrupted_previous_turn": bool(voice_mode and voice_interrupted_previous_turn),
    }

    if _TEST_PREP_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.WORKFLOW,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            workflow_intent=Intent.TEST_PREP,
            attachment_authoritative=has_media,
            reason_code="explicit_test_prep",
        )
    if _COACH_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.WORKFLOW,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            workflow_intent=Intent.COACH,
            attachment_authoritative=False,
            reason_code="explicit_coach",
        )
    if _COURSE_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.CREATE,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            workflow_intent=Intent.COURSE,
            attachment_authoritative=has_media,
            reason_code="explicit_course_or_classroom",
        )
    if _FLASHCARD_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.CREATE,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            workflow_intent=Intent.FLASHCARDS,
            attachment_authoritative=has_media,
            reason_code="explicit_flashcards",
        )
    if _QUIZ_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.QUIZ,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            workflow_intent=Intent.QUIZ,
            attachment_authoritative=has_media,
            reason_code="explicit_quiz",
        )

    if _SEARCH_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.SEARCH,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            reason_code="explicit_search",
        )
    if _CONTINUE_RE.search(text):
        lowered = text.casefold()
        continuation_directives = []
        if "show visually" in lowered:
            continuation_directives.append(
                "Use the clearest visual/structured representation available "
                "(diagram, table, sequence, or worked layout) rather than more prose."
            )
        if "show an example" in lowered:
            continuation_directives.append(
                "Give one concrete worked example that directly extends the prior answer."
            )
        if "go deeper" in lowered or "tell me more" in lowered:
            continuation_directives.append(
                "Continue from the prior answer without repeating its introduction."
            )
        return InteractionContract(
            mode=InteractionMode.CONTINUE,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            attachment_authoritative=has_media,
            reason_code="explicit_continue",
            directives=tuple(continuation_directives),
        )
    if _COMPARE_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.COMPARE,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            attachment_authoritative=has_media,
            reason_code="explicit_compare",
        )
    if _SUMMARY_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.SUMMARIZE,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            attachment_authoritative=has_media,
            reason_code="explicit_summary",
        )
    if has_media and (has_current_media or _ANALYZE_RE.search(text) or _EXPLAIN_RE.search(text)):
        return InteractionContract(
            mode=InteractionMode.ANALYZE,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            attachment_authoritative=True,
            reason_code="attachment_analysis",
            directives=(
                "Inspect the supplied material before answering.",
                "Answer the learner's request before offering instruction or assessment.",
            ),
        )
    if _TEACH_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.TEACH,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            reason_code="explicit_teach",
        )
    if _EXPLAIN_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.EXPLAIN,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            attachment_authoritative=has_media,
            reason_code="explicit_explain",
        )
    if _ANALYZE_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.ANALYZE,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            attachment_authoritative=has_media,
            reason_code="explicit_analyze",
        )
    if _DIRECT_ANSWER_RE.search(text):
        return InteractionContract(
            mode=InteractionMode.ANSWER,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            attachment_authoritative=has_media,
            reason_code="explicit_answer",
        )

    # Only after all explicit learner-authored verbs have been checked may
    # the probabilistic router supply a fallback activity. This prevents a
    # router guess such as QUIZ from overriding "explain photosynthesis".
    if routed_intent == Intent.TEST_PREP:
        return InteractionContract(
            mode=InteractionMode.WORKFLOW,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            workflow_intent=Intent.TEST_PREP,
            attachment_authoritative=has_media,
            reason_code="routed_test_prep",
        )
    if routed_intent == Intent.COACH:
        return InteractionContract(
            mode=InteractionMode.WORKFLOW,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            workflow_intent=Intent.COACH,
            attachment_authoritative=False,
            reason_code="routed_coach",
        )
    if routed_intent == Intent.COURSE:
        return InteractionContract(
            mode=InteractionMode.CREATE,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            workflow_intent=Intent.COURSE,
            attachment_authoritative=has_media,
            reason_code="routed_course",
        )
    if routed_intent == Intent.FLASHCARDS:
        return InteractionContract(
            mode=InteractionMode.CREATE,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            workflow_intent=Intent.FLASHCARDS,
            attachment_authoritative=has_media,
            reason_code="routed_flashcards",
        )
    if routed_intent == Intent.QUIZ:
        return InteractionContract(
            mode=InteractionMode.QUIZ,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            workflow_intent=Intent.QUIZ,
            attachment_authoritative=has_media,
            reason_code="routed_quiz",
        )
    if routed_intent == Intent.EXPLAIN:
        return InteractionContract(
            mode=InteractionMode.EXPLAIN,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            attachment_authoritative=has_media,
            reason_code="routed_explain",
        )
    if routed_intent == Intent.SUMMARIZE_NOTES:
        return InteractionContract(
            mode=InteractionMode.SUMMARIZE,
            depth=depth,
            **delivery_metadata,
            fast_lane=True,
            attachment_authoritative=has_media,
            reason_code="routed_summarize",
        )
    if routed_intent in {
        Intent.STUDY_PLAN,
        Intent.SCHEDULE_REMINDERS,
        Intent.COMMUNITY,
        Intent.MODIFY_ARTIFACT,
        Intent.REFLECT,
        Intent.WEEKLY_REVIEW,
    }:
        return InteractionContract(
            mode=InteractionMode.WORKFLOW,
            depth=depth,
            **delivery_metadata,
            fast_lane=False,
            workflow_intent=routed_intent,
            attachment_authoritative=has_media,
            reason_code="routed_workflow",
        )

    return InteractionContract(
        mode=InteractionMode.ANSWER,
        depth=depth,
        **delivery_metadata,
        fast_lane=True,
        attachment_authoritative=has_media and has_current_media,
        reason_code="default_answer",
    )


def contract_prompt(contract: InteractionContract) -> str:
    """Bounded, model-facing form of the interaction contract."""
    depth_rules = {
        ResponseDepth.CONCISE: "Answer in the shortest complete form; usually 1-2 short paragraphs.",
        ResponseDepth.STANDARD: "Give a concise but complete answer; usually 2-4 short paragraphs.",
        ResponseDepth.DEEP: "Go deeper: explain reasoning, implications, and a concrete example without padding.",
    }
    rules = [
        f"Mode: {contract.mode.value}",
        f"Depth: {contract.depth.value}",
        f"Delivery: {contract.delivery_mode.value}",
        depth_rules[contract.depth],
        "The interaction mode is authoritative. Do not silently change it into a different activity.",
    ]
    if contract.delivery_mode is DeliveryMode.VOICE:
        rules.extend([
            "This is a live spoken turn. Sound natural when read aloud.",
            "Prefer short clauses and compact answers; avoid markdown tables, long headings, or dense bullet lists.",
            "Do not announce interaction mechanics, policies, or that you are in voice mode.",
            "End cleanly so the learner can take the floor; do not append a forced quiz or generic follow-up question.",
        ])
    if contract.delivery_mode is DeliveryMode.VOICE and contract.voice_interrupted_previous_turn:
        rules.append("The learner interrupted the previous spoken answer. Follow the new request without restarting the old answer.")
    if contract.attachment_authoritative:
        rules.append("The attachment is authoritative context for this turn; inspect it before answering.")
    rules.extend(contract.directives)
    return "\n".join(f"- {rule}" for rule in rules)
