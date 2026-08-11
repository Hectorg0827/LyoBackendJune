"""Verify the chat_messages.blocks migration runs and is idempotent.

The app boots via init_db's create_all on some environments and via
`alembic upgrade heads` on others, so this column can already exist when the
migration runs. Both orders must succeed.
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.runtime.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "chat_003_add_message_blocks.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("chat_003", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(conn, table):
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _with_ops(conn, fn):
    """Run a migration function against a live connection."""
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        fn()


def test_migration_declares_the_chat_lineage():
    module = _load_migration()
    assert module.revision == "chat_003"
    assert module.down_revision == "chat_002"


def test_upgrade_adds_column_and_is_idempotent():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE chat_messages (id VARCHAR(36) PRIMARY KEY, content TEXT)"
        ))
        assert "blocks" not in _columns(conn, "chat_messages")

        _with_ops(conn, module.upgrade)
        assert "blocks" in _columns(conn, "chat_messages")

        # Running again must not raise (create_all may have already added it).
        _with_ops(conn, module.upgrade)
        assert "blocks" in _columns(conn, "chat_messages")


def test_upgrade_is_a_noop_when_the_table_is_absent():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _with_ops(conn, module.upgrade)  # must not raise


def test_downgrade_removes_the_column():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE chat_messages (id VARCHAR(36) PRIMARY KEY, content TEXT)"
        ))
        _with_ops(conn, module.upgrade)
        _with_ops(conn, module.downgrade)
        assert "blocks" not in _columns(conn, "chat_messages")
        # Idempotent in this direction too.
        _with_ops(conn, module.downgrade)


def test_model_round_trips_blocks_json():
    """The ORM column actually stores and returns structured blocks."""
    from lyo_app.ai.schemas.smart_block import SmartBlock

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    messages = sa.Table(
        "chat_messages", metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("blocks", sa.JSON, nullable=True),
    )
    metadata.create_all(engine)

    payload = [SmartBlock.callout("trap", "trap").model_dump(mode="json")]
    with engine.begin() as conn:
        conn.execute(messages.insert().values(id="m1", blocks=payload))
        conn.execute(messages.insert().values(id="m2", blocks=None))

    with engine.connect() as conn:
        rows = {r.id: r.blocks for r in conn.execute(sa.select(messages))}

    assert rows["m1"][0]["subtype"] == "callout"
    assert rows["m1"][0]["content"]["style"] == "trap"
    # Existing/plain messages stay null rather than needing a backfill.
    assert rows["m2"] is None
