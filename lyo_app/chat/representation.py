"""Deterministic promotion of model prose into SmartBlock representations."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from lyo_app.ai.schemas.smart_block import SmartBlock

_MERMAID_RE = re.compile(r"```mermaid\s*\n(?P<body>.*?)\n```", re.IGNORECASE | re.DOTALL)
_TABLE_RE = re.compile(
    r"(?P<table>(?:^|\n)\|[^\n]+\|\n\|\s*:?-{3,}[^\n]*\|(?:\n\|[^\n]+\|)+)",
    re.MULTILINE,
)
_NUMBERED_RE = re.compile(r"(?m)^\s*(?P<n>\d+)[.)]\s+(?P<text>.+)$")


def promote_answer_representations(
    answer_text: str,
    *,
    interaction_mode: str = "",
) -> Tuple[str, List[Dict[str, Any]]]:
    """Return prose with large structured payloads removed plus renderable blocks.

    This is deliberately deterministic: the model chooses the content, while
    the server chooses whether a declared table/diagram/sequence becomes a
    workspace object instead of remaining raw implementation text.
    """
    text = answer_text or ""
    blocks: List[Dict[str, Any]] = []

    def mermaid_replace(match: re.Match[str]) -> str:
        source = match.group("body").strip()
        if source:
            blocks.append(
                SmartBlock.data_viz(source=source, fmt="mermaid", title="Visual").model_dump()
            )
        return "\n"

    text = _MERMAID_RE.sub(mermaid_replace, text)

    # Comparison/data tables are promoted into the native table renderer.
    table_match = _TABLE_RE.search(text)
    if table_match:
        table = table_match.group("table").strip()
        if table.count("\n") >= 2:
            blocks.append(
                SmartBlock.table(
                    markdown=table,
                    title="Comparison" if interaction_mode == "compare" else None,
                ).model_dump()
            )
            text = text[: table_match.start()] + "\n" + text[table_match.end() :]

    # A real procedure with at least three numbered steps becomes an
    # interactive step-by-step block. Keep short two-item lists as prose.
    numbered = list(_NUMBERED_RE.finditer(text))
    if len(numbered) >= 3 and interaction_mode in {"explain", "analyze", "continue", "answer"}:
        items = [
            {"label": f"Step {index + 1}", "detail": match.group("text").strip()}
            for index, match in enumerate(numbered)
        ]
        blocks.append(
            SmartBlock(
                type="interactive",
                subtype="stepByStep",
                content={"title": "Steps", "items": items},
            ).model_dump()
        )
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines if not _NUMBERED_RE.match(line)
        )

    return text.strip(), blocks
