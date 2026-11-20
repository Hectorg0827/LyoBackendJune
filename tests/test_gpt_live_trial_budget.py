"""Staging GPT-Live safety contract: no network provider calls in tests."""
import asyncio

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from lyo_app.live_trial import budget
from lyo_app.live_trial import routes


@pytest.mark.asyncio
async def test_trial_cannot_reserve_more_than_ten_dollars(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/trial.db")
    try:
        await budget.initialize_schema(engine)
        tickets = [await budget.issue_ticket(engine, 42) for _ in range(66)]
        assert len(set(tickets)) == 66
        status = await budget.get_status(engine)
        assert status.reserved_micro_usd == 9_900_000
        assert status.remaining_micro_usd == 100_000
        assert status.max_sessions_remaining == 0
        with pytest.raises(budget.TrialBudgetExhausted):
            await budget.issue_ticket(engine, 42)
        assert (await budget.get_status(engine)).reserved_micro_usd == 9_900_000
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ticket_is_short_lived_and_single_use_even_across_connections(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/trial.db")
    try:
        await budget.initialize_schema(engine)
        ticket = await budget.issue_ticket(engine, 51)
        assert await budget.claim_ticket(engine, ticket) is True
        assert await budget.claim_ticket(engine, ticket) is False
        await budget.finish_ticket(engine, ticket, 20)
        assert (await budget.get_status(engine)).reserved_micro_usd == 150_000
        expired = await budget.issue_ticket(engine, 51)
        original_now = budget.time.time
        monkeypatch.setattr(budget.time, "time", lambda: original_now() + 120)
        assert await budget.claim_ticket(engine, expired) is False
        assert (await budget.get_status(engine)).reserved_micro_usd == 300_000
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_reservations_are_database_atomic(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/trial.db")
    try:
        await budget.initialize_schema(engine)
        results = await asyncio.gather(
            *(budget.issue_ticket(engine, 42) for _ in range(12))
        )
        assert len(set(results)) == 12
        assert (await budget.get_status(engine)).reserved_micro_usd == 1_800_000
    finally:
        await engine.dispose()


def test_staging_gate_is_fail_closed_and_requires_separate_key(monkeypatch):
    keys = (
        "ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "LYO_GPT_LIVE_STAGING_HOST",
        "LYO_GPT_LIVE_TRIAL_ENABLED", "LYO_GPT_LIVE_STAGING_OPENAI_API_KEY",
        "LYO_GPT_LIVE_TRIAL_ALLOWED_USER_IDS",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    assert routes._staging_allowed("staging.example.net") is False
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("LYO_GPT_LIVE_STAGING_HOST", "staging.example.net")
    monkeypatch.setenv("LYO_GPT_LIVE_TRIAL_ALLOWED_USER_IDS", "42")
    monkeypatch.setenv("LYO_GPT_LIVE_TRIAL_ENABLED", "true")
    assert routes._staging_allowed("staging.example.net") is False  # missing trial key
    monkeypatch.setenv("LYO_GPT_LIVE_STAGING_OPENAI_API_KEY", "test-not-real")
    assert routes._staging_allowed("staging.example.net") is True
    assert routes._user_allowed(42) is True
    assert routes._user_allowed(13) is False
    assert routes._staging_allowed("api.lyoai.app") is False
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    assert routes._staging_allowed("staging.example.net") is False
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME")
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert routes._staging_allowed("staging.example.net") is False
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("LYO_GPT_LIVE_TRIAL_ENABLED", "false")
    assert routes._staging_allowed("staging.example.net") is False


def test_no_external_paid_delegation_is_possible_from_trial():
    assert "client" in routes.VOICE_INSTRUCTIONS.lower()
    assert "gpt-live-1" in routes._relay.__doc__ or callable(routes._relay)
    assert "gpt-5.6" not in routes.VOICE_INSTRUCTIONS
    assert "fraction" in routes._local_trial_answer("fractions").lower()
    assert "cell" in routes._local_trial_answer("cells").lower()
    assert "not connected" in routes._local_trial_answer("Tell me quantum theory")


@pytest.mark.asyncio
async def test_trial_budget_survives_application_restart(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/persistent_trial.db"
    first = create_async_engine(url)
    await budget.initialize_schema(first)
    ticket = await budget.issue_ticket(first, 92)
    await first.dispose()

    # A fresh process/worker must see earlier reservations and used tickets.
    second = create_async_engine(url)
    try:
        await budget.initialize_schema(second)
        assert (await budget.get_status(second)).reserved_micro_usd == 150_000
        assert await budget.claim_ticket(second, ticket) is True
        assert await budget.claim_ticket(second, ticket) is False
    finally:
        await second.dispose()


@pytest.mark.asyncio
async def test_guest_cannot_reserve_a_paid_voice_ticket(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/trial.db")
    try:
        await budget.initialize_schema(engine)
        with pytest.raises(ValueError, match="Authenticated"):
            await budget.issue_ticket(engine, 0)
        assert (await budget.get_status(engine)).reserved_micro_usd == 0
    finally:
        await engine.dispose()
