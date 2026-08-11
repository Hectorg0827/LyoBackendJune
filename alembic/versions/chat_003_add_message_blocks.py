"""Add blocks column to chat_messages

Revision ID: chat_003
Revises: chat_002
Create Date: 2026-08-11

Stores the structured SmartBlocks rendered with an assistant message.

Two things depend on this being persisted rather than emitted-and-forgotten:
a reloaded conversation keeps its lesson structure instead of collapsing to
plain text, and grading an in-chat check reads the correct answer back from
this column, so the client is never the authority on whether an answer was
right.

Nullable, so every existing message and every non-lesson turn is unaffected.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'chat_003'
down_revision = 'chat_002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # chat_messages is created by the chat_001 migration on a migration-managed
    # database, but init_db's create_all may already have added this column on
    # environments that boot the app before running migrations. Guard so the
    # upgrade is idempotent across both paths.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('chat_messages'):
        return
    existing = {col['name'] for col in inspector.get_columns('chat_messages')}
    if 'blocks' not in existing:
        op.add_column('chat_messages', sa.Column('blocks', sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('chat_messages'):
        return
    existing = {col['name'] for col in inspector.get_columns('chat_messages')}
    if 'blocks' in existing:
        op.drop_column('chat_messages', 'blocks')
