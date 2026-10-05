"""Durable model-usage attribution for Learning OS teaching sessions.

The provider layer is shared by many product features. A ContextVar lets only
Learning OS call sites opt into attribution without teaching the generic model
client about conversations, classrooms, or learner evidence.

Usage is written with an independent short-lived DB session. That matters for
Classroom prefetch: speculative authoring can outlive the request that started
it and must never share the live Classroom AsyncSession.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterator, Optional


@dataclass(frozen=True)
class ModelUsage:
    model: str
    tokens_used: int
    latency_ms: int
    cache_hit: bool = False
    completion_status: str = "completed"
    usage_reported: bool = True


UsageRecorder = Callable[[ModelUsage], Awaitable[None]]
_usage_recorder: ContextVar[Optional[UsageRecorder]] = ContextVar(
    "lyo_learning_os_model_usage_recorder",
    default=None,
)
_usage_tasks: set[asyncio.Task[None]] = set()


def _finish_usage_task(task: asyncio.Task[None]) -> None:
    """Retain fire-and-forget telemetry tasks until completion and consume errors."""
    _usage_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Learning OS model usage task failed: %s",
            type(exc).__name__,
        )


@contextmanager
def bind_model_usage(recorder: Optional[UsageRecorder]) -> Iterator[None]:
    """Bind one request/session recorder for model calls in this async context."""
    token = _usage_recorder.set(recorder)
    try:
        yield
    finally:
        _usage_recorder.reset(token)


async def capture_model_usage(
    *,
    model: Optional[str],
    tokens_used: object,
    latency_ms: object,
    cache_hit: bool = False,
    completion_status: str = "completed",
    usage_reported: bool = True,
) -> None:
    """Send bounded provider usage to the active Learning OS recorder.

    Telemetry can never break a learner response. Invalid provider metadata is
    normalized rather than trusted, and recorder errors are swallowed by the
    recorder itself.
    """
    recorder = _usage_recorder.get()
    if recorder is None:
        return
    try:
        tokens = max(0, int(tokens_used or 0))
    except (TypeError, ValueError):
        tokens = 0
    try:
        latency = max(0, int(latency_ms or 0))
    except (TypeError, ValueError):
        latency = 0
    usage = ModelUsage(
        model=str(model or "unknown")[:80],
        tokens_used=tokens,
        latency_ms=latency,
        cache_hit=bool(cache_hit),
        completion_status=(completion_status if completion_status in {
            "completed", "incomplete", "cancelled", "failed"
        } else "failed"),
        usage_reported=bool(usage_reported),
    )
    # Observability must never sit on the learner response path. The durable
    # recorder can wait on a busy database pool without delaying a successful
    # provider result or consuming the caller's routing/teaching timeout.
    task = asyncio.create_task(
        recorder(usage),
        name="learning-os-model-usage",
    )
    _usage_tasks.add(task)
    task.add_done_callback(_finish_usage_task)


def learning_event_usage_recorder(
    *,
    user_id: object,
    surface: str,
    session_id: object,
    model_tier: Optional[str] = None,
) -> Optional[UsageRecorder]:
    """Build a durable recorder keyed to the same identity as learner evidence."""
    try:
        learner_id = int(user_id)
    except (TypeError, ValueError):
        return None
    if learner_id <= 0 or not session_id:
        return None

    bounded_surface = str(surface or "unknown")[:32]
    bounded_session = str(session_id)[:128]
    bounded_tier = str(model_tier or "unknown")[:32]

    async def record(usage: ModelUsage) -> None:
        # Import lazily: the provider client is initialized during application
        # bootstrap, before every ORM model necessarily is.
        import logging

        logger = logging.getLogger(__name__)
        try:
            from lyo_app.core.database import AsyncSessionLocal
            from lyo_app.events.models import EventType, LearningEvent

            async with AsyncSessionLocal() as db:
                db.add(
                    LearningEvent(
                        user_id=learner_id,
                        event_type=EventType.AI_SESSION,
                        source_surface=bounded_surface,
                        metadata_json={
                            "event_kind": "model_usage",
                            "session_id": bounded_session,
                            "model": usage.model,
                            "tokens_used": usage.tokens_used,
                            "latency_ms": usage.latency_ms,
                            "cache_hit": usage.cache_hit,
                            "model_tier": bounded_tier,
                            "completion_status": usage.completion_status,
                            "usage_reported": usage.usage_reported,
                        },
                    )
                )
                await db.commit()
        except Exception as exc:
            logger.warning(
                "Learning OS model usage was not persisted: %s",
                type(exc).__name__,
            )

    return record
