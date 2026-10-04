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


@dataclass
class VoiceSegmenter:
    """Incrementally group token deltas into TTS-safe phrases.

    Strong sentence boundaries are preferred. For a long sentence, a comma or
    other clause boundary can be emitted to keep time-to-first-audio low. A
    hard length ceiling prevents an unusually punctuation-free answer from
    holding the floor indefinitely.
    """

    min_chars: int = 28
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
            if match.start() >= self.min_chars:
                return match.end()
        # A provider delta can end exactly on punctuation with no trailing
        # whitespace yet. Emit it once it is substantial enough.
        stripped = self._buffer.rstrip()
        if (
            len(stripped) >= self.min_chars
            and stripped[-1:] in {".", "!", "?"}
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
