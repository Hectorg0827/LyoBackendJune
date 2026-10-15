"""P0 learner ledger: XP comes from server-graded events, never client claims."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from lyo_app.events.models import EventType
from lyo_app.events.processor import _award_verified_learning_xp


def event(**kwargs):
    fields = dict(
        id=23, user_id=7,
        event_type=EventType.CLASSROOM_DEMONSTRATION,
        source_surface="classroom", measurable_outcome=1.0,
        evidence_confidence=0.8,
    )
    fields.update(kwargs)
    return SimpleNamespace(**fields)


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [
    {"measurable_outcome": None, "evidence_confidence": None},
    {"measurable_outcome": 0.0},
    {"evidence_confidence": 0},
    {"source_surface": "untrusted_client"},
    {"event_type": EventType.AI_SESSION},
    {"id": None},
])
async def test_unverified_or_ungraded_event_cannot_mint_xp(fields):
    db = MagicMock()
    db.execute = AsyncMock()
    assert await _award_verified_learning_xp(db, event(**fields)) is False
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_graded_checkpoint_awards_once(monkeypatch):
    award = AsyncMock()
    import lyo_app.gamification.service as service
    monkeypatch.setattr(service.GamificationService, "award_xp", award)

    row_lock = MagicMock()
    existing_record = MagicMock()
    existing_record.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[row_lock, existing_record])
    assert await _award_verified_learning_xp(db, event()) is True
    award.assert_awaited_once()
    kwargs = award.await_args.kwargs
    assert kwargs["user_id"] == 7
    assert kwargs["context_type"] == "learning_event"
    assert kwargs["context_id"] == 23


@pytest.mark.asyncio
async def test_retry_cannot_double_award(monkeypatch):
    award = AsyncMock()
    import lyo_app.gamification.service as service
    monkeypatch.setattr(service.GamificationService, "award_xp", award)

    row_lock = MagicMock()
    existing_record = MagicMock()
    existing_record.scalar_one_or_none.return_value = 501
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[row_lock, existing_record])
    assert await _award_verified_learning_xp(db, event()) is False
    award.assert_not_awaited()
