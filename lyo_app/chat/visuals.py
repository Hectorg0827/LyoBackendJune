"""Exploratory updates to persisted teaching visuals; never learner grades."""

from copy import deepcopy
from typing import Any

from lyo_app.ai_classroom.teaching_visuals import TeachingVisual


def update_visual_blocks(blocks: list[dict], block_id: str, values: dict) -> tuple[list[dict], dict]:
    """Replace exactly one server-authored visual while preserving other blocks.

    Input is a persisted message, not a new representation supplied by the
    client. Answer keys, checkpoint results, labels and geometry stay owned by
    the server. Reassignment makes SQLAlchemy track the JSON-column update.
    """
    updated = deepcopy(blocks)
    for block in updated:
        if not isinstance(block, dict) or block.get("id") != block_id:
            continue
        if block.get("type") != "interactive" or block.get("subtype") != "teaching_visual":
            raise LookupError("This block is not an exploratory visual")
        content = block.get("content") or {}
        if not isinstance(content, dict):
            raise ValueError("Invalid stored visual content")
        visual = TeachingVisual.model_validate(content.get("visual"))
        allowed = {"parts", "value"} if visual.kind == "fraction_pie" else {"params"} if visual.kind == "graph" else {"value"}
        if not isinstance(values, dict) or not values or set(values) - allowed or not visual.update(values):
            raise ValueError("Invalid exploratory values")
        block["content"] = {
            **content, "visual": visual.model_dump(mode="json"),
            "items": [{"label": visual.title, "detail": visual.description}],
        }
        return updated, block
    raise LookupError("No such visual in this conversation")


async def refresh_message_for_block_update(db: Any, message: Any) -> None:
    """Merge into the current row so a visual edit cannot erase a quiz result.

    PostgreSQL holds a row lock through commit. The same refresh is used by
    quiz-result persistence, so the two writers preserve each other's blocks.
    """
    from lyo_app.chat.models import ChatMessage

    if isinstance(message, ChatMessage):
        await db.refresh(message, attribute_names=["blocks"], with_for_update=True)
