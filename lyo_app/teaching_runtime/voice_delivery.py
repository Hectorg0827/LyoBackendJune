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
    text = _LIST_PREFIX_RE.sub("", text)
    text = re.sub(r"\x60([^\x60]+)\x60", r"\1", text)
    text = _EMPHASIS_RE.sub("", text)
    text = text.replace("\\(", "").replace("\\)", "")
    text = text.replace("\\[", "").replace("\\]", "")
    text = text.replace("$", "")
    text = re.sub(r"(?m)^\s*\|?(.*?)\|\s*$", lambda m: m.group(1).replace("|", ", "), text)
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

    def feed(self, delta: str) -> List[str]:
        if not delta:
            return []
        self._buffer += delta
        return self._drain(final=False)

    def flush(self) -> List[str]:
        return self._drain(final=True)

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
