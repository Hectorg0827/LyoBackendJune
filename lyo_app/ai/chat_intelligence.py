"""Deterministic chat interaction contract and context helpers.

This module sits above routing and pedagogy. It answers one question before
any model gets creative: what did the learner explicitly ask Lyo to *do*?

The contract is intentionally small and inspectable. Router classification,
teaching policy, planners, memory, and presentation may enrich a turn, but
they must not silently change an explicit answer/explain/analyze/quiz/create
request into another interaction shape.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional

from lyo_app.ai.schemas.lyo2 import Intent, RouterDecision
from lyo_app.ai.schemas.smart_block import SmartBlock


class InteractionMode(str, Enum):
    ANSWER = "answer"
    EXPLAIN = "explain"
    ANALYZE = "analyze"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    TEACH = "teach"
    QUIZ = "quiz"
    CREATE = "create"
    TEST_PREP = "test_prep"
    FLASHCARDS = "flashcards"
    STUDY_PLAN = "study_plan"
    SEARCH = "search"
    CONTINUE = "continue"
    CLARIFY = "clarify"
    CONVERSE = "converse"
    UNKNOWN = "unknown"


class ResponseDepth(str, Enum):
    CONCISE = "concise"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass(frozen=True)
class InteractionContract:
    mode: InteractionMode
    confidence: float
    answer_first: bool
    allow_assessment: bool
    fast_lane: bool
    response_depth: ResponseDepth = ResponseDepth.STANDARD
    router_intent: Optional[Intent] = None
    reason: str = "fallback"
    attachment_referential: bool = False

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        payload["response_depth"] = self.response_depth.value
        payload["router_intent"] = self.router_intent.value if self.router_intent else None
        return payload


_DEEP_RE = re.compile(
    r"\b(deep dive|in depth|in-depth|detailed|detail|thorough|comprehensive|"
    r"explain deeply|go deeper|profund[oa]|detallad[oa]|a fondo)\b",
    re.IGNORECASE,
)
_CONCISE_RE = re.compile(
    r"\b(brief|briefly|short|shortly|quick|quickly|concise|tl;?dr|"
    r"resumen corto|breve|r[aá]pido)\b",
    re.IGNORECASE,
)
_QUIZ_RE = re.compile(
    r"\b(quiz me|test me|give me a quiz|make (?:me )?a quiz|practice questions?|"
    r"preg[uú]ntame|hazme (?:un )?(?:quiz|examen)|ponme a prueba)\b",
    re.IGNORECASE,
)
_COURSE_RE = re.compile(
    r"^\s*(?:(?:please\s+)?(?:create|make|build|generate)\s+(?:me\s+)?(?:a\s+)?"
    r"(?:course|curriculum)|i\s+(?:want|need)\s+(?:a\s+)?(?:course|curriculum)|"
    r"(?:course|curriculum)\s+(?:on|about|for)\b)",
    re.IGNORECASE,
)
_TEACH_RE = re.compile(
    r"\b(teach me|walk me through|tutor me|teach this|turn this into a lesson|"
    r"ens[eé][nñ]ame|dame una clase|expl[ií]camelo como clase)\b",
    re.IGNORECASE,
)
_TEST_PREP_RE = re.compile(
    r"\b(i have (?:a )?(?:test|exam)|prepare me for (?:my )?(?:test|exam)|"
    r"test prep|use (?:this|it) for test prep|study for (?:my )?(?:test|exam)|"
    r"tengo (?:un )?examen|prep[aá]rame para (?:el|mi) examen)\b",
    re.IGNORECASE,
)
_FLASHCARDS_RE = re.compile(
    r"\b(flashcards?|flash cards?|make cards|tarjetas de estudio)\b",
    re.IGNORECASE,
)
_STUDY_PLAN_RE = re.compile(
    r"\b(study plan|study schedule|learning plan|revision plan|plan de estudio)\b",
    re.IGNORECASE,
)
_SUMMARY_RE = re.compile(
    r"\b(summarize|summarise|summary|sum up|tl;?dr|resume|resumen)\b",
    re.IGNORECASE,
)
_COMPARE_RE = re.compile(
    r"\b(compare|comparison|versus|vs\.?|difference between|differences? between|"
    r"compara|comparaci[oó]n|diferencia entre)\b",
    re.IGNORECASE,
)
_ANALYZE_RE = re.compile(
    r"\b(analy[sz]e|analize|review this|inspect|interpret|what does this (?:show|say|mean)|"
    r"what is this|what['’]?s this|describe this|read this|"
    r"analiza|revisa|interpreta|qu[eé] es esto|qu[eé] dice esto)\b",
    re.IGNORECASE,
)
_EXPLAIN_RE = re.compile(
    r"\b(explain|explain this|what does .* mean|why does|how does|"
    r"help me understand|expl[ií]came|qu[eé] significa|por qu[eé])\b",
    re.IGNORECASE,
)
_DIRECT_QUESTION_RE = re.compile(
    r"^\s*(what|who|when|where|why|how|which|is|are|can|could|does|do|did|"
    r"qu[eé]|qui[eé]n|cu[aá]ndo|d[oó]nde|por qu[eé]|c[oó]mo|cu[aá]l)\b",
    re.IGNORECASE,
)
_SEARCH_RE = re.compile(
    r"\b(search|look up|find online|latest|current information|web search|"
    r"busca|buscar en internet|informaci[oó]n actual)\b",
    re.IGNORECASE,
)
_CONTINUE_RE = re.compile(
    r"^\s*(continue|keep going|go on|next|resume|contin[uú]a|sigue|pr[oó]ximo)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_ATTACHMENT_REF_RE = re.compile(
    r"\b(this|that|it|attached|attachment|file|document|pdf|image|photo|"
    r"screenshot|page\s+\d+|esto|este documento|archivo|imagen|foto|p[aá]gina\s+\d+)\b",
    re.IGNORECASE,
)


def _depth(text: str) -> ResponseDepth:
    if _DEEP_RE.search(text):
        return ResponseDepth.DEEP
    if _CONCISE_RE.search(text):
        return ResponseDepth.CONCISE
    return ResponseDepth.STANDARD


def derive_interaction_contract(
    text: str | None,
    *,
    has_media: bool = False,
    has_current_media: bool = False,
) -> InteractionContract:
    raw = (text or "").strip()
    depth = _depth(raw)
    attachment_ref = bool(_ATTACHMENT_REF_RE.search(raw))

    def make(
        mode: InteractionMode,
        reason: str,
        *,
        answer_first: bool,
        allow_assessment: bool,
        fast_lane: bool,
        router_intent: Optional[Intent],
        confidence: float = 0.99,
    ) -> InteractionContract:
        return InteractionContract(
            mode=mode,
            confidence=confidence,
            answer_first=answer_first,
            allow_assessment=allow_assessment,
            fast_lane=fast_lane,
            response_depth=depth,
            router_intent=router_intent,
            reason=reason,
            attachment_referential=attachment_ref,
        )

    # Workflow ownership comes before generic verbs such as "explain".
    if _TEST_PREP_RE.search(raw):
        return make(
            InteractionMode.TEST_PREP, "explicit_test_prep",
            answer_first=False, allow_assessment=True, fast_lane=False,
            router_intent=Intent.TEST_PREP,
        )
    if _COURSE_RE.search(raw):
        return make(
            InteractionMode.CREATE, "explicit_course_creation",
            answer_first=False, allow_assessment=False, fast_lane=False,
            router_intent=Intent.COURSE,
        )
    if _QUIZ_RE.search(raw):
        return make(
            InteractionMode.QUIZ, "explicit_quiz",
            answer_first=False, allow_assessment=True, fast_lane=False,
            router_intent=Intent.QUIZ,
        )
    if _FLASHCARDS_RE.search(raw):
        return make(
            InteractionMode.FLASHCARDS, "explicit_flashcards",
            answer_first=False, allow_assessment=True, fast_lane=False,
            router_intent=Intent.FLASHCARDS,
        )
    if _STUDY_PLAN_RE.search(raw):
        return make(
            InteractionMode.STUDY_PLAN, "explicit_study_plan",
            answer_first=False, allow_assessment=False, fast_lane=False,
            router_intent=Intent.STUDY_PLAN,
        )
    if _TEACH_RE.search(raw):
        if has_media and attachment_ref:
            return make(
                InteractionMode.TEACH, "attachment_to_classroom",
                answer_first=False, allow_assessment=True, fast_lane=False,
                router_intent=Intent.COURSE,
            )
        return make(
            InteractionMode.TEACH, "explicit_teaching",
            answer_first=False, allow_assessment=True, fast_lane=False,
            router_intent=Intent.EXPLAIN,
        )

    # A current attachment supplies the referent. Inspection is answer-first.
    if has_media and (has_current_media or attachment_ref):
        if _SUMMARY_RE.search(raw):
            return make(
                InteractionMode.SUMMARIZE, "attachment_summary",
                answer_first=True, allow_assessment=False, fast_lane=True,
                router_intent=Intent.SUMMARIZE_NOTES,
            )
        if _COMPARE_RE.search(raw):
            return make(
                InteractionMode.COMPARE, "attachment_comparison",
                answer_first=True, allow_assessment=False, fast_lane=True,
                router_intent=Intent.EXPLAIN,
            )
        if _ANALYZE_RE.search(raw) or _EXPLAIN_RE.search(raw) or _DIRECT_QUESTION_RE.search(raw) or not raw:
            return make(
                InteractionMode.ANALYZE, "attachment_information_request",
                answer_first=True, allow_assessment=False, fast_lane=True,
                router_intent=Intent.EXPLAIN,
            )

    if _SEARCH_RE.search(raw):
        return make(
            InteractionMode.SEARCH, "explicit_search",
            answer_first=True, allow_assessment=False, fast_lane=False,
            router_intent=Intent.GENERAL,
        )
    if _SUMMARY_RE.search(raw):
        return make(
            InteractionMode.SUMMARIZE, "explicit_summary",
            answer_first=True, allow_assessment=False, fast_lane=True,
            router_intent=Intent.SUMMARIZE_NOTES,
        )
    if _COMPARE_RE.search(raw):
        return make(
            InteractionMode.COMPARE, "explicit_comparison",
            answer_first=True, allow_assessment=False, fast_lane=True,
            router_intent=Intent.EXPLAIN,
        )
    if _EXPLAIN_RE.search(raw):
        return make(
            InteractionMode.EXPLAIN, "explicit_explanation",
            answer_first=True, allow_assessment=False, fast_lane=True,
            router_intent=Intent.EXPLAIN,
        )
    if _CONTINUE_RE.search(raw):
        return make(
            InteractionMode.CONTINUE, "explicit_continuation",
            answer_first=False, allow_assessment=True, fast_lane=False,
            router_intent=None,
            confidence=0.95,
        )
    if _DIRECT_QUESTION_RE.search(raw):
        return make(
            InteractionMode.ANSWER, "direct_question",
            answer_first=True, allow_assessment=False, fast_lane=True,
            router_intent=Intent.EXPLAIN,
            confidence=0.98,
        )

    return make(
        InteractionMode.UNKNOWN, "router_required",
        answer_first=False, allow_assessment=True, fast_lane=False,
        router_intent=None, confidence=0.40,
    )


def enforce_interaction_contract(
    decision: RouterDecision,
    contract: InteractionContract,
) -> RouterDecision:
    """Return a router decision that cannot contradict explicit user intent."""
    if contract.router_intent is None or contract.confidence < 0.95:
        return decision

    payload = decision.model_dump()
    payload.update(
        intent=contract.router_intent,
        confidence=max(float(decision.confidence or 0.0), contract.confidence),
    )
    if contract.answer_first:
        payload["needs_clarification"] = False
        payload["clarification_question"] = None
    return RouterDecision.model_validate(payload)


def response_word_budget(contract: InteractionContract) -> int:
    if contract.response_depth is ResponseDepth.CONCISE:
        return 100
    if contract.response_depth is ResponseDepth.DEEP:
        return 450
    return 220


def contract_directives(contract: InteractionContract) -> List[str]:
    directives: List[str] = [
        f"Interaction contract: {contract.mode.value}. Do not change it into another interaction mode.",
    ]
    if contract.answer_first:
        directives += [
            "Answer the user's explicit request before offering any exercise, quiz, or follow-up.",
            "Do not ask a calibration question unless the requested task is impossible without missing information.",
        ]
    if not contract.allow_assessment:
        directives.append("Do not assess or quiz the learner in this turn unless they explicitly ask for it.")
    if contract.response_depth is ResponseDepth.CONCISE:
        directives.append("Keep the answer compact: lead with the answer and omit optional detail.")
    elif contract.response_depth is ResponseDepth.DEEP:
        directives.append("Give a thorough explanation with structure, examples, and the important caveats.")
    else:
        directives.append("Use moderate depth: enough to be useful without turning the answer into a lecture.")
    if contract.mode is InteractionMode.COMPARE:
        directives.append("Use a compact comparison table when it materially improves clarity.")
    if contract.mode is InteractionMode.ANALYZE:
        directives.append("Ground claims in the attached material and distinguish observation from inference.")
    return directives


def contextual_action_labels(
    contract: InteractionContract,
    *,
    has_media: bool,
) -> List[str]:
    if contract.mode in {InteractionMode.ANALYZE, InteractionMode.SUMMARIZE} and has_media:
        return ["Explain deeper", "Teach this", "Use this for Test Prep"]
    if contract.mode is InteractionMode.COMPARE:
        return ["Explain the key difference", "Show visually", "Quiz me on this"]
    if contract.mode in {InteractionMode.ANSWER, InteractionMode.EXPLAIN}:
        return ["Explain deeper", "Show visually", "Teach me this"]
    if contract.mode is InteractionMode.TEACH:
        return ["Show visually", "Give me an example", "Quiz me"]
    if contract.mode is InteractionMode.QUIZ:
        return ["Explain the answer", "Try harder questions", "Teach the weak spot"]
    if contract.mode is InteractionMode.TEST_PREP:
        return ["Start studying", "Use my materials", "Quiz me"]
    return []


def _extract_markdown_table(text: str) -> Optional[str]:
    lines = [line.rstrip() for line in (text or "").splitlines()]
    for i in range(len(lines) - 1):
        if "|" not in lines[i]:
            continue
        separator = lines[i + 1].strip()
        if not re.fullmatch(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?", separator):
            continue
        table = [lines[i], lines[i + 1]]
        for line in lines[i + 2:]:
            if "|" not in line or not line.strip():
                break
            table.append(line)
        return "\n".join(table)
    return None


def prose_without_presented_table(text: str) -> str:
    """Remove a markdown table that is rendered as its own SmartBlock.

    This prevents the workspace from showing the same comparison twice: once
    as markdown inside the prose block and again as the richer table block.
    """
    lines = (text or "").splitlines()
    start = None
    end = None
    for i in range(len(lines) - 1):
        if "|" not in lines[i]:
            continue
        separator = lines[i + 1].strip()
        if not re.fullmatch(
            r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?",
            separator,
        ):
            continue
        start = i
        end = i + 2
        while end < len(lines) and "|" in lines[end] and lines[end].strip():
            end += 1
        break
    if start is None or end is None:
        return (text or "").strip()
    remaining = lines[:start] + lines[end:]
    return "\n".join(remaining).strip()


def _extract_numbered_steps(text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for line in (text or "").splitlines():
        match = re.match(r"^\s*(\d+)[.)]\s+(.+)$", line)
        if not match:
            continue
        detail = match.group(2).strip()
        if detail:
            items.append({"label": f"Step {match.group(1)}", "detail": detail})
        if len(items) == 8:
            break
    return items


def presentation_blocks(
    *,
    contract: InteractionContract,
    answer_text: str,
    media_attachments: Iterable[Mapping[str, Any]] = (),
) -> List[Dict[str, Any]]:
    """Add useful workspace blocks without replacing the answer prose."""
    blocks: List[Dict[str, Any]] = []

    table = _extract_markdown_table(answer_text)
    if table and contract.mode is InteractionMode.COMPARE:
        blocks.append(SmartBlock.table(table, title="Comparison").model_dump(mode="json"))

    steps = _extract_numbered_steps(answer_text)
    if steps and contract.mode in {InteractionMode.EXPLAIN, InteractionMode.TEACH, InteractionMode.ANALYZE}:
        blocks.append(
            SmartBlock(
                type="interactive",
                subtype="stepByStep",
                content={"title": "Steps", "items": steps},
            ).model_dump(mode="json")
        )

    sources: List[Dict[str, str]] = []
    for attachment in media_attachments:
        name = str(attachment.get("name") or "Attachment")
        pages = attachment.get("source_pages")
        if isinstance(pages, list) and pages:
            page_numbers = [
                str(item.get("page"))
                for item in pages
                if isinstance(item, Mapping) and item.get("page") is not None
            ]
            detail = (
                f"Pages {', '.join(page_numbers[:8])}"
                if page_numbers
                else "Attached document"
            )
        else:
            detail = str(attachment.get("mime_type") or "Attached material")
        sources.append({"label": name, "detail": detail})

    if sources:
        blocks.append(
            SmartBlock(
                type="interactive",
                subtype="notes",
                content={"title": "Source material", "items": sources[:4]},
            ).model_dump(mode="json")
        )

    return blocks


def memory_should_be_personalized(contract: InteractionContract, text: str) -> bool:
    if re.search(
        r"\b(remember|last time|before|again|my progress|my level|my learning|"
        r"you know me|recuerdas|la vez pasada|mi progreso|mi nivel)\b",
        text or "",
        re.IGNORECASE,
    ):
        return True
    return contract.mode in {
        InteractionMode.TEACH,
        InteractionMode.QUIZ,
        InteractionMode.TEST_PREP,
        InteractionMode.STUDY_PLAN,
    }


async def build_memory_layers(
    *,
    db: Any,
    user_id: Any,
    text: str,
    history: Iterable[Mapping[str, Any]],
    contract: InteractionContract,
    learner_snapshot: Optional[Any] = None,
) -> Dict[str, Any]:
    """Return bounded working/learner/personal memory, each independently gated."""
    working: List[Dict[str, str]] = []
    for turn in list(history or [])[-6:]:
        role = str(turn.get("role") or "")
        content = str(turn.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            working.append({"role": role, "content": content[:1200]})

    learner: Dict[str, Any] = {}
    if learner_snapshot is not None:
        learner = {
            "concept_id": getattr(learner_snapshot, "concept_id", None),
            "mastery_score": getattr(learner_snapshot, "mastery_score", None),
            "evidence_state": getattr(learner_snapshot, "evidence_state", None),
            "strongest_rung": getattr(learner_snapshot, "strongest_rung", None),
            "next_rung": getattr(learner_snapshot, "next_rung", None),
            "misconception": getattr(learner_snapshot, "misconception", None),
        }
        learner = {k: v for k, v in learner.items() if v not in (None, "", [])}

    personal = ""
    if (
        db is not None
        and str(user_id or "") not in {"", "0", "None"}
        and memory_should_be_personalized(contract, text)
    ):
        try:
            from lyo_app.services.memory_synthesis import memory_synthesis_service

            user = await memory_synthesis_service._get_user(int(user_id), db)
            summary = str(getattr(user, "user_context_summary", "") or "").strip()
            if summary:
                personal = summary[:3000]
        except Exception:
            personal = ""

    return {
        "working": working,
        "learner": learner,
        "personal": personal,
    }
