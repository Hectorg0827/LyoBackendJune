"""Direct messages: add the message_metadata column the Message model reads.

Revision ID: messaging_001
Revises: community_map_004
Create Date: 2026-09-26

`20250728_add_social_and_messenger_models` created `messages` with a column
named `metadata`, but `lyo_app.models.social.Message` maps
`message_metadata`. On a database built by migrations, every query that
loads a Message (listing conversations, opening one, sending) therefore
failed with "column messages.message_metadata does not exist", which the
web Messages page showed as an empty list.

This adds `message_metadata` when it is missing and copies any existing
`metadata` values into it. The old column is left in place (nothing reads
it any more, and dropping data is not this revision's job). When the column
already exists (a database created by `create_all`), or the table does not
exist yet, the revision does nothing, so it is safe to re-run.
"""

import sqlalchemy as sa
from alembic import op

revision = "messaging_001"
down_revision = "community_map_004"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    columns = _columns("messages")
    if not columns or "message_metadata" in columns:
        return
    op.add_column("messages", sa.Column("message_metadata", sa.JSON(), nullable=True))
    if "metadata" in columns:
        op.execute("UPDATE messages SET message_metadata = metadata WHERE metadata IS NOT NULL")


def downgrade() -> None:
    columns = _columns("messages")
    # Only remove the column this revision added; a create_all database had it
    # from the start and "metadata" is its only other copy of the data.
    if "message_metadata" in columns and "metadata" in columns:
        op.drop_column("messages", "message_metadata")
