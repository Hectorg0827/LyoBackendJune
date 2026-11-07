"""Fail-closed spending guard for a one-off Google Chirp staging pilot.

The user approved a $25 total experiment.  This separate TTS allowance is
hard-limited to $15 to leave room for the preceding infrastructure experiment.
Reservations happen *before* each uncached call and are not refunded on errors:
a timed-out or failed provider call may still be billed.  This ledger must
remain durable in Redis (no TTL/eviction) across workers and deployments.
Each reservation must be acknowledged by the local append-only file before a
paid request is allowed; RDB snapshots alone are not sufficient.

Reservations bound API speech-character charges, not the Google Cloud invoice,
taxes, currency conversion, or unrelated project usage. A billing-side budget
and a TTS-only credential with quota limits are additionally required.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

MAX_TRIAL_USD = Decimal("15.00")
LEDGER_KEY = "lyo:tts:chirp:trial:20261107:reserved_microusd"

# The published Chirp 3 HD speech rate is $30 per million characters.
# Reserve $40 per million UTF-8 *bytes* as a deliberately higher allowance.
# 1 USD = 1,000,000 microUSD, so each byte reserves 40 microUSD.
RESERVE_MICRO_USD_PER_UTF8_BYTE = 40

# A disk failure or non-AOF Redis configuration must block a paid request.
AOF_WAIT_TIMEOUT_MS = 5_000

_RESERVE_LUA = """
local existing = tonumber(redis.call('GET', KEYS[1]) or '0')
local cost = tonumber(ARGV[1])
local ceiling = tonumber(ARGV[2])
if not existing or existing < 0 or not cost or cost <= 0 or not ceiling or ceiling <= 0 then
    return -2
end
if existing + cost > ceiling then
    return -1
end
return redis.call('INCRBY', KEYS[1], cost)
"""


class TTSTrialBudgetExceeded(RuntimeError):
    """A paid voice request cannot safely proceed under the pilot allowance."""


def _trial_limit_micro_usd() -> int:
    if os.getenv("ENVIRONMENT", "").strip().lower() not in {"stage", "staging"}:
        raise TTSTrialBudgetExceeded("Paid Chirp pilot may run in staging only")
    if os.getenv("TTS_CHIRP_TRIAL_ENABLED", "").strip().lower() != "true":
        raise TTSTrialBudgetExceeded("Paid Chirp pilot is not enabled")
    try:
        amount = Decimal(os.getenv("TTS_CHIRP_TRIAL_LIMIT_USD", ""))
        if not amount.is_finite() or not 0 < amount <= MAX_TRIAL_USD:
            raise ValueError("Invalid TTS pilot budget")
        micro = amount * 1_000_000
        if micro != micro.to_integral_exact():
            raise ValueError("Sub-microUSD precision")
        return int(micro)
    except (InvalidOperation, ValueError) as exc:
        raise TTSTrialBudgetExceeded("TTS pilot limit must be at most $15") from exc


async def reserve_chirp_attempt(text: str) -> int:
    """Atomically reserve an upper estimate before *every* paid request."""
    ceiling = _trial_limit_micro_usd()
    charge = len(text.encode("utf-8")) * RESERVE_MICRO_USD_PER_UTF8_BYTE
    if not charge or charge > ceiling:
        raise TTSTrialBudgetExceeded("TTS pilot request exceeds the allowance")

    from lyo_app.core.redis_client import redis_client

    client = redis_client.client
    if client is None:
        raise TTSTrialBudgetExceeded("TTS pilot Redis ledger unavailable")
    try:
        # WAITAOF acknowledges writes from *this same connection*. A normal
        # client.eval() followed by client.execute_command() may use different
        # pooled connections. A non-transactional pipeline pins both commands
        # to one connection and permits WAITAOF to block until local fsync.
        async with client.pipeline(transaction=False) as pipe:
            pipe.eval(_RESERVE_LUA, 1, LEDGER_KEY, charge, ceiling)
            pipe.execute_command("WAITAOF", 1, 0, AOF_WAIT_TIMEOUT_MS)
            result = await pipe.execute()
        if not isinstance(result, (tuple, list)) or len(result) != 2:
            raise ValueError("Invalid reservation durability response")
        total = int(result[0])
        if total >= 0:
            # Timeouts can return zero instead of raising an exception.
            aof_acks = result[1]
            if not isinstance(aof_acks, (tuple, list)) or len(aof_acks) != 2:
                raise ValueError("Invalid AOF acknowledgment")
            if int(aof_acks[0]) < 1:
                raise ValueError("Reservation was not fsynced")
    except Exception as exc:
        logger.warning("TTS pilot reservation failed: %s", type(exc).__name__)
        raise TTSTrialBudgetExceeded("TTS pilot durable Redis ledger unavailable") from exc
    if total < 0:
        raise TTSTrialBudgetExceeded("TTS pilot $15 maximum allowance exhausted")
    remaining = ceiling - total
    logger.info("Chirp trial reserved_micro_usd=%s remaining_micro_usd=%s", charge, remaining)
    return remaining
