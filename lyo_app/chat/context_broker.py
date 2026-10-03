"""Selective context broker for Chat.

Chat has three different memory scopes and they should not be conflated:

* working: recent turns in this conversation;
* learner: measured learning state for the current concept/topic;
* personal: synthesized long-term context from prior sessions.

Working memory is always eligible. Learner and personal memory are loaded only
when the interaction contract says they can materially improve this turn.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.chat.experience import InteractionContract, MemoryScope


async def build_context_bundle(
    *,
    db: Optional[AsyncSession],
    user_id: Any,
    contract: InteractionContract,
    concept_id: Optional[str],
    topic: Optional[str],
) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "scopes": [scope.value for scope in contract.memory_scopes],
        "learner": None,
        "personal": None,
    }

    if (
        MemoryScope.LEARNER in contract.memory_scopes
        and db is not None
        and user_id not in (None, "", 0, "0")
    ):
        try:
            from lyo_app.teaching_runtime.service import load_learner_snapshot

            learner = await load_learner_snapshot(
                db,
                user_id,
                concept_id,
                topic=topic,
            )
            # Only measured/bounded fields enter prompts.  No raw event log or
            # arbitrary profile JSON is copied into the model context.
            bundle["learner"] = {
                "concept_id": learner.concept_id,
                "mastery_score": learner.mastery_score,
                "evidence_state": learner.evidence_state,
                "strongest_rung": learner.strongest_rung,
                "next_rung": learner.next_rung,
                "misconception": learner.misconception,
                "attempts": learner.attempts,
                "hints_used": learner.hints_used,
            }
        except Exception:
            # Personalization is additive.  A read failure must never block the
            # learner's immediate request.
            bundle["learner"] = None

    if (
        MemoryScope.PERSONAL in contract.memory_scopes
        and db is not None
        and user_id not in (None, "", 0, "0")
    ):
        try:
            from lyo_app.services.memory_synthesis import memory_synthesis_service

            bundle["personal"] = await memory_synthesis_service.get_memory_for_prompt(
                int(user_id), db
            )
        except Exception:
            bundle["personal"] = None

    return bundle
