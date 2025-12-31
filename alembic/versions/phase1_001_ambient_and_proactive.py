"""Phase 1: Add ambient presence and proactive intervention tables

Revision ID: phase1_001
Revises:
Create Date: 2025-01-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'phase1_001'
down_revision = None  # Update this to point to your latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Ambient Presence States table
    op.create_table(
        'ambient_presence_states',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),  # TenantMixin

        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.Column('current_page', sa.String(100), nullable=True),
        sa.Column('current_topic', sa.String(200), nullable=True),
        sa.Column('current_content_id', sa.String(100), nullable=True),
        sa.Column('time_on_page', sa.Float(), nullable=True),

        sa.Column('scroll_count', sa.Integer(), default=0, nullable=False),
        sa.Column('mouse_hesitations', sa.Integer(), default=0, nullable=False),

        sa.Column('inline_help_count_today', sa.Integer(), default=0, nullable=False),
        sa.Column('quick_access_count_today', sa.Integer(), default=0, nullable=False),

        sa.Column('context', postgresql.JSONB(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),

        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ambient_presence_states_user_id', 'ambient_presence_states', ['user_id'])
    op.create_index('ix_ambient_presence_states_org_id', 'ambient_presence_states', ['organization_id'])

    # Inline Help Logs table
    op.create_table(
        'inline_help_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),  # TenantMixin

        sa.Column('help_type', sa.String(50), nullable=False),
        sa.Column('help_text', sa.String(500), nullable=False),

        sa.Column('page', sa.String(100), nullable=False),
        sa.Column('topic', sa.String(200), nullable=True),
        sa.Column('content_id', sa.String(100), nullable=True),

        sa.Column('user_response', sa.String(20), nullable=True),
        sa.Column('response_at', sa.DateTime(timezone=True), nullable=True),

        sa.Column('shown_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_inline_help_logs_user_id', 'inline_help_logs', ['user_id'])

    # Intervention Logs table
    op.create_table(
        'intervention_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),  # TenantMixin

        sa.Column('intervention_type', sa.String(100), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),

        sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),

        sa.Column('user_response', sa.String(50), nullable=True),
        sa.Column('response_at', sa.DateTime(timezone=True), nullable=True),

        sa.Column('context', postgresql.JSONB(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_intervention_logs_user_id', 'intervention_logs', ['user_id'])
    op.create_index('ix_intervention_logs_type', 'intervention_logs', ['intervention_type'])
    op.create_index('ix_intervention_logs_triggered_at', 'intervention_logs', ['triggered_at'])

    # User Notification Preferences table
    op.create_table(
        'user_notification_preferences',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),  # TenantMixin

        sa.Column('dnd_enabled', sa.Boolean(), default=False, nullable=False),

        sa.Column('quiet_hours_start', sa.Time(), nullable=True),
        sa.Column('quiet_hours_end', sa.Time(), nullable=True),

        sa.Column('max_notifications_per_day', sa.Integer(), default=5, nullable=False),

        sa.Column('enabled_intervention_types', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('disabled_intervention_types', postgresql.ARRAY(sa.String()), nullable=True),

        sa.Column('preferred_study_times', postgresql.JSONB(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),

        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_user_notification_preferences_user_id')
    )
    op.create_index('ix_user_notification_preferences_user_id', 'user_notification_preferences', ['user_id'])


def downgrade():
    op.drop_index('ix_user_notification_preferences_user_id', table_name='user_notification_preferences')
    op.drop_table('user_notification_preferences')

    op.drop_index('ix_intervention_logs_triggered_at', table_name='intervention_logs')
    op.drop_index('ix_intervention_logs_type', table_name='intervention_logs')
    op.drop_index('ix_intervention_logs_user_id', table_name='intervention_logs')
    op.drop_table('intervention_logs')

    op.drop_index('ix_inline_help_logs_user_id', table_name='inline_help_logs')
    op.drop_table('inline_help_logs')

    op.drop_index('ix_ambient_presence_states_org_id', table_name='ambient_presence_states')
    op.drop_index('ix_ambient_presence_states_user_id', table_name='ambient_presence_states')
    op.drop_table('ambient_presence_states')
