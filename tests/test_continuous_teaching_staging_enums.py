"""The staging enum repair must be narrowly scoped and idempotent."""
from unittest.mock import AsyncMock
import pytest

from scripts.repair_continuous_teaching_staging_enums import (
    EXPECTED_PROJECT, EXPECTED_SERVICE, REQUIRED_LABELS, repair, validate_target,
)

EXPECTED_ENV = {
    "RAILWAY_PROJECT_ID": EXPECTED_PROJECT,
    "RAILWAY_SERVICE_ID": EXPECTED_SERVICE,
    "RAILWAY_ENVIRONMENT_NAME": "staging",
    "LYO_CONTINUOUS_TEACHING_STAGING": "1",
    "LYO_CONTINUOUS_TEACHING_PRODUCTION_ENABLED": "0",
    "DATABASE_URL": "postgresql+asyncpg://placeholder/preview",
}


def test_guard_requires_exact_isolated_staging_target():
    validate_target(EXPECTED_ENV)
    for field, value in [
        ("RAILWAY_PROJECT_ID", "another-project"),
        ("RAILWAY_SERVICE_ID", "another-service"),
        ("RAILWAY_ENVIRONMENT_NAME", "production"),
        ("LYO_CONTINUOUS_TEACHING_STAGING", "0"),
        ("LYO_CONTINUOUS_TEACHING_PRODUCTION_ENABLED", "1"),
        ("DATABASE_URL", ""),
    ]:
        with pytest.raises(RuntimeError):
            validate_target({**EXPECTED_ENV, field: value})


@pytest.mark.asyncio
async def test_additive_enum_repair_and_idempotent_recheck():
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "type_name": "eventtype", "type_kind": "e", "schema_name": "public",
    }
    available = {"QUIZ_ANSWER", "LESSON_COMPLETION"}
    async def fetch(_sql):
        return [{"enumlabel": s} for s in sorted(available)]
    async def execute(sql):
        assert sql.startswith("ALTER TYPE public.eventtype ADD VALUE IF NOT EXISTS '")
        label = sql.split("'")[1]
        available.add(label)
    conn.fetch.side_effect = fetch
    conn.execute.side_effect = execute
    added = await repair(conn)
    assert added == tuple(label for label in REQUIRED_LABELS if label not in {"QUIZ_ANSWER", "LESSON_COMPLETION"})
    assert set(REQUIRED_LABELS).issubset(available)
    assert await repair(conn) == ()
    assert conn.execute.await_count == len(added)


@pytest.mark.asyncio
async def test_unknown_schema_never_executes_mutations():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"type_name": "unexpected", "type_kind": "e", "schema_name": "public"}
    with pytest.raises(RuntimeError, match="Unexpected"):
        await repair(conn)
    conn.execute.assert_not_awaited()
