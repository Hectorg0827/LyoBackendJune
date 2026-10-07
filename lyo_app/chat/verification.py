"""Selective second-pass verification for canonical Chat.

Simple turns stay on the fast path. Answers with freshness, numerical, or
substantial technical risk can be checked by a small critic before the final
snapshot is persisted.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

_CURRENT_RE = re.compile(
    r"\b(?:today|current|currently|latest|newest|this week|this month|"
    r"price|weather|news|president|ceo|version|release|law|rule|schedule)\b",
    re.IGNORECASE,
)
_TECHNICAL_RE = re.compile(
    r"\b(?:because|causes?|therefore|mechanism|algorithm|equation|formula|"
    r"statistically|probability|physics|chemistry|biology|economics|"
    r"programming|software|database|network|medical|legal|financial)\b",
    re.IGNORECASE,
)
_NUMERIC_CLAIM_RE = re.compile(r"(?<!\w)(?:\$|€|£)?\d+(?:\.\d+)?(?:%|\b)")


@dataclass(frozen=True)
class VerificationResult:
    checked: bool
    revised: bool
    text: str
    reason: str


def should_verify_answer(
    *,
    question: str,
    answer: str,
    interaction_mode: str,
    search_required: bool = False,
) -> bool:
    """Choose verification only where it can materially reduce factual risk."""
    if not answer or len(answer.strip()) < 80:
        return bool(search_required)
    if search_required or interaction_mode == "search":
        return True
    if _CURRENT_RE.search(question or ""):
        return True
    if len(answer) >= 450 and (
        _TECHNICAL_RE.search(question or "")
        or _TECHNICAL_RE.search(answer)
        or _NUMERIC_CLAIM_RE.search(answer)
    ):
        return True
    # Analysis of a source with many factual claims is worth a critic pass.
    if interaction_mode in {"analyze", "compare"} and len(answer) >= 650:
        return True
    return False


def _source_context(
    media_attachments: Iterable[Mapping[str, Any]],
    sources: Iterable[Mapping[str, Any]],
) -> str:
    pieces: list[str] = []
    for source in sources or []:
        if not isinstance(source, Mapping):
            continue
        title = str(source.get("title") or source.get("name") or "Source")
        url = str(source.get("url") or "")
        snippet = str(
            source.get("snippet")
            or source.get("content")
            or source.get("excerpt")
            or ""
        ).strip()[:1000]
        entry = f"- {title}: {url}".strip()
        if snippet:
            entry += f"\n  Evidence: {snippet}"
        pieces.append(entry)

    budget = 6000
    for item in media_attachments or []:
        name = str(item.get("name") or "Attachment")
        for page in item.get("source_pages") or []:
            if not isinstance(page, Mapping):
                continue
            text = str(page.get("text") or "").strip()
            number = page.get("page")
            if not text:
                continue
            snippet = text[:1000]
            pieces.append(f"- {name} page {number}: {snippet}")
            budget -= len(snippet)
            if budget <= 0:
                return "\n".join(pieces)
    return "\n".join(pieces)


async def selectively_verify_answer(
    *,
    question: str,
    answer: str,
    interaction_mode: str,
    media_attachments: Optional[Iterable[Mapping[str, Any]]] = None,
    sources: Optional[Iterable[Mapping[str, Any]]] = None,
    search_required: bool = False,
    timeout_seconds: float = 4.5,
) -> VerificationResult:
    """Run a bounded critic and return either the original or a corrected answer.

    The critic is not asked for chain-of-thought. It either says PASS or returns
    a complete replacement answer after checking factual consistency and source
    support.
    """
    if not should_verify_answer(
        question=question,
        answer=answer,
        interaction_mode=interaction_mode,
        search_required=search_required,
    ):
        return VerificationResult(False, False, answer, "not_required")

    source_list = [
        source for source in (sources or []) if isinstance(source, Mapping)
    ]
    has_fresh_evidence = any(
        str(
            source.get("snippet")
            or source.get("content")
            or source.get("excerpt")
            or ""
        ).strip()
        for source in source_list
    )

    if search_required and not has_fresh_evidence:
        # Native provider grounding often returns titles/URLs only. Run one
        # bounded independent retrieval so the critic checks current claims
        # against evidence instead of its own training cutoff.
        try:
            from lyo_app.ai_agents.multi_agent_v2.tools.web_search_tool import WebSearchTool

            search_result = await asyncio.wait_for(
                WebSearchTool().execute(0, query=question, max_results=5),
                timeout=min(timeout_seconds, 3.5),
            )
            if search_result.success and isinstance(search_result.output, list):
                for item in search_result.output:
                    if not isinstance(item, Mapping):
                        continue
                    snippet = str(
                        item.get("snippet") or item.get("content") or ""
                    ).strip()
                    if not snippet:
                        continue
                    source_list.append(
                        {
                            "title": str(item.get("title") or "Live source"),
                            "url": str(item.get("url") or ""),
                            "snippet": snippet[:1000],
                        }
                    )
                has_fresh_evidence = any(
                    str(source.get("snippet") or "").strip()
                    for source in source_list
                )
        except Exception:
            has_fresh_evidence = False

    if search_required and not has_fresh_evidence:
        return VerificationResult(
            True,
            False,
            answer,
            "fresh_evidence_unavailable",
        )

    context = _source_context(media_attachments or [], source_list)
    prompt = f"""You are a factual verification gate for a learning assistant.
Do not provide reasoning or commentary.

USER REQUEST:
{question}

DRAFT ANSWER:
{answer}

AVAILABLE SOURCE CONTEXT:
{context or "(No source excerpts supplied. Check internal factual consistency only.)"}

Rules:
- If the draft is factually sound and does not overclaim beyond the supplied sources, reply exactly PASS.
- If a material factual error, unsupported current claim, numerical inconsistency, or invented source/page claim exists, reply with:
REVISED:
<complete corrected answer>
- Preserve the user's requested interaction mode and approximate length.
- Do not add a quiz or ask an unnecessary question.
"""

    try:
        from lyo_app.core.ai_resilience import ai_resilience_manager

        response = await asyncio.wait_for(
            ai_resilience_manager.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                provider_order=["gpt-4o-mini", "gemini-2.5-flash"],
                temperature=0.0,
                max_tokens=1200,
                use_cache=False,
            ),
            timeout=timeout_seconds,
        )
        content = str(response.get("content") or "").strip()
    except Exception:
        # Verification must never turn a healthy answer into a failure.
        return VerificationResult(True, False, answer, "critic_unavailable")

    if content == "PASS":
        return VerificationResult(True, False, answer, "passed")
    if content.startswith("REVISED:"):
        revised = content[len("REVISED:"):].strip()
        if revised:
            return VerificationResult(True, True, revised, "revised")
    return VerificationResult(True, False, answer, "critic_malformed")
