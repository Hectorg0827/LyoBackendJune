"""One-time guarded repair for the isolated Continuous Teaching preview database.

Do not run against production or shared databases. No existing rows are changed.
Native PostgreSQL enum additions are additive and cannot be undone safely once used.
The preview database was observed missing AI_SESSION, causing LearningEvent writes
to fail (2026-11-19). This is a narrow repair, not alembic stamp/upgrade.
"""
from __future__ import annotations

import asyncio
import os

EXPECTED_PROJECT = "8eb44c4c-d8df-46f2-b535-e75675823469"
EXPECTED_SERVICE = "fdedc7b9-1471-4f56-ac9d-c849ebf8837b"
REQUIRED_LABELS = (
    "QUIZ_ANSWER",
    "LESSON_COMPLETION",
    "AI_SESSION",
    "REFLECTION",
    "PROJECT",
    "VOICE_INTERACTION",
    "CLASSROOM_DEMONSTRATION",
)


def validate_target(env: dict[str, str]) -> None:
    """Fail closed unless executed by the designated preview backend."""
    if env.get("RAILWAY_PROJECT_ID") != EXPECTED_PROJECT:
        raise RuntimeError("Refusing enum repair outside isolated preview project")
    if env.get("RAILWAY_SERVICE_ID") != EXPECTED_SERVICE:
        raise RuntimeError("Refusing enum repair outside isolated preview backend")
    if env.get("RAILWAY_ENVIRONMENT_NAME", "").lower() != "staging":
        raise RuntimeError("Refusing enum repair outside staging")
    if env.get("LYO_CONTINUOUS_TEACHING_STAGING") != "1":
        raise RuntimeError("Refusing enum repair without staging feature gate")
    if env.get("LYO_CONTINUOUS_TEACHING_PRODUCTION_ENABLED") == "1":
        raise RuntimeError("Refusing enum repair with production gate enabled")
    if not env.get("DATABASE_URL"):
        raise RuntimeError("Refusing enum repair without preview DATABASE_URL")


async def repair(conn) -> tuple[str, ...]:
    """Check exact public.learning_events enum type, then add missing labels."""
    details = await conn.fetchrow(
        """
        SELECT t.typname AS type_name, t.typtype AS type_kind, n.nspname AS schema_name
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_type t ON t.oid = a.atttypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE c.oid = to_regclass('public.learning_events')
          AND a.attname = 'event_type'
          AND a.attnum > 0 AND NOT a.attisdropped
        """
    )
    if not details or details["type_name"] != "eventtype" or details["type_kind"] != "e":
        raise RuntimeError("Unexpected learning_events.event_type; refusing schema mutation")
    schema = details["schema_name"]
    if schema != "public":
        raise RuntimeError("Unexpected enum schema; refusing schema mutation")
    existing = {
        row["enumlabel"]
        for row in await conn.fetch(
            """
            SELECT e.enumlabel FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            JOIN pg_namespace n ON t.typnamespace = n.oid
            WHERE n.nspname = 'public' AND t.typname = 'eventtype'
            """
        )
    }
    missing = tuple(label for label in REQUIRED_LABELS if label not in existing)
    # asyncpg does not wrap standalone statements in a transaction. PostgreSQL's
    # ADD VALUE is committed before the follow-up validation query below.
    for label in missing:
        await conn.execute(f"ALTER TYPE public.eventtype ADD VALUE IF NOT EXISTS '{label}'")
    after = {
        row["enumlabel"]
        for row in await conn.fetch(
            """
            SELECT e.enumlabel FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            JOIN pg_namespace n ON t.typnamespace = n.oid
            WHERE n.nspname = 'public' AND t.typname = 'eventtype'
            """
        )
    }
    if not set(REQUIRED_LABELS).issubset(after):
        raise RuntimeError("Enum repair verification failed")
    return missing


async def main() -> None:
    validate_target(dict(os.environ))
    import asyncpg

    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(dsn)
    try:
        missing = await repair(conn)
        print("Preview enum schema verified; labels added:", ", ".join(missing) if missing else "none")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
