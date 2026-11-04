"""Exact, narrow grading for unambiguous classroom fraction checkpoints.

The model remains responsible for explanations, multi-part rubrics and ambiguous
questions. This module only intervenes when a single numerical fraction is
explicitly requested and the authored reference has one mathematical value.
"""

from dataclasses import dataclass
from fractions import Fraction
import re
from typing import Any


@dataclass(frozen=True)
class FractionAssessment:
    correct: bool


_TOKEN = re.compile(r"(?<![\w/])(-?\d{1,7})\s*/\s*(-?\d{1,7})(?![\w/])")
_FULL = re.compile(r"\s*(-?\d{1,7})\s*/\s*(-?\d{1,7})\s*\.?\s*")
_ASKS_FOR_FRACTION = re.compile(
    r"(?:what|which|write|state|identify|find|express|qué|cuál|escribe|"
    r"indica|identifica|encuentra)[^.!?]{0,180}\b(?:fraction|fracción)\b",
    re.IGNORECASE,
)
_REQUIRES_REASONING = re.compile(
    r"\b(?:why|explain|justify|reason|reasoning|show your work|"
    r"demonstrate|because|compare|por qué|explica|justifica|razona|"
    r"demuestra|compara)\b",
    re.IGNORECASE,
)


def assess_objective_fraction(task: Any, answer: str) -> FractionAssessment | None:
    """Grade only a pure fraction answer to a single-criterion fraction task.

    Return None for anything ambiguous so the existing semantic teacher can
    consider context and equivalent explanations. A zero denominator is an
    invalid learner answer, never an exception or a model-correct answer.
    """
    if task.response_format != "short_answer" or task.kind not in {"predict", "apply"}:
        return None
    if len(task.criteria) != 1 or not _ASKS_FOR_FRACTION.search(task.question):
        return None
    if _REQUIRES_REASONING.search(task.question + " " + task.criteria[0]):
        return None

    reference_matches = _TOKEN.findall(task.example_answer)
    if not reference_matches:
        return None

    references: set[Fraction] = set()
    for numerator, denominator in reference_matches:
        if int(denominator) == 0:
            return None  # Invalid reference; do not trust it to grade.
        references.add(Fraction(int(numerator), int(denominator)))
    if len(references) != 1:
        return None  # The reference contains multiple distinct mathematical values.

    match = _FULL.fullmatch(answer)
    if match is None:
        return None  # Explanations, decimals, units and follow-ups need semantic grading.

    numerator, denominator = (int(part) for part in match.groups())
    if denominator == 0:
        return FractionAssessment(correct=False)
    return FractionAssessment(
        correct=Fraction(numerator, denominator) == next(iter(references))
    )
