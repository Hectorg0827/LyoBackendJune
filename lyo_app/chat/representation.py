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
_TIMELINE_RE = re.compile(
    r"(?m)^\s*[-*]?\s*(?P<label>(?:\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?))\s*[-:–—]\s*(?P<detail>.+)$",
    re.IGNORECASE,
)
_DISPLAY_MATH_RE = re.compile(
    r"(?P<full>"
    r"\$\$(?P<dollar>.+?)\$\$"
    r"|\\\[(?P<bracket>.+?)\\\]"
    r"|(?m:^\s*\$(?!\$)(?P<single>[^$\n]+)\$\s*$)"
    r")",
    re.DOTALL,
)


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

    # Reuse the Classroom manipulative for a fraction the answer already
    # explains. No second generation call and no quiz added to an explanation.
    if interaction_mode in {"", "answer", "explain", "teach", "continue", "test_prep"}:
        from lyo_app.ai_classroom.teaching_visuals import fraction_pie_from_text
        visual = fraction_pie_from_text("", text, "es" if re.search(r"\b(?:fracci[oó]n|fracciones)\b", text, re.I) else "en")
        if visual is not None:
            blocks.append(SmartBlock.teaching_visual(visual).model_dump())

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

    # A dated sequence is a timeline, not merely another prose list.
    timeline_matches = list(_TIMELINE_RE.finditer(text))
    if len(timeline_matches) >= 2:
        blocks.append(
            SmartBlock(
                type="interactive",
                subtype="timeline",
                content={
                    "title": "Timeline",
                    "items": [
                        {
                            "label": match.group("label").strip(),
                            "detail": match.group("detail").strip(),
                        }
                        for match in timeline_matches
                    ],
                },
            ).model_dump()
        )
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not _TIMELINE_RE.match(line))

    # Promote the first display equation into a native math block. Worked
    # examples keep their surrounding explanation/steps in prose/step blocks.
    math_match = _DISPLAY_MATH_RE.search(text)
    if math_match:
        source = (
            math_match.group("dollar")
            or math_match.group("bracket")
            or math_match.group("single")
            or ""
        ).strip()
        if source:
            blocks.append(
                SmartBlock.data_viz(source=source, fmt="math", title="Worked math").model_dump()
            )
            text = text[: math_match.start()] + "\n" + text[math_match.end() :]

    # Comparisons are always represented structurally. A markdown table is the
    # preferred form above; this deterministic fallback prevents a model that
    # chose prose from collapsing the workspace back into an ordinary bubble.
    if interaction_mode == "compare" and not any(
        block.get("subtype") in {"table", "comparison"}
        or (
            block.get("type") == "dataViz"
            and (block.get("content") or {}).get("format") == "table"
        )
        for block in blocks
    ):
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
            if sentence.strip()
        ]
        if sentences:
            blocks.append(
                SmartBlock(
                    type="interactive",
                    subtype="comparison",
                    content={
                        "title": "Comparison",
                        "items": [
                            {"label": f"Difference {index + 1}", "detail": sentence}
                            for index, sentence in enumerate(sentences[:6])
                        ],
                    },
                ).model_dump()
            )
            text = ""

    return text.strip(), blocks
