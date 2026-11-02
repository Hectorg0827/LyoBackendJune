"""Staging-only, durable prepaid budget for GPT-Live.

Reservations are deliberately NOT refunded, including failed/abandoned starts.
A session is limited to 60 wall-clock seconds, and reserves $0.15 (three
minutes at the verified $0.05/min price). That conservative buffer covers
startup/close uncertainty. Backend delegation never calls a paid model.
The single SQL UPDATE is atomic across workers and app restarts.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

from sqlalchemy import (
    BigInteger, Column, MetaData, String, Table, insert, select, text, update
)
from sqlalchemy.ext.asyncio import AsyncEngine

TRIAL_CAP_MICRO_USD = 10_000_000  # Exactly $10.00; intentionally not configurable.
SESSION_RESERVATION_MICRO_USD = 150_000  # $0.15, conservatively above max voice cost.
SESSION_MAX_WALL_SECONDS = 60
TICKET_TTL_SECONDS = 45

metadata = MetaData()
budget_table = Table(
    "lyo_gpt_live_trial_budget", metadata,
    Column("budget_key", String(32), primary_key=True),
    Column("reserved_micro_usd", BigInteger, nullable=False),
)
ticket_table = Table(
    "lyo_gpt_live_trial_tickets", metadata,
    Column("ticket_hash", String(64), primary_key=True),
    Column("user_id", BigInteger, nullable=False),
    Column("expires_at_epoch", BigInteger, nullable=False),
    Column("claimed_at_epoch", BigInteger, nullable=True),
    Column("finished_at_epoch", BigInteger, nullable=True),
    Column("reported_seconds", BigInteger, nullable=True),
)


class TrialBudgetExhausted(Exception):
    """No new paid provider session is permitted."""


@dataclass(frozen=True)
class TrialStatus:
    reserved_micro_usd: int
    remaining_micro_usd: int
    max_sessions_remaining: int


def _digest(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


async def initialize_schema(engine: AsyncEngine) -> None:
    """Creates only the isolated staging trial tables; fails closed on DB errors."""
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def get_status(engine: AsyncEngine) -> TrialStatus:
    async with engine.connect() as conn:
        used = (await conn.execute(
            select(budget_table.c.reserved_micro_usd).where(
                budget_table.c.budget_key == "global"
            )
        )).scalar_one_or_none() or 0
    remaining = max(0, TRIAL_CAP_MICRO_USD - used)
    return TrialStatus(used, remaining, remaining // SESSION_RESERVATION_MICRO_USD)


async def issue_ticket(engine: AsyncEngine, user_id: int) -> str:
    """Reserve capacity BEFORE creating a single-use ticket, atomically.

    A provider session cannot be opened without first consuming a ticket.
    Debits are irreversible on purpose: errors or missing final usage never
    return authorization for potentially billable provider work.
    """
    if user_id <= 0:
        raise ValueError("Authenticated user required")
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO lyo_gpt_live_trial_budget "
            "(budget_key, reserved_micro_usd) VALUES ('global', 0) "
            "ON CONFLICT(budget_key) DO NOTHING"
        ))
        result = await conn.execute(
            update(budget_table)
            .where(budget_table.c.budget_key == "global")
            .where(
                budget_table.c.reserved_micro_usd + SESSION_RESERVATION_MICRO_USD
                <= TRIAL_CAP_MICRO_USD
            )
            .values(
                reserved_micro_usd=(
                    budget_table.c.reserved_micro_usd + SESSION_RESERVATION_MICRO_USD
                )
            )
        )
        if result.rowcount != 1:
            raise TrialBudgetExhausted("Trial budget reached; no new voice sessions")
        await conn.execute(insert(ticket_table).values(
            ticket_hash=_digest(token),
            user_id=user_id,
            expires_at_epoch=now + TICKET_TTL_SECONDS,
        ))
    return token


async def claim_ticket(engine: AsyncEngine, token: str) -> bool:
    """Only one websocket, on any worker, can claim a ticket."""
    if len(token) < 30 or len(token) > 256:
        return False
    now = int(time.time())
    async with engine.begin() as conn:
        result = await conn.execute(
            update(ticket_table)
            .where(ticket_table.c.ticket_hash == _digest(token))
            .where(ticket_table.c.claimed_at_epoch.is_(None))
            .where(ticket_table.c.expires_at_epoch >= now)
            .values(claimed_at_epoch=now)
        )
    return result.rowcount == 1


async def finish_ticket(engine: AsyncEngine, token: str, seconds: int | None) -> None:
    """Record provider usage for audit only; never replenish the reservation."""
    async with engine.begin() as conn:
        await conn.execute(
            update(ticket_table)
            .where(ticket_table.c.ticket_hash == _digest(token))
            .where(ticket_table.c.claimed_at_epoch.is_not(None))
            .values(
                finished_at_epoch=int(time.time()),
                reported_seconds=seconds,
            )
        )
