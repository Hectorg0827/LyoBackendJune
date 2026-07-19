"""Widen chat session_id columns to fit web device ids

Revision ID: chat_004
Revises: catalog_001
Create Date: 2026-07-18

The web client identifies each browser as "web-<uuid>" (40 chars), which the
chat conversation endpoints store as session_id. The columns were VARCHAR(36),
so every conversation create from a real browser failed the INSERT with a
StringDataRightTruncation and surfaced as a 500 — making web chat unusable.
Widen to VARCHAR(64) on chat_conversations and chat_telemetry.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'chat_004'
down_revision = 'catalog_001'
branch_labels = None
depends_on = None


def _widen(table: str, column: str, nullable: bool) -> None:
    if not sa.inspect(op.get_bind()).has_table(table):
        return
    op.alter_column(
        table,
        column,
        existing_type=sa.String(36),
        type_=sa.String(64),
        existing_nullable=nullable,
    )


def upgrade() -> None:
    _widen('chat_conversations', 'session_id', nullable=False)
    _widen('chat_telemetry', 'session_id', nullable=True)


def downgrade() -> None:
    # Truncate any values that would no longer fit before narrowing back.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table('chat_conversations'):
        bind.execute(sa.text(
            "UPDATE chat_conversations SET session_id = LEFT(session_id, 36)"
        ))
        op.alter_column(
            'chat_conversations', 'session_id',
            existing_type=sa.String(64), type_=sa.String(36),
            existing_nullable=False,
        )
    if inspector.has_table('chat_telemetry'):
        bind.execute(sa.text(
            "UPDATE chat_telemetry SET session_id = LEFT(session_id, 36)"
        ))
        op.alter_column(
            'chat_telemetry', 'session_id',
            existing_type=sa.String(64), type_=sa.String(36),
            existing_nullable=True,
        )
