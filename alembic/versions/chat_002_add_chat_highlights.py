"""Add chat_highlights table

Revision ID: chat_002
Revises: 06351054f90b
Create Date: 2026-03-18

Adds persistent text highlights created via the in-chat selection popup.
Each row stores the selected text, character offsets within the source
message, and an optional annotation so the iOS client can re-render
yellow highlights on every conversation open.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'chat_002'
down_revision = '06351054f90b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_highlights',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.Integer,
                  sa.ForeignKey('organizations.id'), nullable=False,
                  index=True, server_default='1'),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), nullable=False, index=True),
        sa.Column('message_id', sa.String(36), nullable=True, index=True),
        sa.Column('selected_text', sa.Text, nullable=False),
        sa.Column('char_start', sa.Integer, nullable=True),
        sa.Column('char_end', sa.Integer, nullable=True),
        sa.Column('color', sa.String(20), nullable=False, server_default='#FBBF24'),
        sa.Column('annotation', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False, index=True),
    )

    op.create_index(
        'ix_chat_highlights_conv_user',
        'chat_highlights',
        ['conversation_id', 'user_id'],
    )
    op.create_index(
        'ix_chat_highlights_created',
        'chat_highlights',
        ['created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_chat_highlights_created', table_name='chat_highlights')
    op.drop_index('ix_chat_highlights_conv_user', table_name='chat_highlights')
    op.drop_table('chat_highlights')
