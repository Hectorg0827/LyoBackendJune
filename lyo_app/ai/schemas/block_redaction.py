"""Keep grading internals off the wire.

The product's trust rules are explicit: never expose answer keys before
submission, internal expected keywords, or hidden rubrics.

Chat's check block was failing that. `correct_index` and `explanation` were
serialised into the block and streamed to the client along with the question,
and each option carried `reveals` — the misconception tag naming what
choosing it would say about the learner. The client is disciplined about not
grading with them, and a comment in `CheckBlock.tsx` says so. That is not the
point. A learner with the network tab open could read the answer before
choosing, and the misconception tags are internal diagnosis that no learner
should be reading about themselves mid-question.

WHAT STAYS

* `hint` — the learner is meant to be able to ask for it, and asking is
  tracked as evidence rather than punished.
* `bailout_index` — the "just explain it" opt-out has to be visible to be
  chosen.
* `metadata.result` — the verdict, written after the learner answers. It
  legitimately carries the correct index and the explanation, which is how an
  already-answered check still renders correctly after a reload.

The stored block is untouched. Grading happens later against what was
persisted, so redaction is applied on the way out and nowhere else — a
redacted block written back to the database would be an ungradeable one.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

#: Removed from a block's content before it leaves the server.
REDACTED_CONTENT_FIELDS = ("correct_index", "explanation")

#: Removed from each option. `reveals` names the misconception that choosing
#: this option would indicate.
REDACTED_OPTION_FIELDS = ("reveals",)


def redact_content(content: Any) -> Any:
    """Strip grading internals from one block's content payload.

    Separate from `redact_block` because not every way out of the server
    wraps content in a block. The legacy `artifact` event on the planner path
    streams `artifact.content` directly, and redacting only the block-shaped
    exits left the answer key travelling on that one.
    """
    if not isinstance(content, dict):
        return content

    if not any(field in content for field in REDACTED_CONTENT_FIELDS) and not _has_option_secrets(
        content
    ):
        return content

    clean: Dict[str, Any] = {
        key: value
        for key, value in content.items()
        if key not in REDACTED_CONTENT_FIELDS
    }

    options = content.get("options")
    if isinstance(options, list):
        clean["options"] = [
            {k: v for k, v in option.items() if k not in REDACTED_OPTION_FIELDS}
            if isinstance(option, dict)
            else option
            for option in options
        ]

    return clean


def redact_block(block: Any) -> Any:
    """Return a copy of one block with grading internals removed.

    Non-dict blocks and blocks with no content pass through untouched: this
    runs on every message read, and a surprise in the data is not a reason to
    drop a learner's lesson.
    """
    if not isinstance(block, dict):
        return block

    content = block.get("content")
    if not isinstance(content, dict):
        return block

    clean_content = redact_content(content)
    if clean_content is content:
        return block

    return {**block, "content": clean_content}


def _has_option_secrets(content: Dict[str, Any]) -> bool:
    options = content.get("options")
    if not isinstance(options, list):
        return False
    return any(
        isinstance(option, dict) and any(f in option for f in REDACTED_OPTION_FIELDS)
        for option in options
    )


def redact_blocks(blocks: Optional[List[Any]]) -> Optional[List[Any]]:
    """Redact a whole message's blocks, preserving order and count."""
    if not blocks:
        return blocks
    return [redact_block(block) for block in blocks]
