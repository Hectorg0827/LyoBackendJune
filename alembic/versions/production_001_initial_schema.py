"""
Production database migration - Create all tables for Lyo backend.
This includes all tables specified in the backend completion prompt.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'production_001_initial_schema'
down_revision = '20250728_add_social'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all production tables."""
    
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('username', sa.String(100), nullable=True, unique=True),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('is_verified', sa.Boolean, nullable=False, default=False),
        sa.Column('is_superuser', sa.Boolean, nullable=False, default=False),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('bio', sa.Text, nullable=True),
        sa.Column('timezone', sa.String(50), nullable=True),
        sa.Column('locale', sa.String(10), nullable=False, default='en'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_username', 'users', ['username'])
    
    # Courses table
    op.create_table(
        'courses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String(50), nullable=False, default='draft'),
        sa.Column('topic', sa.String(200), nullable=True),
        sa.Column('interests', sa.JSON, nullable=True),
        sa.Column('level', sa.String(50), nullable=True),
        sa.Column('locale', sa.String(10), nullable=False, default='en'),
        sa.Column('estimated_duration', sa.Integer, nullable=True),
        sa.Column('generation_prompt', sa.Text, nullable=True),
        sa.Column('generation_metadata', sa.JSON, nullable=True),
        sa.Column('total_items', sa.Integer, nullable=False, default=0),
        sa.Column('completed_items', sa.Integer, nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_courses_user_id', 'courses', ['user_id'])
    op.create_index('ix_courses_status', 'courses', ['status'])
    op.create_index('ix_courses_topic', 'courses', ['topic'])
    op.create_index('idx_courses_user_status', 'courses', ['user_id', 'status'])
    op.create_index('idx_courses_created', 'courses', ['created_at'])
    
    # Tasks table for async operations
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('idempotency_key', sa.String(255), nullable=True, unique=True),
        sa.Column('state', sa.String(20), nullable=False, default='PENDING'),
        sa.Column('progress_pct', sa.Integer, nullable=False, default=0),
        sa.Column('message', sa.Text, nullable=True),
        sa.Column('provisional_course_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('result_course_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('task_type', sa.String(50), nullable=False, default='course_generation'),
        sa.Column('payload', sa.JSON, nullable=True),
        sa.Column('error_details', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['result_course_id'], ['courses.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_tasks_user_id', 'tasks', ['user_id'])
    op.create_index('ix_tasks_state', 'tasks', ['state'])
    op.create_index('ix_tasks_idempotency_key', 'tasks', ['idempotency_key'])
    op.create_index('idx_tasks_user_state', 'tasks', ['user_id', 'state'])
    op.create_index('idx_tasks_created', 'tasks', ['created_at'])
    
    # Lessons table
    op.create_table(
        'lessons',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('order_index', sa.Integer, nullable=False),
        sa.Column('objectives', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_lessons_course_id', 'lessons', ['course_id'])
    op.create_index('idx_lessons_course_order', 'lessons', ['course_id', 'order_index'])
    op.create_unique_constraint('uq_lesson_order', 'lessons', ['course_id', 'order_index'])
    
    # Course items table (lessons, videos, etc.)
    op.create_table(
        'course_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lesson_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text, nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('source_url', sa.Text, nullable=True),
        sa.Column('thumbnail_url', sa.String(500), nullable=True),
        sa.Column('duration', sa.Integer, nullable=True),
        sa.Column('difficulty_level', sa.String(20), nullable=True),
        sa.Column('tags', sa.JSON, nullable=True),
        sa.Column('order_index', sa.Integer, nullable=False),
        sa.Column('view_count', sa.Integer, nullable=False, default=0),
        sa.Column('completion_rate', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_course_items_course_id', 'course_items', ['course_id'])
    op.create_index('ix_course_items_lesson_id', 'course_items', ['lesson_id'])
    op.create_index('ix_course_items_type', 'course_items', ['type'])
    op.create_index('idx_courseitems_course_order', 'course_items', ['course_id', 'order_index'])
    op.create_index('idx_courseitems_lesson_order', 'course_items', ['lesson_id', 'order_index'])
    op.create_unique_constraint('uq_courseitem_order', 'course_items', ['course_id', 'order_index'])
    
    # User profiles for gamification
    op.create_table(
        'user_profiles',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('xp', sa.Integer, nullable=False, default=0),
        sa.Column('level', sa.Integer, nullable=False, default=1),
        sa.Column('current_streak', sa.Integer, nullable=False, default=0),
        sa.Column('longest_streak', sa.Integer, nullable=False, default=0),
        sa.Column('last_activity_date', sa.Date, nullable=True),
        sa.Column('courses_completed', sa.Integer, nullable=False, default=0),
        sa.Column('lessons_completed', sa.Integer, nullable=False, default=0),
        sa.Column('total_study_time', sa.Integer, nullable=False, default=0),
        sa.Column('daily_goal', sa.Integer, nullable=False, default=30),
        sa.Column('notification_preferences', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    
    # Badges
    op.create_table(
        'badges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('icon_url', sa.String(500), nullable=True),
        sa.Column('criteria', sa.JSON, nullable=True),
        sa.Column('xp_reward', sa.Integer, nullable=False, default=0),
        sa.Column('rarity', sa.String(20), nullable=False, default='common'),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_badges_category', 'badges', ['category'])
    
    # User badges (many-to-many)
    op.create_table(
        'user_badges',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('badge_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('earned_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('progress_data', sa.JSON, nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['badge_id'], ['badges.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'badge_id'),
    )
    
    # Push devices
    op.create_table(
        'push_devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_token', sa.String(255), nullable=False, unique=True),
        sa.Column('platform', sa.String(20), nullable=False),
        sa.Column('device_name', sa.String(100), nullable=True),
        sa.Column('app_version', sa.String(20), nullable=True),
        sa.Column('active', sa.Boolean, nullable=False, default=True),
        sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_push_devices_user_id', 'push_devices', ['user_id'])
    op.create_index('ix_push_devices_device_token', 'push_devices', ['device_token'])
    op.create_index('ix_push_devices_platform', 'push_devices', ['platform'])
    op.create_index('idx_push_devices_user_active', 'push_devices', ['user_id', 'active'])
    
    # Feed items
    op.create_table(
        'feed_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text, nullable=True),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('image_url', sa.String(500), nullable=True),
        sa.Column('link_url', sa.String(500), nullable=True),
        sa.Column('like_count', sa.Integer, nullable=False, default=0),
        sa.Column('comment_count', sa.Integer, nullable=False, default=0),
        sa.Column('share_count', sa.Integer, nullable=False, default=0),
        sa.Column('is_public', sa.Boolean, nullable=False, default=True),
        sa.Column('is_featured', sa.Boolean, nullable=False, default=False),
        sa.Column('priority_score', sa.DECIMAL(10, 6), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_feed_items_user_id', 'feed_items', ['user_id'])
    op.create_index('ix_feed_items_type', 'feed_items', ['type'])
    op.create_index('idx_feed_items_type_created', 'feed_items', ['type', 'created_at'])
    op.create_index('idx_feed_items_public_priority', 'feed_items', ['is_public', 'priority_score'])
    op.create_index('idx_feed_items_user_created', 'feed_items', ['user_id', 'created_at'])
    op.create_index('idx_feed_items_featured_created', 'feed_items', ['is_featured', 'created_at'])


def downgrade() -> None:
    """Drop all production tables."""
    op.drop_table('feed_items')
    op.drop_table('push_devices')
    op.drop_table('user_badges')
    op.drop_table('badges')
    op.drop_table('user_profiles')
    op.drop_table('course_items')
    op.drop_table('lessons')
    op.drop_table('tasks')
    op.drop_table('courses')
    op.drop_table('users')
