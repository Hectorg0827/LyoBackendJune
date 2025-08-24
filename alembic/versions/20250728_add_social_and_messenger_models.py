"""Add social and messenger models

Revision ID: 20250728_add_social
Revises: 003_educational_resources
Create Date: 2025-07-28 19:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '20250728_add_social'
down_revision = '003_educational_resources'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'stories',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('content_type', sa.String(50)),
        sa.Column('media_url', sa.String(500)),
        sa.Column('text_content', sa.String(1000)),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('expires_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('is_highlight', sa.Boolean, default=False),
        sa.Column('view_count', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
    )
    op.create_table(
        'story_views',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('story_id', sa.Integer, sa.ForeignKey('stories.id'), nullable=False),
        sa.Column('viewer_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('viewed_at', sa.DateTime, default=datetime.utcnow),
    )
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('type', sa.String(20)),
        sa.Column('name', sa.String(100)),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, default=datetime.utcnow),
    )
    op.create_table(
        'conversation_participants',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('conversation_id', sa.Integer, sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('joined_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('last_read_at', sa.DateTime),
        sa.Column('is_admin', sa.Boolean, default=False),
    )
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('conversation_id', sa.Integer, sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('sender_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('content', sa.Text),
        sa.Column('message_type', sa.String(20)),
        sa.Column('media_url', sa.String(500)),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('is_edited', sa.Boolean, default=False),
        sa.Column('is_deleted', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, default=datetime.utcnow),
    )
    op.create_table(
        'message_read_receipts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('message_id', sa.Integer, sa.ForeignKey('messages.id'), nullable=False),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('read_at', sa.DateTime, default=datetime.utcnow),
    )

def downgrade():
    op.drop_table('message_read_receipts')
    op.drop_table('messages')
    op.drop_table('conversation_participants')
    op.drop_table('conversations')
    op.drop_table('story_views')
    op.drop_table('stories')
