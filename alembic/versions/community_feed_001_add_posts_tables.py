"""Add community feed tables for posts, comments, and moderation

Revision ID: community_feed_001
Revises: 20250728_add_social
Create Date: 2025-01-28 20:00:00.000000

This migration adds:
- community_posts: Social feed posts with reactions
- post_comments: Threaded comments with replies
- post_likes: Like tracking for posts
- post_bookmarks: Bookmark tracking for posts
- content_reports: Content moderation reports
- user_blocks: User blocking functionality
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'community_feed_001'
down_revision = '20250728_add_social'
branch_labels = None
depends_on = None


def upgrade():
    # ==========================================================================
    # Enum Types
    # ==========================================================================
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE post_type AS ENUM ('text', 'poll', 'question', 'achievement', 'course_share', 'study_group');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE post_visibility AS ENUM ('public', 'followers', 'group', 'private');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE report_target_type AS ENUM ('post', 'comment', 'user');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE report_reason AS ENUM ('spam', 'harassment', 'hate_speech', 'misinformation', 'inappropriate', 'other');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE report_status AS ENUM ('pending', 'reviewed', 'resolved', 'dismissed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # ==========================================================================
    # Community Posts Table
    # ==========================================================================
    op.create_table(
        'community_posts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('author_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('author_name', sa.String(100), nullable=False),
        sa.Column('author_avatar', sa.String(500)),
        sa.Column('author_level', sa.Integer, default=1),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('media_urls', postgresql.ARRAY(sa.String), default=[]),
        sa.Column('tags', postgresql.ARRAY(sa.String), default=[]),
        sa.Column('like_count', sa.Integer, default=0),
        sa.Column('comment_count', sa.Integer, default=0),
        sa.Column('post_type', postgresql.ENUM('text', 'poll', 'question', 'achievement', 'course_share', 'study_group', name='post_type', create_type=False), default='text'),
        sa.Column('visibility', postgresql.ENUM('public', 'followers', 'group', 'private', name='post_visibility', create_type=False), default='public'),
        sa.Column('linked_course_id', sa.Integer, sa.ForeignKey('courses.id', ondelete='SET NULL')),
        sa.Column('linked_group_id', sa.Integer, sa.ForeignKey('study_groups.id', ondelete='SET NULL')),
        sa.Column('is_pinned', sa.Boolean, default=False),
        sa.Column('is_edited', sa.Boolean, default=False),
        sa.Column('is_deleted', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow, index=True),
        sa.Column('updated_at', sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    )
    
    # Index for feed queries
    op.create_index('ix_community_posts_feed', 'community_posts', 
                    ['visibility', 'is_deleted', 'created_at'], 
                    postgresql_ops={'created_at': 'DESC'})
    op.create_index('ix_community_posts_tags', 'community_posts', ['tags'], postgresql_using='gin')

    # ==========================================================================
    # Post Comments Table
    # ==========================================================================
    op.create_table(
        'post_comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('post_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('community_posts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('author_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('author_name', sa.String(100), nullable=False),
        sa.Column('author_avatar', sa.String(500)),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('like_count', sa.Integer, default=0),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('post_comments.id', ondelete='CASCADE')),
        sa.Column('reply_count', sa.Integer, default=0),
        sa.Column('is_edited', sa.Boolean, default=False),
        sa.Column('is_deleted', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow, index=True),
        sa.Column('updated_at', sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    )

    # ==========================================================================
    # Post Likes Table (Junction)
    # ==========================================================================
    op.create_table(
        'post_likes',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('post_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('community_posts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_post_likes_post_user'),
    )
    op.create_index('ix_post_likes_user', 'post_likes', ['user_id'])

    # ==========================================================================
    # Post Bookmarks Table (Junction)
    # ==========================================================================
    op.create_table(
        'post_bookmarks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('post_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('community_posts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_post_bookmarks_post_user'),
    )
    op.create_index('ix_post_bookmarks_user', 'post_bookmarks', ['user_id'])

    # ==========================================================================
    # Content Reports Table
    # ==========================================================================
    op.create_table(
        'content_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('reporter_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('target_type', postgresql.ENUM('post', 'comment', 'user', name='report_target_type', create_type=False), nullable=False),
        sa.Column('target_id', sa.String(36), nullable=False),
        sa.Column('reason', postgresql.ENUM('spam', 'harassment', 'hate_speech', 'misinformation', 'inappropriate', 'other', name='report_reason', create_type=False), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('status', postgresql.ENUM('pending', 'reviewed', 'resolved', 'dismissed', name='report_status', create_type=False), default='pending'),
        sa.Column('reviewed_by_id', sa.Integer, sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('reviewed_at', sa.DateTime),
        sa.Column('resolution_notes', sa.Text),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow, index=True),
    )
    op.create_index('ix_content_reports_target', 'content_reports', ['target_type', 'target_id'])
    op.create_index('ix_content_reports_status', 'content_reports', ['status'])

    # ==========================================================================
    # User Blocks Table
    # ==========================================================================
    op.create_table(
        'user_blocks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('blocker_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('blocked_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('reason', sa.String(500)),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.UniqueConstraint('blocker_id', 'blocked_id', name='uq_user_blocks_pair'),
    )


def downgrade():
    op.drop_table('user_blocks')
    op.drop_table('content_reports')
    op.drop_table('post_bookmarks')
    op.drop_table('post_likes')
    op.drop_table('post_comments')
    op.drop_table('community_posts')
    
    op.execute("DROP TYPE IF EXISTS report_status")
    op.execute("DROP TYPE IF EXISTS report_reason")
    op.execute("DROP TYPE IF EXISTS report_target_type")
    op.execute("DROP TYPE IF EXISTS post_visibility")
    op.execute("DROP TYPE IF EXISTS post_type")
