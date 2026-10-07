"""Low-latency spoken delivery helpers for canonical Chat.

This module never decides *what* Lyo should say. The interaction contract,
teaching policy, memory and model stack already own that. It only turns model
text deltas into stable, speakable segments so clients can begin TTS before the
full response is complete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


_STRONG_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:[\"'”’)]*)\s+")
_SOFT_BOUNDARY_RE = re.compile(r"(?<=[,;:])\s+")
_ABBREVIATION_RE = re.compile(
    r"(?:\b(?:dr|mr|mrs|ms|prof|sr|jr|vs|etc)\.|\b(?:[a-z]\.){2,})$",
    re.IGNORECASE,
)


_SOURCE_CITATION_RE = re.compile(r"【[^】]+】")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_CODE_FENCE_RE = re.compile(r"\x60\x60\x60[\s\S]*?\x60\x60\x60")
_HEADING_RE = re.compile(r"(?m)^#{1,6}\s*")
_LIST_PREFIX_RE = re.compile(r"(?m)^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_EMPHASIS_RE = re.compile(r"[*_~]+")
_URL_RE = re.compile(r"https?://\S+")
_MATH_BLOCK_RE = re.compile(r"\$\$([\s\S]*?)\$\$")
_INLINE_MATH_RE = re.compile(r"(?<!\$)\$([^$\n]+)\$(?!\$)")
_TABLE_SEPARATOR_RE = re.compile(
    r"(?m)^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)


def prepare_spoken_text(raw: str) -> str:
    """Convert canonical Chat text into a speech-only rendering.

    This is deliberately presentation-only. The canonical text stays unchanged
    for persistence, rendering, citations, memory, and evaluation. Voice clients
    receive this field only to avoid reading markdown syntax, source markers,
    raw URLs, or table pipes aloud.
    """
    text = raw or ""
    text = _CODE_FENCE_RE.sub(" ", text)
    text = _MARKDOWN_IMAGE_RE.sub(" ", text)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _SOURCE_CITATION_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _HEADING_RE.sub("", text)
    text = re.sub(r"(?m)^\s*([A-Da-d])[.)]\s+", r"\1: ", text)
    text = _LIST_PREFIX_RE.sub("", text)
    text = re.sub(r"\x60([^\x60]+)\x60", r"\1", text)
    text = _EMPHASIS_RE.sub("", text)
    text = re.sub(
        r"\\frac\{([^{}]+)\}\{([^{}]+)\}",
        r"\1 over \2",
        text,
    )
    text = text.replace("\\(", "").replace("\\)", "")
    text = text.replace("\\[", "").replace("\\]", "")
    # Strip paired math delimiters but preserve semantic currency such as $2,100.
    text = _MATH_BLOCK_RE.sub(r"\1", text)
    text = _INLINE_MATH_RE.sub(r"\1", text)
    text = _TABLE_SEPARATOR_RE.sub(" ", text)
    text = re.sub(r"(?m)^\s*\|?(.*?)\|\s*$", lambda m: m.group(1).replace("|", ", "), text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@dataclass
class VoiceSegmenter:
    """Incrementally group token deltas into TTS-safe phrases.

    Strong sentence boundaries are preferred. For a long sentence, a comma or
    other clause boundary can be emitted to keep time-to-first-audio low. A
    hard length ceiling prevents an unusually punctuation-free answer from
    holding the floor indefinitely.
    """

    min_chars: int = 16
    soft_target_chars: int = 120
    hard_max_chars: int = 220
    _buffer: str = field(default="", init=False, repr=False)
    _inside_fenced_code: bool = field(default=False, init=False, repr=False)
    _fence_carry: str = field(default="", init=False, repr=False)

    def feed(self, delta: str) -> List[str]:
        if not delta:
            return []
        speakable = self._strip_fenced_code(delta, final=False)
        if speakable:
            self._buffer += speakable
        return self._drain(final=False)

    def flush(self) -> List[str]:
        trailing = self._strip_fenced_code("", final=True)
        if trailing:
            self._buffer += trailing
        return self._drain(final=True)

    def _strip_fenced_code(self, delta: str, *, final: bool) -> str:
        """Remove fenced-code content across arbitrary model-delta boundaries."""
        fence_token = chr(96) * 3
        data = self._fence_carry + (delta or "")
        self._fence_carry = ""
        output: List[str] = []
        cursor = 0

        while cursor < len(data):
            fence = data.find(fence_token, cursor)
            if fence < 0:
                remainder = data[cursor:]
                if not final:
                    keep = 0
                    for size in (2, 1):
                        if remainder.endswith(chr(96) * size):
                            keep = size
                            break
                    visible = remainder[:-keep] if keep else remainder
                    if not self._inside_fenced_code:
                        output.append(visible)
                    if keep:
                        self._fence_carry = remainder[-keep:]
                elif not self._inside_fenced_code:
                    output.append(remainder)
                break

            if not self._inside_fenced_code:
                output.append(data[cursor:fence])
            self._inside_fenced_code = not self._inside_fenced_code
            cursor = fence + len(fence_token)

        if final:
            if self._fence_carry and not self._inside_fenced_code:
                output.append(self._fence_carry)
            self._fence_carry = ""
            self._inside_fenced_code = False

        return "".join(output)

    def _drain(self, *, final: bool) -> List[str]:
        segments: List[str] = []

        while self._buffer:
            cut = self._strong_cut()
            if cut is None and len(self._buffer) >= self.soft_target_chars:
                cut = self._soft_cut()
            if cut is None and len(self._buffer) >= self.hard_max_chars:
                cut = self._hard_cut()
            if cut is None:
                break

            raw = self._buffer[:cut]
            self._buffer = self._buffer[cut:]
            spoken = raw.strip()
            if spoken:
                segments.append(spoken)

        if final:
            spoken = self._buffer.strip()
            self._buffer = ""
            if spoken:
                segments.append(spoken)

        return segments

    def _strong_cut(self) -> int | None:
        for match in _STRONG_BOUNDARY_RE.finditer(self._buffer):
            prefix = self._buffer[:match.start()].rstrip("\"'”’)")
            if prefix.endswith(".") and _ABBREVIATION_RE.search(prefix):
                continue
            if match.start() >= self.min_chars:
                return match.end()
        # A terminal period needs lookahead: the next provider delta may be
        # the rest of a decimal or abbreviation. Flush owns the final period.
        stripped = self._buffer.rstrip()
        if (
            len(stripped) >= self.min_chars
            and stripped[-1:] in {"!", "?"}
        ):
            return len(self._buffer)
        return None

    def _soft_cut(self) -> int | None:
        candidate = None
        for match in _SOFT_BOUNDARY_RE.finditer(self._buffer):
            if match.start() >= self.min_chars:
                candidate = match.end()
            if match.start() >= self.soft_target_chars:
                return match.end()
        return candidate

    def _hard_cut(self) -> int:
        window = self._buffer[: self.hard_max_chars]
        whitespace = max(window.rfind(" "), window.rfind("\n"), window.rfind("\t"))
        if whitespace >= self.min_chars:
            return whitespace + 1
        return self.hard_max_chars
