"""Subject-independent board documents derived from validated teaching content.

The parser preserves authored content; it never invents a diagram, executes code,
adds a model call, grades exploration or advances the classroom. Older clients
retain ExampleBlock.content as the complete fallback.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BoardBlock(BaseModel):
    # Code indentation is authored content, including the first line.
    model_config = ConfigDict(extra="forbid")
    kind: Literal["text", "bullets", "steps", "code", "table"]
    text: str = Field(default="", max_length=1500)
    language: str = Field(default="", max_length=40)
    items: list[str] = Field(default_factory=list, max_length=20)
    headers: list[str] = Field(default_factory=list, max_length=8)
    rows: list[list[str]] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def coherent(self):
        strings = self.items + self.headers + [cell for row in self.rows for cell in row]
        if any(not value.strip() or len(value) > 1500 for value in strings):
            raise ValueError("Board cells and items need bounded, nonempty text")
        if self.kind in {"text", "code"} and not self.text.strip():
            raise ValueError("Text and code blocks need their authored content")
        if self.kind in {"steps", "bullets"} and not self.items:
            raise ValueError("Lists need authored items")
        if self.kind == "table" and (not self.headers or not self.rows
                                     or any(len(row) != len(self.headers) for row in self.rows)):
            raise ValueError("A table needs rectangular rows and column labels")
        return self


class BoardDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    blocks: list[BoardBlock] = Field(min_length=1, max_length=20)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def board_document(content: str) -> BoardDocument | None:
    """Recognise explicit markdown structure, with lossless readable fallback.

    Malformed/unbounded tables remain text. Only complete fenced code is code.
    Any subject can supply prose, a list, worked steps, a table or fenced code;
    quantitative/image/process representations keep the existing TeachingVisual.
    """
    if not content or len(content) > 1500:
        return None
    lines = content.splitlines()
    blocks: list[BoardBlock] = []
    pending: list[str] = []

    def flush():
        if pending:
            text = "\n".join(pending).strip()
            if text:
                blocks.append(BoardBlock(kind="text", text=text))
            pending.clear()

    i = 0
    fence = chr(96) * 3
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith(fence):
            end = next((n for n in range(i + 1, len(lines)) if lines[n].strip() == fence), None)
            if end is not None and "\n".join(lines[i + 1:end]).strip():
                flush()
                blocks.append(BoardBlock(kind="code", text="\n".join(lines[i + 1:end]),
                                         language=stripped[3:].strip()[:40]))
                i = end + 1
                continue
            # An unmatched fence is literal text, including its delimiters.
            pending.extend(lines[i:])
            break
        if i + 1 < len(lines) and "|" in stripped:
            headers = _cells(line)
            separator = _cells(lines[i + 1])
            if len(separator) == len(headers) and all(re.fullmatch(r":?-{3,}:?", c) for c in separator):
                end = i + 2
                while end < len(lines) and "|" in lines[end] and lines[end].strip():
                    end += 1
                rows = [_cells(row) for row in lines[i + 2:end]]
                if (1 <= len(headers) <= 8 and 1 <= len(rows) <= 20
                        and all(headers) and all(len(row) == len(headers) and all(row) for row in rows)):
                    flush()
                    blocks.append(BoardBlock(kind="table", headers=headers, rows=rows))
                    i = end
                    continue
        numbered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        bullet = re.match(r"^\s*[-*•]\s+(.+)$", line)
        if numbered or bullet:
            kind = "steps" if numbered else "bullets"
            pattern = r"^\s*\d+[.)]\s+(.+)$" if numbered else r"^\s*[-*•]\s+(.+)$"
            items = []
            numbers = []
            end = i
            while end < len(lines) and len(items) < 20:
                match = re.match(pattern, lines[end])
                if not match:
                    break
                items.append(match.group(1))
                if numbered:
                    numbers.append(int(re.match(r"^\s*(\d+)", lines[end]).group(1)))
                end += 1
            flush()
            # Renumbering a continuation or a skipped authored step would
            # change its meaning. Preserve such lists literally instead.
            if numbered and numbers != list(range(1, len(items) + 1)):
                blocks.append(BoardBlock(kind="text", text="\n".join(lines[i:end])))
            else:
                blocks.append(BoardBlock(kind=kind, items=items))
            i = end
            continue
        pending.append(line)
        i += 1
    flush()
    # Preserve the full source if unusually fragmented content exceeds the
    # render contract; never drop later steps to fit a client cap.
    if len(blocks) > 20:
        blocks = [BoardBlock(kind="text", text=content)]
    return BoardDocument(blocks=blocks) if blocks else None
