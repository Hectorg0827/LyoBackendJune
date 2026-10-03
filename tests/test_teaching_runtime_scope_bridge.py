from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.teaching_runtime.service import (
    load_learner_snapshot,
    teaching_topic_from_text,
)


class _Scalars:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)


class _Result:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return _Scalars(self._values)


def _record_item(
    concept_id,
    *,
    state="APPLIED",
    best_rung="application",
    next_rung="transfer",
    misconception=None,
    last_seen="2026-10-02T12:00:00",
):
    return SimpleNamespace(
        concept_id=concept_id,
        state=state,
        best_rung=best_rung,
        next_rung=next_rung,
        misconception=misconception,
        last_seen=last_seen,
    )


def test_teaching_topic_strips_instruction_wrapper_without_guessing_aliases():
    assert teaching_topic_from_text("Teach me about fractions") == "fractions"
    assert teaching_topic_from_text("Explain price elasticity") == "price elasticity"
    assert teaching_topic_from_text("fractions") == "fractions"


@pytest.mark.asyncio
async def test_chat_reuses_exact_scoped_classroom_evidence(monkeypatch):
    classroom_concept_id = "9dc41d89-76d9-46f7-8ee4-8dc7e41004c8"
    record = SimpleNamespace(
        unavailable=False,
        concepts=[
            _record_item(
                classroom_concept_id,
                misconception="compares denominators without a common whole",
            )
        ],
    )

    async def _learner_record(_db, _user_id, limit=100):
        assert limit == 100
        return record

    monkeypatch.setattr(
        "lyo_app.events.concept_record.learner_record",
        _learner_record,
    )

    db = AsyncMock()
    # First query resolves all Concepts inside topic_scope("fractions").
    # Second query asks for numeric LearnerMastery rows across those exact IDs.
    db.execute.side_effect = [
        _Result([classroom_concept_id]),
        _Result([]),
    ]

    snapshot = await load_learner_snapshot(
        db,
        "42",
        "fractions",  # legacy Chat slug has no exact event
        topic="fractions",
    )

    assert snapshot.evidence_state == "APPLIED"
    assert snapshot.strongest_rung == "application"
    assert snapshot.next_rung == "transfer"
    assert snapshot.attempts == 1
    assert snapshot.misconception == "compares denominators without a common whole"
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_exact_legacy_chat_evidence_wins_without_scope_guess(monkeypatch):
    record = SimpleNamespace(
        unavailable=False,
        concepts=[
            _record_item(
                "fractions",
                state="TRANSFERRED",
                best_rung="transfer",
                next_rung="retention",
            )
        ],
    )

    async def _learner_record(_db, _user_id, limit=100):
        return record

    monkeypatch.setattr(
        "lyo_app.events.concept_record.learner_record",
        _learner_record,
    )

    db = AsyncMock()
    # Only the numeric exact-skill query should execute; there is no Concept
    # scope lookup when a verified legacy record already exists.
    db.execute.return_value = _Result([])

    snapshot = await load_learner_snapshot(
        db,
        "42",
        "fractions",
        topic="fractions",
    )

    assert snapshot.evidence_state == "TRANSFERRED"
    assert snapshot.strongest_rung == "transfer"
    assert snapshot.next_rung == "retention"
    assert db.execute.await_count == 1
