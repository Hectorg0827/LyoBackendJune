"""Progressive hint-leveling (Parity D).

Replaces hardcoded one-shot hints with escalating scaffolding. A learner who
stays stuck gets progressively more support — but never the answer before they
have had a chance to think:

    Level 1  NUDGE          — a gentle pointer ("what are you being asked to find?")
    Level 2  CONCEPT        — remind the underlying concept/rule
    Level 3  WORKED_EXAMPLE — walk a *similar* example end-to-end
    Level 4  NEAR_SOLUTION  — lay out the steps for THIS problem, stopping short
                              of the final answer

The level advances only when the learner remains stuck (the caller passes an
increasing attempt count). Hints are LLM-backed via the resilience manager with
a deterministic per-level template fallback so the feature works offline.
"""
from __future__ import annotations

import logging
from enum import IntEnum
from typing import Optional

logger = logging.getLogger(__name__)


class HintLevel(IntEnum):
    NUDGE = 1
    CONCEPT = 2
    WORKED_EXAMPLE = 3
    NEAR_SOLUTION = 4


# Per-level instruction injected into the LLM prompt + a deterministic fallback.
_LEVEL_SPEC = {
    HintLevel.NUDGE: (
        "Give only a gentle nudge: restate what's being asked and point to where "
        "to start. Do NOT reveal any steps or the answer.",
        "Let's start by being clear about what {concept} is asking for. "
        "What information do you have, and what are you trying to find?",
    ),
    HintLevel.CONCEPT: (
        "Remind the learner of the key concept or rule that applies here. Still "
        "no steps for their specific problem.",
        "Remember the core idea behind {concept}: think about which rule or "
        "relationship connects what you know to what you need.",
    ),
    HintLevel.WORKED_EXAMPLE: (
        "Walk through a SIMILAR (not identical) worked example end to end, so the "
        "learner can map the steps onto their own problem.",
        "Here's a similar example for {concept}: work it step by step, then line "
        "up each step against your own problem and see what matches.",
    ),
    HintLevel.NEAR_SOLUTION: (
        "Lay out the exact steps for THIS problem in order, but stop before the "
        "final computed answer so the learner finishes it themselves.",
        "Let's set up {concept} together: here are the steps in order — now carry "
        "out the last step yourself to reach the answer.",
    ),
}


def hint_level_for_attempt(attempts: int) -> HintLevel:
    """Map the number of times the learner has been stuck to a hint level (1-4)."""
    clamped = max(1, min(int(attempts or 1), len(HintLevel)))
    return HintLevel(clamped)


async def generate_hint(
    level: HintLevel,
    *,
    concept: str,
    question: str = "",
    ai_manager=None,
) -> str:
    """Return a hint at the requested escalation level.

    LLM-backed when an ai_manager is available; otherwise a deterministic
    template so the scaffolding still escalates offline.
    """
    instruction, template = _LEVEL_SPEC[level]

    if ai_manager is not None:
        try:
            prompt = (
                f"You are tutoring a learner on '{concept}'.\n"
                + (f"The problem: {question[:500]}\n" if question else "")
                + f"\nHint level {int(level)} of 4. {instruction}\n"
                "Keep it to 1-3 sentences. Be encouraging, never condescending."
            )
            resp = await ai_manager.chat_completion(
                messages=[
                    {"role": "system", "content": "You give scaffolded, level-appropriate hints."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=200,
            )
            # Ignore the resilience manager's generic "all providers failed"
            # fallback so we escalate with our level-appropriate template instead.
            if resp and not resp.get("is_fallback"):
                content = resp.get("content") or resp.get("text")
                if content and content.strip():
                    return content.strip()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"progressive hint LLM unavailable (level {int(level)}): {e}")

    return template.format(concept=concept or "this problem")
