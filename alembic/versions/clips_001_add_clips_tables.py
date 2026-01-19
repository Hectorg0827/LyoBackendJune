"""Add clips tables for educational video clips

Revision ID: clips_001
Revises: phase2_001
Create Date: 2026-01-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'clips_001'
down_revision = 'phase2_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create clips table
    op.create_table(
        'clips',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('video_url', sa.String(500), nullable=False),
        sa.Column('thumbnail_url', sa.String(500), nullable=True),
        sa.Column('duration_seconds', sa.Float(), server_default='0'),
        sa.Column('subject', sa.String(100), nullable=True),
        sa.Column('topic', sa.String(100), nullable=True),
        sa.Column('level', sa.String(50), server_default='beginner'),
        sa.Column('key_points', sa.JSON(), server_default='[]'),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), server_default='[]'),
        sa.Column('enable_course_generation', sa.Boolean(), server_default='true'),
        sa.Column('view_count', sa.Integer(), server_default='0'),
        sa.Column('like_count', sa.Integer(), server_default='0'),
        sa.Column('share_count', sa.Integer(), server_default='0'),
        sa.Column('is_public', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clips_id'), 'clips', ['id'], unique=False)
    op.create_index(op.f('ix_clips_user_id'), 'clips', ['user_id'], unique=False)
    op.create_index(op.f('ix_clips_subject'), 'clips', ['subject'], unique=False)
    op.create_index(op.f('ix_clips_topic'), 'clips', ['topic'], unique=False)
    
    # Create clip_likes table
    op.create_table(
        'clip_likes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clip_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['clip_id'], ['clips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('clip_id', 'user_id', name='uq_clip_user_like')
    )
    op.create_index(op.f('ix_clip_likes_id'), 'clip_likes', ['id'], unique=False)
    op.create_index(op.f('ix_clip_likes_clip_id'), 'clip_likes', ['clip_id'], unique=False)
    op.create_index(op.f('ix_clip_likes_user_id'), 'clip_likes', ['user_id'], unique=False)
    
    # Create clip_views table
    op.create_table(
        'clip_views',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clip_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),  # Nullable for anonymous views
        sa.Column('view_duration_seconds', sa.Float(), server_default='0'),
        sa.Column('completed', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['clip_id'], ['clips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clip_views_id'), 'clip_views', ['id'], unique=False)
    op.create_index(op.f('ix_clip_views_clip_id'), 'clip_views', ['clip_id'], unique=False)


def downgrade() -> None:
    op.drop_table('clip_views')
    op.drop_table('clip_likes')
    op.drop_table('clips')
