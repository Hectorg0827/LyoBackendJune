"""Add idempotency keys to canonical chat messages.

Revision ID: chat_003
Revises: users_sync_001
Create Date: 2026-07-17
"""
import sqlalchemy as sa
from alembic import op

revision = "chat_003"
down_revision = "users_sync_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("chat_messages")
    }
    if "client_message_id" not in columns:
        op.add_column(
            "chat_messages",
            sa.Column("client_message_id", sa.String(length=128), nullable=True),
        )

    indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("chat_messages")
    }
    if "uq_chat_messages_conv_client_id" not in indexes:
        op.create_index(
            "uq_chat_messages_conv_client_id",
            "chat_messages",
            ["conversation_id", "client_message_id"],
            unique=True,
        )


def downgrade() -> None:
    indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("chat_messages")
    }
    if "uq_chat_messages_conv_client_id" in indexes:
        op.drop_index(
            "uq_chat_messages_conv_client_id", table_name="chat_messages"
        )
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("chat_messages")
    }
    if "client_message_id" in columns:
        op.drop_column("chat_messages", "client_message_id")
