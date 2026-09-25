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


MIGRATION_003 = MIGRATION.with_name("community_map_003_discovery_contract.py")


def _load_migration_003():
    spec = importlib.util.spec_from_file_location("community_map_003", MIGRATION_003)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_discovery_contract_upgrade_is_repeatable_and_repairs_reports():
    module = _load_migration_003()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(
            sa.text(
                """
                CREATE TABLE community_events (
                    id INTEGER PRIMARY KEY,
                    organizer_id INTEGER NOT NULL,
                    status VARCHAR(20),
                    end_time DATETIME,
                    event_type VARCHAR(30),
                    is_online BOOLEAN NOT NULL DEFAULT 0,
                    latitude FLOAT,
                    longitude FLOAT
                )
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO community_events (id, organizer_id, is_online, latitude, longitude)
                VALUES (1, 7, 0, 40.7, -74.0), (2, 7, 1, NULL, NULL), (3, 7, 1, 40.7, -74.0)
                """
            )
        )
        # The ORM-shaped legacy table: enum *names* and the singular column.
        connection.execute(
            sa.text(
                """
                CREATE TABLE content_reports (
                    id VARCHAR(36) PRIMARY KEY,
                    reporter_id INTEGER,
                    target_type VARCHAR(20),
                    target_id VARCHAR(36),
                    reason VARCHAR(30),
                    status VARCHAR(20),
                    resolution_note TEXT
                )
                """
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO content_reports VALUES ('r1', 7, 'POST', '1', 'HATE_SPEECH', 'PENDING', 'n')"
            )
        )

        _with_ops(connection, module.upgrade)
        _with_ops(connection, module.upgrade)

        inspector = sa.inspect(connection)
        columns = {column["name"] for column in inspector.get_columns("community_events")}
        assert {
            "visibility", "price_type", "price_amount", "currency", "website_url",
            "organizer_name", "venue_name", "address", "attendance_mode",
            "moderation_status", "client_request_id",
        } <= columns
        modes = dict(
            connection.execute(sa.text("SELECT id, attendance_mode FROM community_events")).all()
        )
        assert modes == {1: "in_person", 2: "online", 3: "hybrid"}
        assert connection.scalar(
            sa.text("SELECT visibility FROM community_events WHERE id = 1")
        ) == "public"

        report = connection.execute(
            sa.text("SELECT target_type, reason, status, resolution_notes FROM content_reports")
        ).one()
        assert tuple(report) == ("post", "hate_speech", "pending", "n")

        connection.execute(
            sa.text(
                "INSERT INTO community_events (id, organizer_id, is_online, client_request_id) "
                "VALUES (10, 7, 0, 'same')"
            )
        )
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO community_events (id, organizer_id, is_online, client_request_id) "
                    "VALUES (11, 7, 0, 'same')"
                )
            )
