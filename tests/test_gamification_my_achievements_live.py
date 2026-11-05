"""Executable regression checks for the live learner achievements endpoint.

These test the production route function, not a copied implementation.
The existing legacy gamification route module is skipped wholesale.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from lyo_app.gamification.routes import get_my_achievements


@pytest.mark.asyncio
async def test_my_achievements_reads_persisted_rows_for_current_user():
    own_row = SimpleNamespace(id=8, user_id=41, achievement_id=11, is_completed=True)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [own_row]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    rows = await get_my_achievements(
        skip=0,
        limit=50,
        completed_only=False,
        current_user=SimpleNamespace(id=41),
        db=db,
    )

    assert rows == [own_row]  # The old stub always returned [].
    stmt = db.execute.await_args.args[0]
    assert "user_achievements.user_id" in str(stmt)
    assert stmt._limit_clause.value == 50
    assert stmt._offset_clause.value == 0


@pytest.mark.asyncio
async def test_my_achievements_completed_only_filters_and_paginates():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    await get_my_achievements(
        skip=10,
        limit=20,
        completed_only=True,
        current_user=SimpleNamespace(id=72),
        db=db,
    )

    stmt = db.execute.await_args.args[0]
    rendered = str(stmt)
    assert "user_achievements.user_id" in rendered
    assert "user_achievements.is_completed IS true" in rendered
    assert stmt._limit_clause.value == 20
    assert stmt._offset_clause.value == 10
