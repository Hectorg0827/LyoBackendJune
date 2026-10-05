"""Persist completed Chat answers independently of the SSE request lifetime."""

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.chat.stores import conversation_store


logger = logging.getLogger(__name__)
_assistant_writes: set[asyncio.Task] = set()


def _finish_write(task: asyncio.Task) -> None:
    _assistant_writes.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning("Completed Chat answer persistence was cancelled")
    except Exception:
        logger.exception("Completed Chat answer persistence failed")


def schedule_assistant_message(
    db: AsyncSession, conversation_id: str, *, store: Any = conversation_store, **message: Any
) -> asyncio.Task:
    """Own a bounded, idempotent write before yielding any completed answer.

    The independent session prevents a disconnect from closing the write's
    session, or concurrent streaming work from sharing an AsyncSession. The
    store's client_message_id uniqueness guard owns retry deduplication.
    """
    async def persist() -> None:
        if isinstance(db, AsyncSession):
            async with AsyncSession(bind=db.bind, expire_on_commit=False) as write_db:
                await store.add_message(
                    write_db, conversation_id, role="assistant", **message
                )
        else:
            # Lightweight adapters used by route tests implement the store,
            # rather than SQLAlchemy sessions.
            await store.add_message(
                db, conversation_id, role="assistant", **message
            )

    task = asyncio.create_task(
        asyncio.wait_for(persist(), timeout=15.0),
        name="chat-completed-answer-persistence",
    )
    _assistant_writes.add(task)
    task.add_done_callback(_finish_write)
    return task


async def finish_assistant_messages(tasks: list[asyncio.Task]) -> None:
    """Flush on iterator close without transferring cancellation to a write."""
    if tasks:
        await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
