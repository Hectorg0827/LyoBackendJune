"""Phase 2: Add predictive intelligence tables

Revision ID: phase2_001
Revises: phase1_001
Create Date: 2025-01-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'phase2_001'
down_revision = 'phase1_001'
branch_labels = None
depends_on = None


def upgrade():
    # Struggle Predictions table
    op.create_table(
        'struggle_predictions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),  # TenantMixin

        sa.Column('content_id', sa.String(100), nullable=False),
        sa.Column('content_type', sa.String(50), nullable=False),

        sa.Column('struggle_probability', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),

        # Features used for prediction
        sa.Column('prereq_mastery', sa.Float(), nullable=True),
        sa.Column('similar_performance', sa.Float(), nullable=True),
        sa.Column('content_difficulty', sa.Float(), nullable=True),
        sa.Column('days_since_review', sa.Integer(), nullable=True),
        sa.Column('cognitive_load', sa.Float(), nullable=True),
        sa.Column('sentiment_trend', sa.Float(), nullable=True),

        sa.Column('prediction_features', postgresql.JSONB(), nullable=True),

        # Actual outcome (for model improvement)
        sa.Column('actual_struggled', sa.Boolean(), nullable=True),
        sa.Column('actual_outcome_at', sa.DateTime(timezone=True), nullable=True),

        # Intervention tracking
        sa.Column('intervention_offered', sa.Boolean(), default=False, nullable=False),
        sa.Column('intervention_accepted', sa.Boolean(), nullable=True),

        sa.Column('predicted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_struggle_predictions_user_id', 'struggle_predictions', ['user_id'])
    op.create_index('ix_struggle_predictions_content_id', 'struggle_predictions', ['content_id'])
    op.create_index('ix_struggle_predictions_predicted_at', 'struggle_predictions', ['predicted_at'])

    # Dropout Risk Scores table
    op.create_table(
        'dropout_risk_scores',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),  # TenantMixin

        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('risk_level', sa.String(20), nullable=False),

        sa.Column('risk_factors', postgresql.ARRAY(sa.String()), nullable=False),

        # Metrics contributing to score
        sa.Column('session_frequency_trend', sa.Float(), nullable=True),
        sa.Column('avg_days_between_sessions', sa.Float(), nullable=True),
        sa.Column('sentiment_trend_7d', sa.Float(), nullable=True),
        sa.Column('days_since_last_completion', sa.Integer(), nullable=True),
        sa.Column('performance_trend', sa.Float(), nullable=True),
        sa.Column('longest_streak', sa.Integer(), nullable=True),
        sa.Column('current_streak', sa.Integer(), nullable=True),

        # Re-engagement strategy
        sa.Column('reengagement_strategy', postgresql.JSONB(), nullable=True),
        sa.Column('strategy_executed', sa.Boolean(), default=False, nullable=False),
        sa.Column('strategy_executed_at', sa.DateTime(timezone=True), nullable=True),

        # Outcome tracking
        sa.Column('user_returned', sa.Boolean(), nullable=True),
        sa.Column('returned_at', sa.DateTime(timezone=True), nullable=True),

        sa.Column('calculated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),

        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_dropout_risk_scores_user_id')
    )
    op.create_index('ix_dropout_risk_scores_user_id', 'dropout_risk_scores', ['user_id'])
    op.create_index('ix_dropout_risk_scores_calculated_at', 'dropout_risk_scores', ['calculated_at'])

    # User Timing Profiles table
    op.create_table(
        'user_timing_profiles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),  # TenantMixin

        # Peak learning times
        sa.Column('peak_hours', postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column('optimal_study_time', sa.Time(), nullable=True),

        # Day preferences
        sa.Column('best_days', postgresql.ARRAY(sa.String()), nullable=True),

        # Session patterns
        sa.Column('avg_session_duration_minutes', sa.Float(), nullable=True),
        sa.Column('preferred_session_length', sa.Integer(), nullable=True),

        # Performance data
        sa.Column('performance_by_hour', postgresql.JSONB(), nullable=True),

        # Activity patterns
        sa.Column('most_active_hour', sa.Integer(), nullable=True),
        sa.Column('least_active_hour', sa.Integer(), nullable=True),

        # Study day patterns
        sa.Column('typical_study_days', postgresql.ARRAY(sa.Integer()), nullable=True),

        # Confidence metrics
        sa.Column('sessions_analyzed', sa.Integer(), default=0, nullable=False),
        sa.Column('confidence', sa.Float(), default=0.0, nullable=False),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),

        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_user_timing_profiles_user_id')
    )
    op.create_index('ix_user_timing_profiles_user_id', 'user_timing_profiles', ['user_id'])

    # Learning Plateaus table
    op.create_table(
        'learning_plateaus',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),  # TenantMixin

        sa.Column('topic', sa.String(200), nullable=False),
        sa.Column('skill_id', sa.String(100), nullable=False),

        # Plateau metrics
        sa.Column('days_on_topic', sa.Integer(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('mastery_level', sa.Float(), nullable=False),
        sa.Column('mastery_improvement', sa.Float(), nullable=False),

        # Status
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('resolved', sa.Boolean(), default=False, nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),

        # Intervention
        sa.Column('intervention_suggested', sa.Text(), nullable=True),
        sa.Column('intervention_taken', sa.Boolean(), default=False, nullable=False),

        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),

        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_learning_plateaus_user_id', 'learning_plateaus', ['user_id'])
    op.create_index('ix_learning_plateaus_detected_at', 'learning_plateaus', ['detected_at'])

    # Skill Regressions table
    op.create_table(
        'skill_regressions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),  # TenantMixin

        sa.Column('skill_id', sa.String(100), nullable=False),
        sa.Column('skill_name', sa.String(200), nullable=False),

        # Regression metrics
        sa.Column('peak_mastery', sa.Float(), nullable=False),
        sa.Column('current_mastery', sa.Float(), nullable=False),
        sa.Column('regression_amount', sa.Float(), nullable=False),

        # Time since last practice
        sa.Column('days_since_practice', sa.Integer(), nullable=False),
        sa.Column('last_practiced_at', sa.DateTime(timezone=True), nullable=False),

        # Forgetting curve prediction
        sa.Column('predicted_mastery_in_week', sa.Float(), nullable=True),
        sa.Column('urgency', sa.String(20), nullable=False),

        # Intervention tracking
        sa.Column('reminder_sent', sa.Boolean(), default=False, nullable=False),
        sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_reviewed', sa.Boolean(), default=False, nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),

        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_skill_regressions_user_id', 'skill_regressions', ['user_id'])
    op.create_index('ix_skill_regressions_detected_at', 'skill_regressions', ['detected_at'])


def downgrade():
    op.drop_index('ix_skill_regressions_detected_at', table_name='skill_regressions')
    op.drop_index('ix_skill_regressions_user_id', table_name='skill_regressions')
    op.drop_table('skill_regressions')

    op.drop_index('ix_learning_plateaus_detected_at', table_name='learning_plateaus')
    op.drop_index('ix_learning_plateaus_user_id', table_name='learning_plateaus')
    op.drop_table('learning_plateaus')

    op.drop_index('ix_user_timing_profiles_user_id', table_name='user_timing_profiles')
    op.drop_table('user_timing_profiles')

    op.drop_index('ix_dropout_risk_scores_calculated_at', table_name='dropout_risk_scores')
    op.drop_index('ix_dropout_risk_scores_user_id', table_name='dropout_risk_scores')
    op.drop_table('dropout_risk_scores')

    op.drop_index('ix_struggle_predictions_predicted_at', table_name='struggle_predictions')
    op.drop_index('ix_struggle_predictions_content_id', table_name='struggle_predictions')
    op.drop_index('ix_struggle_predictions_user_id', table_name='struggle_predictions')
    op.drop_table('struggle_predictions')
