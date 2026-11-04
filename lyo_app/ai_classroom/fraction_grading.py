"""Exact, narrow grading for unambiguous classroom fraction checkpoints.

The model remains responsible for explanations, multi-part rubrics and ambiguous
questions. A numeric answer is graded here only when the teacher's reference
matches independently checkable counts stated in the actual task.
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

_PARTS = r"(?:parts|pieces|slices|sections|segments|blocks|cells)"
_TOTAL = re.compile(rf"\b(\d{{1,7}})\s+equal\s+{_PARTS}\b", re.IGNORECASE)
_SELECTED = (
    re.compile(
        rf"\b(\d{{1,7}})\s+(?:of\s+(?:those|these|the)\s+{_PARTS}\s+)?"
        r"(?:are|were|is)\s+(?:shaded|colou?red|filled|selected|planted)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(\d{{1,7}})\s+(?:shaded|colou?red|filled|selected|planted)\s+{_PARTS}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:shades?|colou?rs?|fills?|selects?|plants?)\s+(\d{1,7})\b",
        re.IGNORECASE,
    ),
)


def _simple_fraction_task(task: Any) -> bool:
    return (
        task.response_format == "short_answer"
        and task.kind in {"predict", "apply"}
        and len(task.criteria) == 1
        and _ASKS_FOR_FRACTION.search(task.question) is not None
        and _REQUIRES_REASONING.search(task.question + " " + task.criteria[0]) is None
    )


def _reference_value(task: Any) -> Fraction | None:
    values: set[Fraction] = set()
    for numerator, denominator in _TOKEN.findall(task.example_answer):
        if int(denominator) == 0:
            return None
        values.add(Fraction(int(numerator), int(denominator)))
    return next(iter(values)) if len(values) == 1 else None


def _stated_counts(task: Any) -> Fraction | None:
    """Read only explicit selected/total shape counts; never guess from a diagram."""
    words = task.scenario + " " + task.question
    totals = {int(m.group(1)) for m in _TOTAL.finditer(words)}
    selected = {
        int(m.group(1))
        for pattern in _SELECTED
        for m in pattern.finditer(words)
    }
    if len(totals) != 1 or len(selected) != 1:
        return None
    total = next(iter(totals))
    shaded = next(iter(selected))
    if total == 0 or shaded > total:
        return None
    return Fraction(shaded, total)


def fraction_reference_consistent(task: Any) -> bool:
    """Reject checkable wrong model answer keys before asking the student."""
    if not _simple_fraction_task(task):
        return True
    expected = _reference_value(task)
    stated = _stated_counts(task)
    return expected is None or stated is None or expected == stated


def assess_objective_fraction(task: Any, answer: str) -> FractionAssessment | None:
    """Grade a pure fraction only when the question's independent counts agree.

    Return None whenever the question, its reference or the student's response
    is ambiguous. The semantic grader remains the safe fallback.
    """
    if not _simple_fraction_task(task):
        return None
    expected = _reference_value(task)
    stated = _stated_counts(task)
    if expected is None or stated is None or expected != stated:
        return None

    match = _FULL.fullmatch(answer)
    if match is None:
        return None

    numerator, denominator = (int(part) for part in match.groups())
    if denominator == 0:
        return FractionAssessment(correct=False)
    return FractionAssessment(
        correct=Fraction(numerator, denominator) == stated
    )
