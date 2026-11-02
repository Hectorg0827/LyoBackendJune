"""Regression tests for idempotent Community event-capacity schema repair."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "community_capacity_001_reconcile_event_cap.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("community_capacity_001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migrate(connection, fn):
    with Operations.context(MigrationContext.configure(connection)):
        fn()


def test_upgrade_repairs_legacy_events_without_losing_data():
    migration = _module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE community_events (id INTEGER PRIMARY KEY, title VARCHAR(100))")
        )
        connection.execute(sa.text("INSERT INTO community_events (id, title) VALUES (3, 'Library tour')"))
        _migrate(connection, migration.upgrade)
        _migrate(connection, migration.upgrade)

        columns = {col["name"] for col in sa.inspect(connection).get_columns("community_events")}
        assert "max_attendees" in columns
        row = connection.execute(
            sa.text("SELECT title, max_attendees FROM community_events WHERE id = 3")
        ).one()
        assert row == ("Library tour", None)


def test_upgrade_preserves_capacity_on_existing_schema():
    migration = _module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE community_events "
                "(id INTEGER PRIMARY KEY, max_attendees INTEGER)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO community_events (id, max_attendees) VALUES (7, 24)")
        )
        _migrate(connection, migration.upgrade)
        assert connection.execute(
            sa.text("SELECT max_attendees FROM community_events WHERE id = 7")
        ).scalar_one() == 24


def test_upgrade_fails_loudly_when_events_table_is_missing():
    migration = _module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        with pytest.raises(RuntimeError, match="Community base schema"):
            _migrate(connection, migration.upgrade)
