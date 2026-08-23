"""Regression tests for the production Community map repair migration."""

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
    / "community_map_002_reconcile_schema.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("community_map_002", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _with_ops(connection, function):
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        function()


def _create_map_tables(connection):
    connection.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    connection.execute(sa.text("CREATE TABLE community_events (id INTEGER PRIMARY KEY)"))
    connection.execute(sa.text("CREATE TABLE study_groups (id INTEGER PRIMARY KEY)"))
    connection.execute(sa.text("CREATE TABLE private_lessons (id INTEGER PRIMARY KEY)"))


def test_upgrade_repairs_an_existing_partial_saved_node_table():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        _create_map_tables(connection)
        connection.execute(
            sa.text(
                """
                CREATE TABLE community_saved_nodes (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    node_kind VARCHAR(50) NOT NULL,
                    node_id VARCHAR(255) NOT NULL
                )
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO community_saved_nodes (id, user_id, node_kind, node_id)
                VALUES
                    (1, 7, 'event', '42'),
                    (2, 7, 'event', '42')
                """
            )
        )

        _with_ops(connection, module.upgrade)
        _with_ops(connection, module.upgrade)

        inspector = sa.inspect(connection)
        columns = {
            column["name"]
            for column in inspector.get_columns("community_saved_nodes")
        }
        assert {
            "id",
            "user_id",
            "node_kind",
            "node_id",
            "snapshot",
            "created_at",
            "updated_at",
        }.issubset(columns)
        assert {
            "ix_community_saved_nodes_id",
            "ix_community_saved_nodes_user_id",
            "ix_community_saved_nodes_node_kind",
            "ix_community_saved_nodes_node_id",
        }.issubset(
            {index["name"] for index in inspector.get_indexes("community_saved_nodes")}
        )
        assert connection.scalar(
            sa.text("SELECT COUNT(*) FROM community_saved_nodes")
        ) == 1

        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO community_saved_nodes (
                        id, user_id, node_kind, node_id, snapshot
                    ) VALUES (3, 7, 'event', '42', '{}')
                    """
                )
            )


def test_upgrade_preserves_an_unidentifiable_partial_table_as_a_backup():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        _create_map_tables(connection)
        connection.execute(
            sa.text(
                """
                CREATE TABLE community_saved_nodes (
                    id INTEGER PRIMARY KEY,
                    snapshot JSON
                )
                """
            )
        )
        connection.execute(
            sa.text("INSERT INTO community_saved_nodes (id, snapshot) VALUES (1, '{}')")
        )
        connection.execute(
            sa.text(
                "CREATE INDEX ix_community_saved_nodes_id "
                "ON community_saved_nodes (id)"
            )
        )

        _with_ops(connection, module.upgrade)

        inspector = sa.inspect(connection)
        assert inspector.has_table("community_saved_nodes")
        assert inspector.has_table("community_saved_nodes_partial_backup_002")
        assert connection.scalar(
            sa.text("SELECT COUNT(*) FROM community_saved_nodes_partial_backup_002")
        ) == 1
        assert {
            "id",
            "user_id",
            "node_kind",
            "node_id",
            "snapshot",
            "created_at",
            "updated_at",
        } == {
            column["name"]
            for column in inspector.get_columns("community_saved_nodes")
        }
