"""Fresh-install regression for Chat's legacy default organization FK."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from sqlalchemy import create_engine, select

from lyo_app.tenants.models import Organization


def _migration():
    path = (Path(__file__).resolve().parents[1] /
            "alembic/versions/coach_003_default_tenant_bootstrap.py")
    spec = spec_from_file_location("coach_003_default_tenant_bootstrap", path)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_new_database_has_chat_default_tenant_after_migration(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        Organization.__table__.create(conn)
        migration = _migration()
        monkeypatch.setattr(migration.op, "get_bind", lambda: conn)
        migration.upgrade()
        row = conn.execute(select(Organization.__table__).where(Organization.id == 1)).one()
        assert row._mapping["slug"] == "lyo-default-tenant"
        migration.upgrade()
        assert len(conn.execute(select(Organization.id)).all()) == 1


def test_existing_default_tenant_is_never_overwritten(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        Organization.__table__.create(conn)
        conn.execute(Organization.__table__.insert().values(
            id=1, name="Existing Organization", slug="existing-default",
            plan_tier="enterprise", is_active=True,
            monthly_api_calls=10, monthly_ai_tokens=100,
        ))
        migration = _migration()
        monkeypatch.setattr(migration.op, "get_bind", lambda: conn)
        migration.upgrade()
        row = conn.execute(select(Organization.__table__).where(Organization.id == 1)).one()._mapping
        assert row["name"] == "Existing Organization"
        assert row["slug"] == "existing-default"
        assert row["plan_tier"] == "enterprise"
        assert row["monthly_api_calls"] == 10



import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from lyo_app.core.database import _ensure_default_chat_tenant


@pytest.mark.asyncio
async def test_application_bootstrap_preserves_organization_and_is_idempotent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Organization.__table__.create)
            await _ensure_default_chat_tenant(conn)
            await _ensure_default_chat_tenant(conn)
            entries = (await conn.execute(select(Organization.__table__))).all()
            assert len(entries) == 1
            assert entries[0]._mapping["id"] == 1
            assert entries[0]._mapping["name"] == "Lyo Default"
    finally:
        await engine.dispose()
