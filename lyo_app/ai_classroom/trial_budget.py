"""Fail-closed, cross-worker *reservation* ceiling for the Classroom trial.

The trial is deliberately opt-in, staging-only and separate from paid chat or
other LYO features.  A provider attempt reserves its *maximum* estimated cost
before any network request, including attempts that later fail or time out.
Reservations are never refunded: a failed request may still have been billed.
This is a pessimistic budget ledger, not a claim about the provider invoice.

The ledger key has no TTL. The staging Redis instance must retain this key
between restarts/deployments; Redis must not be configured with an evict-all
policy for a paid trial. Missing Redis, an unknown model or Redis errors deny
the call, never bypass the cap.
"""

from __future__ import annotations

import json
import logging
import math
import os
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

LIMIT_MICRO_USD = 60_000_000
# The 2026-11-05 ledger remains durable in Redis for audit and must not be
# deleted or credited back. The user authorized a *separate* $10 staging-only
# acceptance round on 2026-11-08, then an additional $10 within that same
# round on 2026-11-08. Retain its durable key and existing reservations while
# allowing the cumulative ceiling to reach $20. On 2026-11-10, the user
# authorized raising that *same* staging-only acceptance ledger to $60.
# Never reset the key or refund earlier reservations.
LEDGER_KEY = "lyo:classroom:trial:20261108:reserved_microusd"

# Deliberately conservative maxima in USD per million input/output tokens,
# including model thinking/output tokens. These are safety ceilings, NOT live
# provider prices. An unlisted provider cannot participate in this trial.
# Recheck ceilings against actual published model prices before enabling paid
# access; a provider price increase requires raising the ceiling or disabling.
MODEL_UPPER_USD_PER_MILLION: dict[str, tuple[int, int]] = {
    "gpt-4o-mini": (1, 3),
    "gpt-4o": (5, 20),
    "gemini-3.5-flash-lite": (4, 20),
    # Include headroom above higher-priority pricing tiers, not merely the
    # cheaper standard tier, so routing/tier changes cannot silently reduce
    # the trial's conservative pre-request reservation.
    "gemini-3.6-flash": (3, 17),
    "gemini-3.7-flash": (3, 17),
    "gemini-3.8-flash": (3, 17),
}

_RESERVE_LUA = """
local existing = tonumber(redis.call('GET', KEYS[1]) or '0')
local cost = tonumber(ARGV[1])
local ceiling = tonumber(ARGV[2])
if not existing or not cost or cost <= 0 or not ceiling or existing < 0 then
    return -2
end
if existing + cost > ceiling then
    return -1
end
return redis.call('INCRBY', KEYS[1], cost)
"""


class ClassroomTrialBudgetExceeded(RuntimeError):
    """The Classroom trial is spent or its safe spending ledger is unavailable."""


def trial_enabled() -> bool:
    return os.getenv("CLASSROOM_AI_TRIAL_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def configured_ceiling_micro_usd() -> int:
    """Never allow a configuration mistake to exceed the approved $60."""
    raw = os.getenv("CLASSROOM_AI_TRIAL_LIMIT_USD", "")
    try:
        configured = Decimal(raw)
        if not configured.is_finite() or configured <= 0 or configured > Decimal("60.00"):
            raise ValueError("Classroom trial limit must be positive and at most $60")
        micros = configured * 1_000_000
        if micros != micros.to_integral_exact():
            raise ValueError("Classroom trial limit has sub-microUSD precision")
        return int(micros)
    except (InvalidOperation, ValueError) as exc:
        raise ClassroomTrialBudgetExceeded("Classroom trial limit must be explicitly set, at most $60") from exc


def reserve_micro_usd(model: str, messages: list[dict], max_tokens: int,
                      response_format: dict | None = None) -> int:
    """Worst-case charge, rounded up to micro-dollars, before the provider call.

    UTF-8 bytes plus an allowance for message framing are a conservative
    upper bound for text tokenization. The response format is separately
    counted because providers may receive the JSON schema a second time.
    """
    rates = MODEL_UPPER_USD_PER_MILLION.get(model)
    if not rates:
        raise ClassroomTrialBudgetExceeded("Trial provider pricing is not approved")
    if max_tokens < 1 or max_tokens > 16384:
        raise ClassroomTrialBudgetExceeded("Invalid trial output token limit")
    serialized = json.dumps(messages, ensure_ascii=False, default=str)
    schema = json.dumps(response_format, ensure_ascii=False, default=str) if response_format else ""
    input_upper_tokens = len(serialized.encode("utf-8")) + len(schema.encode("utf-8")) + 512
    input_rate, output_rate = rates
    # Integer USD-per-million rates are exactly integer microUSD-per-token.
    return math.ceil(input_upper_tokens * input_rate + max_tokens * output_rate)


async def reserve_classroom_attempt(model: str, messages: list[dict],
                                    max_tokens: int, response_format: dict | None) -> int:
    """Reserve from the same durable Redis key across all workers/replicas.

    Returns the remaining reserved allowance in micro-USD on success. The
    caller must invoke this before *each* real provider attempt, not once for
    a resilience request containing fallback providers.
    """
    if not trial_enabled():
        return LIMIT_MICRO_USD

    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    if environment not in {"staging", "stage"}:
        raise ClassroomTrialBudgetExceeded("Classroom trial may run in staging only")

    ceiling = configured_ceiling_micro_usd()
    requested = reserve_micro_usd(model, messages, max_tokens, response_format)
    if requested > ceiling:
        raise ClassroomTrialBudgetExceeded("Classroom trial request exceeds spending ceiling")

    from lyo_app.core.redis_client import redis_client

    client = redis_client.client
    if client is None:
        raise ClassroomTrialBudgetExceeded("Classroom trial ledger is unavailable")
    try:
        # Eval is atomic, unlike GET followed by INCRBY; no worker can start a
        # billable request by racing another worker past the total $60 limit.
        total = int(await client.eval(_RESERVE_LUA, 1, LEDGER_KEY,
                                      requested, ceiling))
    except Exception as exc:
        logger.warning("Classroom trial ledger rejected a reservation: %s", type(exc).__name__)
        raise ClassroomTrialBudgetExceeded("Classroom trial ledger is unavailable") from exc
    if total < 0:
        raise ClassroomTrialBudgetExceeded("Classroom AI trial $60 budget exhausted")
    remaining = ceiling - total
    logger.info("Classroom trial provider=%s reserved_micro_usd=%d remaining_micro_usd=%d",
                model, requested, remaining)
    return remaining
