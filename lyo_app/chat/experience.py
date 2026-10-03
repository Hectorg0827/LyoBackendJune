"""Deterministic chat experience contract.

This module sits between intent routing and pedagogy/planning.  It answers one
product-level question before any downstream system runs: *what interaction did
the learner actually ask for?*

The contract is deliberately small, inspectable, and model-independent.  It is
used by Chat to:
- keep explicit user intent authoritative over pedagogical defaults,
- decide whether a turn can take the low-latency direct-generation lane,
- select a response depth and representation,
- decide whether live web grounding is required,
- bound which memory scopes are eligible for the turn, and
- generate contextually useful continuation actions.

The router is still useful for semantic classification.  The contract is the
guardrail that prevents later layers from silently changing the interaction
shape.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

from lyo_app.ai.schemas.lyo2 import Intent


class InteractionMode(str, Enum):
    ANSWER = "answer"
    ANALYZE = "analyze"
    EXPLAIN = "explain"
    TEACH = "teach"
    QUIZ = "quiz"
    CREATE = "create"
    COMPARE = "compare"
    SEARCH = "search"
    CONTINUE = "continue"
    CLARIFY = "clarify"


class ResponseDepth(str, Enum):
    CONCISE = "concise"
    STANDARD = "standard"
    DEEP = "deep"


class ResponseRepresentation(str, Enum):
    PROSE = "prose"
    BULLETS = "bullets"
    TABLE = "table"
    TIMELINE = "timeline"
    DIAGRAM = "diagram"
    WORKED_EXAMPLE = "worked_example"
    DOCUMENT = "document"


class MemoryScope(str, Enum):
    WORKING = "working"
    LEARNER = "learner"
    PERSONAL = "personal"


class InteractionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: InteractionMode
    depth: ResponseDepth = ResponseDepth.STANDARD
    representation: ResponseRepresentation = ResponseRepresentation.PROSE
    fast_lane: bool = False
    requires_search: bool = False
    workflow_intent: Optional[Intent] = None
    memory_scopes: list[MemoryScope] = Field(
        default_factory=lambda: [MemoryScope.WORKING]
    )
    suggested_actions: list[str] = Field(default_factory=list)
    explicit_user_control: bool = False
    depth_explicit: bool = False
    reason_code: str = "router_default"

    def prompt_directives(self) -> list[str]:
        directives = [
            f"Interaction contract: {self.mode.value}. Do not change it into a different interaction.",
            f"Response depth: {self.depth.value}.",
            f"Preferred representation: {self.representation.value}.",
        ]
        if self.mode in {
            InteractionMode.ANSWER,
            InteractionMode.ANALYZE,
            InteractionMode.COMPARE,
            InteractionMode.SEARCH,
        }:
            directives.append(
                "Answer the learner's request before offering any assessment or follow-up."
            )
        if self.mode == InteractionMode.QUIZ:
            directives.append("Ask/continue the requested assessment; do not replace it with a lecture.")
        if self.mode == InteractionMode.TEACH:
            directives.append("Teach interactively; learner action may be used when it serves the lesson.")
        if self.requires_search:
            directives.append(
                "Use the supplied live-search evidence for time-sensitive claims and cite its source numbers."
            )
        return directives


_DIRECT_ANSWER_RE = re.compile(
    r"\b(?:just\s+(?:answer|tell|say)|give\s+me\s+(?:the\s+)?answer|"
    r"answer\s+(?:this|me)|tell\s+me\s+directly|solo\s+dime|dame\s+la\s+respuesta)\b",
    re.IGNORECASE,
)
_ANALYZE_RE = re.compile(
    r"\b(?:analy[sz]e|analize|summari[sz]e|review|inspect|read|interpret|"
    r"what\s+(?:is|does)\s+this|what['’]?s\s+this|what\s+does\s+(?:this|it)\s+say|"
    r"analiza|resume|revisa|lee|interpreta|qu[eé]\s+es\s+esto|qu[eé]\s+dice)\b",
    re.IGNORECASE,
)
_EXPLAIN_RE = re.compile(
    r"\b(?:explain|why\s+does|why\s+is|how\s+does|help\s+me\s+understand|"
    r"explica|expl[ií]came|por\s+qu[eé]|c[oó]mo\s+funciona)\b",
    re.IGNORECASE,
)
_TEACH_RE = re.compile(
    r"\b(?:teach\s+me|walk\s+me\s+through|tutor\s+me|learn\s+(?:this|about)|"
    r"ens[eé][nñ]ame|gu[ií]ame|quiero\s+aprender)\b",
    re.IGNORECASE,
)
_QUIZ_RE = re.compile(
    r"\b(?:quiz\s+me|test\s+me|give\s+me\s+(?:a\s+)?quiz|practice\s+questions?|"
    r"hazme\s+(?:un\s+)?(?:quiz|examen)|ponme\s+a\s+prueba)\b",
    re.IGNORECASE,
)
_COMPARE_RE = re.compile(
    r"\b(?:compare|comparison|difference\s+between|versus|\bvs\.?\b|"
    r"compara|comparaci[oó]n|diferencia\s+entre)\b",
    re.IGNORECASE,
)
_SEARCH_RE = re.compile(
    r"\b(?:search\s+(?:the\s+)?web|look\s+up|find\s+online|latest|today|current|"
    r"right\s+now|recent|as\s+of\s+today|news|precio\s+actual|hoy|actual|"
    r"m[aá]s\s+reciente|[uú]ltim[oa]s?)\b",
    re.IGNORECASE,
)
_CONTINUE_RE = re.compile(
    r"^\s*(?:continue|keep\s+going|go\s+on|next|resume|contin[uú]a|sigue|pr[oó]ximo)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_CLASSROOM_RE = re.compile(
    r"\b(?:classroom|ai\s+class|class\s+on\s+this|teach\s+this\s+in\s+class|"
    r"aula|clase\s+de\s+esto)\b",
    re.IGNORECASE,
)
_COURSE_RE = re.compile(
    r"\b(?:create|make|build)\s+(?:me\s+)?(?:a\s+)?course\b|\bcourse\s+(?:on|about|from)\b",
    re.IGNORECASE,
)
_TEST_PREP_RE = re.compile(
    r"\b(?:i\s+have\s+(?:a\s+)?(?:test|exam)|test\s+prep|prepare\s+(?:me\s+)?for\s+(?:my\s+)?(?:test|exam)|"
    r"use\s+(?:this|it)\s+for\s+test\s+prep|tengo\s+(?:un\s+)?examen|preparame\s+para\s+el\s+examen)\b",
    re.IGNORECASE,
)
_FLASHCARDS_RE = re.compile(r"\b(?:flashcards?|tarjetas\s+de\s+estudio)\b", re.IGNORECASE)
_DEEP_RE = re.compile(
    r"\b(?:deep\s+dive|go\s+deeper|more\s+detail|detailed|in\s+depth|advanced|"
    r"profundiza|m[aá]s\s+detalle|a\s+fondo)\b",
    re.IGNORECASE,
)
_CONCISE_RE = re.compile(
    r"\b(?:brief|short|concise|quick|tl;?dr|one\s+sentence|keep\s+it\s+short|"
    r"breve|corto|conciso|r[aá]pido)\b",
    re.IGNORECASE,
)
_VISUAL_RE = re.compile(
    r"\b(?:show\s+visually|visual|diagram|draw|map\s+it|flowchart|"
    r"diagrama|visual|dib[uú]jalo)\b",
    re.IGNORECASE,
)
_TIMELINE_RE = re.compile(r"\b(?:timeline|chronolog|history\s+of|l[ií]nea\s+de\s+tiempo)\b", re.IGNORECASE)
_MATH_RE = re.compile(
    r"(?:\bsolve\b|\bcalculate\b|\bequation\b|\bformula\b|\bmath\b|\balgebra\b|"
    r"\bderivative\b|\bintegral\b|\bresuelve\b|\becuaci[oó]n\b|\bf[oó]rmula\b)",
    re.IGNORECASE,
)
_PERSONAL_MEMORY_RE = re.compile(
    r"\b(?:remember\s+(?:when|that|what)|last\s+time|previously|before\s+we|"
    r"my\s+(?:goal|preference|learning\s+style|usual|plan)|continue\s+where\s+we\s+left|"
    r"you\s+know\s+(?:me|that\s+i)|recuerdas|la\s+vez\s+pasada|mi\s+(?:meta|preferencia))\b",
    re.IGNORECASE,
)
_LEARNER_MEMORY_RE = re.compile(
    r"\b(?:how\s+am\s+i\s+doing|my\s+progress|what\s+am\s+i\s+weak|"
    r"what\s+do\s+i\s+know|my\s+mastery|mis\s+progresos|c[oó]mo\s+voy)\b",
    re.IGNORECASE,
)


def merged_chat_state(
    state_summary: Optional[Mapping[str, Any]],
    conversation_context: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    """Merge server-owned Chat preferences without overriding this client turn.

    Conversation context is the cross-device fallback. A client may explicitly
    send a preference for the current turn; that newer value wins.
    """
    merged = dict(conversation_context or {})
    incoming = dict(state_summary or {})
    merged.update(incoming)

    stored_prefs = (
        dict((conversation_context or {}).get("chat_preferences") or {})
        if isinstance(conversation_context, Mapping)
        else {}
    )
    incoming_prefs = (
        dict((state_summary or {}).get("chat_preferences") or {})
        if isinstance(state_summary, Mapping)
        else {}
    )
    prefs = {**stored_prefs, **incoming_prefs}
    if prefs:
        merged["chat_preferences"] = prefs
    return merged


def context_with_response_depth(
    conversation_context: Optional[Mapping[str, Any]],
    depth: ResponseDepth,
) -> dict[str, Any]:
    """Return a reassigned JSON payload so SQLAlchemy persists the change."""
    context = dict(conversation_context or {})
    preferences = dict(context.get("chat_preferences") or {})
    preferences["response_depth"] = depth.value
    context["chat_preferences"] = preferences
    return context


def _state_depth(state_summary: Optional[Mapping[str, Any]]) -> Optional[ResponseDepth]:
    if not isinstance(state_summary, Mapping):
        return None
    prefs = state_summary.get("chat_preferences")
    if not isinstance(prefs, Mapping):
        return None
    raw = str(prefs.get("response_depth") or "").lower().strip()
    try:
        return ResponseDepth(raw) if raw else None
    except ValueError:
        return None


def _router_default_mode(intent: Intent) -> InteractionMode:
    if intent == Intent.QUIZ:
        return InteractionMode.QUIZ
    if intent in {Intent.COURSE, Intent.STUDY_PLAN, Intent.TEST_PREP, Intent.FLASHCARDS}:
        return InteractionMode.CREATE
    if intent in {Intent.EXPLAIN, Intent.SUMMARIZE_NOTES}:
        return InteractionMode.EXPLAIN
    return InteractionMode.ANSWER


def resolve_interaction_contract(
    *,
    user_text: str,
    router_intent: Intent,
    has_media: bool = False,
    has_current_media: bool = False,
    state_summary: Optional[Mapping[str, Any]] = None,
) -> InteractionContract:
    text = (user_text or "").strip()

    depth = _state_depth(state_summary) or ResponseDepth.STANDARD
    explicit_depth = False
    if _DEEP_RE.search(text):
        depth = ResponseDepth.DEEP
        explicit_depth = True
    elif _CONCISE_RE.search(text):
        depth = ResponseDepth.CONCISE
        explicit_depth = True

    workflow_intent: Optional[Intent] = None
    explicit_user_control = bool(_DIRECT_ANSWER_RE.search(text) or explicit_depth)

    # Workflow requests are strongest: they should not be reinterpreted by
    # pedagogy or by a generic attachment-analysis heuristic.
    if _TEST_PREP_RE.search(text):
        mode = InteractionMode.CREATE
        workflow_intent = Intent.TEST_PREP
        reason = "explicit_test_prep"
        explicit_user_control = True
    elif _CLASSROOM_RE.search(text) or _COURSE_RE.search(text):
        mode = InteractionMode.CREATE
        workflow_intent = Intent.COURSE
        reason = "explicit_course_or_classroom"
        explicit_user_control = True
    elif _FLASHCARDS_RE.search(text):
        mode = InteractionMode.CREATE
        workflow_intent = Intent.FLASHCARDS
        reason = "explicit_flashcards"
        explicit_user_control = True
    elif _QUIZ_RE.search(text):
        mode = InteractionMode.QUIZ
        workflow_intent = Intent.QUIZ
        reason = "explicit_quiz"
        explicit_user_control = True
    elif _SEARCH_RE.search(text):
        mode = InteractionMode.SEARCH
        reason = "explicit_or_time_sensitive_search"
        explicit_user_control = True
    elif _COMPARE_RE.search(text):
        mode = InteractionMode.COMPARE
        reason = "explicit_compare"
        explicit_user_control = True
    elif has_media and (has_current_media or _ANALYZE_RE.search(text)):
        mode = InteractionMode.ANALYZE
        reason = "attachment_analysis"
        explicit_user_control = True
    elif _TEACH_RE.search(text):
        mode = InteractionMode.TEACH
        reason = "explicit_teach"
        explicit_user_control = True
    elif _EXPLAIN_RE.search(text):
        mode = InteractionMode.EXPLAIN
        reason = "explicit_explain"
        explicit_user_control = True
    elif _CONTINUE_RE.search(text):
        mode = InteractionMode.CONTINUE
        reason = "explicit_continue"
        explicit_user_control = True
    elif _DIRECT_ANSWER_RE.search(text):
        mode = InteractionMode.ANSWER
        reason = "explicit_direct_answer"
    else:
        mode = _router_default_mode(router_intent)
        reason = "router_default"

    if _VISUAL_RE.search(text):
        representation = ResponseRepresentation.DIAGRAM
    elif mode == InteractionMode.COMPARE:
        representation = ResponseRepresentation.TABLE
    elif _TIMELINE_RE.search(text):
        representation = ResponseRepresentation.TIMELINE
    elif _MATH_RE.search(text) and mode in {InteractionMode.EXPLAIN, InteractionMode.TEACH, InteractionMode.ANSWER}:
        representation = ResponseRepresentation.WORKED_EXAMPLE
    elif mode == InteractionMode.ANALYZE and has_media:
        representation = ResponseRepresentation.DOCUMENT
    elif depth == ResponseDepth.CONCISE:
        representation = ResponseRepresentation.BULLETS
    else:
        representation = ResponseRepresentation.PROSE

    requires_search = mode == InteractionMode.SEARCH

    # Planner-free turns are those where the product already knows the exact
    # operation: produce one grounded response. Search also bypasses the planner
    # but executes a deterministic web-search step before generation.
    fast_lane = mode in {
        InteractionMode.ANSWER,
        InteractionMode.ANALYZE,
        InteractionMode.COMPARE,
        InteractionMode.EXPLAIN,
        InteractionMode.SEARCH,
        InteractionMode.CONTINUE,
    } and workflow_intent is None

    memory_scopes = [MemoryScope.WORKING]
    if mode in {InteractionMode.EXPLAIN, InteractionMode.TEACH, InteractionMode.QUIZ} or _LEARNER_MEMORY_RE.search(text):
        memory_scopes.append(MemoryScope.LEARNER)
    if _PERSONAL_MEMORY_RE.search(text):
        memory_scopes.append(MemoryScope.PERSONAL)

    if has_media:
        suggested_actions = [
            "Explain deeper",
            "Teach this in Classroom",
            "Quiz me on this",
            "Use this for Test Prep",
        ]
    elif mode == InteractionMode.COMPARE:
        suggested_actions = [
            "Explain the differences",
            "Show visually",
            "Quiz me",
        ]
    elif mode in {InteractionMode.EXPLAIN, InteractionMode.ANSWER, InteractionMode.CONTINUE}:
        suggested_actions = [
            "Go deeper",
            "Show visually",
            "Quiz me",
        ]
    elif mode == InteractionMode.SEARCH:
        suggested_actions = [
            "Explain what changed",
            "Go deeper",
            "Quiz me",
        ]
    else:
        suggested_actions = []

    return InteractionContract(
        mode=mode,
        depth=depth,
        representation=representation,
        fast_lane=fast_lane,
        requires_search=requires_search,
        workflow_intent=workflow_intent,
        memory_scopes=memory_scopes,
        suggested_actions=suggested_actions,
        explicit_user_control=explicit_user_control,
        depth_explicit=explicit_depth,
        reason_code=reason,
    )


def effective_intent(contract: InteractionContract, router_intent: Intent) -> Intent:
    """Return the workflow intent the rest of Chat must honor."""
    if contract.workflow_intent is not None:
        return contract.workflow_intent
    if contract.mode == InteractionMode.QUIZ:
        return Intent.QUIZ
    if contract.mode == InteractionMode.EXPLAIN:
        return Intent.EXPLAIN
    if contract.mode == InteractionMode.TEACH:
        return Intent.EXPLAIN
    if contract.mode == InteractionMode.ANALYZE:
        return Intent.SUMMARIZE_NOTES if router_intent == Intent.SUMMARIZE_NOTES else Intent.EXPLAIN
    return router_intent


def fast_lane_plan(contract: InteractionContract, user_text: str):
    """Create the deterministic plan used when no LLM planner is necessary."""
    from lyo_app.ai.schemas.lyo2 import ActionType, LyoPlan, PlannedAction

    steps: list[PlannedAction] = []
    if contract.requires_search:
        steps.append(
            PlannedAction(
                action_type=ActionType.SEARCH_WEB,
                description="Ground the response in current web sources",
                parameters={"query": user_text, "max_results": 5},
            )
        )
    steps.append(
        PlannedAction(
            action_type=ActionType.GENERATE_TEXT,
            description=f"Execute {contract.mode.value} interaction directly",
            parameters={"content": None},
        )
    )
    return LyoPlan(steps=steps, grounding_required=True)
