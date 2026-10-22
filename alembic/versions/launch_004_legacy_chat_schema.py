"""Bring legacy Chat tables to the current durable SSE/Coach ORM contract.

Revision ID: launch_004
Revises: launch_003

The historical chat_001/chat_002 migrations did not have TenantMixin columns,
and chat_messages predates client idempotency IDs and durable SmartBlocks.
Rows and foreign keys are retained; absent columns are added only once.
"""
from alembic import op
import sqlalchemy as sa

revision = "launch_004"
down_revision = "launch_003"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table):
    inspector = _inspector()
    if not inspector.has_table(table):
        raise RuntimeError(f"Required Chat table missing during upgrade: {table}")
    return {row["name"] for row in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if not _inspector().has_table("organizations"):
        raise RuntimeError("Tenant table missing before Chat upgrade")
    if bind.execute(sa.text("SELECT id FROM organizations WHERE id=1")).scalar_one_or_none() is None:
        raise RuntimeError("Default tenant missing; refusing to orphan historical Chat records")

    for table in (
        "chat_courses", "chat_notes", "chat_conversations",
        "chat_messages", "chat_telemetry", "chat_highlights",
    ):
        if "organization_id" not in _columns(table):
            op.add_column(
                table, sa.Column("organization_id", sa.Integer(),
                                 nullable=False, server_default="1")
            )
            op.create_foreign_key(
                f"fk_{table}_organization_id_organizations",
                table, "organizations", ["organization_id"], ["id"]
            )
            op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])

    if "client_message_id" not in _columns("chat_messages"):
        op.add_column("chat_messages", sa.Column(
            "client_message_id", sa.String(128), nullable=True
        ))
    if "blocks" not in _columns("chat_messages"):
        op.add_column("chat_messages", sa.Column("blocks", sa.JSON(), nullable=True))

    # The web device ID may contain the "web-" prefix plus a full UUID.
    if bind.dialect.name == "postgresql":
        for table in ("chat_conversations", "chat_telemetry"):
            op.execute(f"ALTER TABLE {table} ALTER COLUMN session_id TYPE VARCHAR(64)")

    indices = {ix["name"] for ix in _inspector().get_indexes("chat_messages")}
    if "uq_chat_messages_conv_client_id" not in indices:
        op.create_index(
            "uq_chat_messages_conv_client_id", "chat_messages",
            ["conversation_id", "client_message_id"], unique=True
        )


def downgrade():
    # Never drop chat records, tenant ownership, or idempotency IDs silently.
    pass
