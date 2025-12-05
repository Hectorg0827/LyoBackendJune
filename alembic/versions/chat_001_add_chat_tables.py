"""Add chat module tables

Revision ID: chat_001
Revises: 
Create Date: 2024-12-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'chat_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create chat_courses table
    op.create_table(
        'chat_courses',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=True, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('topic', sa.String(200), nullable=False, index=True),
        sa.Column('difficulty', sa.String(50), default='intermediate'),
        sa.Column('modules', sa.JSON, nullable=True),
        sa.Column('learning_objectives', sa.JSON, nullable=True),
        sa.Column('prerequisites', sa.JSON, nullable=True),
        sa.Column('estimated_hours', sa.Float, nullable=True),
        sa.Column('generated_by_mode', sa.String(50), default='course_planner'),
        sa.Column('source_conversation_id', sa.String(36), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('is_published', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    op.create_index('ix_chat_courses_user_topic', 'chat_courses', ['user_id', 'topic'])
    op.create_index('ix_chat_courses_created', 'chat_courses', ['created_at'])
    
    # Create chat_notes table
    op.create_table(
        'chat_notes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('topic', sa.String(200), nullable=True, index=True),
        sa.Column('tags', sa.JSON, nullable=True),
        sa.Column('source_message_id', sa.String(36), nullable=True),
        sa.Column('source_conversation_id', sa.String(36), nullable=True),
        sa.Column('related_course_id', sa.String(36), sa.ForeignKey('chat_courses.id'), nullable=True),
        sa.Column('note_type', sa.String(50), default='general'),
        sa.Column('importance', sa.Integer, default=0),
        sa.Column('is_archived', sa.Boolean, default=False),
        sa.Column('is_favorite', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    op.create_index('ix_chat_notes_user_topic', 'chat_notes', ['user_id', 'topic'])
    op.create_index('ix_chat_notes_created', 'chat_notes', ['created_at'])
    
    # Create chat_conversations table
    op.create_table(
        'chat_conversations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=True, index=True),
        sa.Column('session_id', sa.String(36), nullable=False, index=True),
        sa.Column('initial_mode', sa.String(50), default='general'),
        sa.Column('current_mode', sa.String(50), default='general'),
        sa.Column('topic', sa.String(200), nullable=True),
        sa.Column('message_count', sa.Integer, default=0),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('context_data', sa.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create chat_messages table
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('chat_conversations.id'), nullable=False, index=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('mode_used', sa.String(50), default='general'),
        sa.Column('action_triggered', sa.String(50), nullable=True),
        sa.Column('tokens_used', sa.Integer, nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('latency_ms', sa.Integer, nullable=True),
        sa.Column('ctas', sa.JSON, nullable=True),
        sa.Column('chip_actions', sa.JSON, nullable=True),
        sa.Column('cache_hit', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    op.create_index('ix_chat_messages_conv_created', 'chat_messages', ['conversation_id', 'created_at'])
    
    # Create chat_telemetry table
    op.create_table(
        'chat_telemetry',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_type', sa.String(50), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), nullable=True, index=True),
        sa.Column('session_id', sa.String(36), nullable=True),
        sa.Column('conversation_id', sa.String(36), nullable=True),
        sa.Column('message_id', sa.String(36), nullable=True),
        sa.Column('mode_chosen', sa.String(50), nullable=True),
        sa.Column('tokens_used', sa.Integer, nullable=True),
        sa.Column('cache_hit', sa.Boolean, default=False),
        sa.Column('cta_clicked', sa.String(100), nullable=True),
        sa.Column('chip_action_used', sa.String(50), nullable=True),
        sa.Column('latency_ms', sa.Integer, nullable=True),
        sa.Column('extra_data', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    
    op.create_index('ix_chat_telemetry_event_time', 'chat_telemetry', ['event_type', 'created_at'])


def downgrade() -> None:
    op.drop_table('chat_telemetry')
    op.drop_table('chat_messages')
    op.drop_table('chat_conversations')
    op.drop_table('chat_notes')
    op.drop_table('chat_courses')
