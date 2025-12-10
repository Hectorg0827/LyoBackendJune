"""Add AI Classroom graph learning models

Revision ID: ai_classroom_001
Revises: production_001_initial_schema
Create Date: 2024-12-07

Creates all tables for the graph-based learning engine:
- graph_courses: Course containers (like Netflix Series)
- learning_nodes: Individual learning content units
- learning_edges: Connections between nodes with conditions
- concepts: Subject matter taxonomy
- misconceptions: Common errors mapped to concepts
- mastery_states: Per-user learning progress
- review_schedules: Spaced repetition tracking
- interaction_attempts: User response tracking
- course_progress: User's position in course graph
- celebration_configs: Success animation triggers
- ad_placement_configs: Monetization during latency
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'ai_classroom_001'
down_revision = 'production_001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create AI Classroom tables."""
    
    # Graph Courses (main container)
    op.create_table(
        'graph_courses',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('subject', sa.String(100), nullable=False, index=True),
        sa.Column('grade_band', sa.String(50), nullable=True),
        sa.Column('visual_theme', sa.String(50), default='modern'),
        sa.Column('audio_mood', sa.String(50), default='calm'),
        sa.Column('entry_node_id', sa.String(36), nullable=True),
        sa.Column('estimated_minutes', sa.Integer, default=30),
        sa.Column('difficulty', sa.String(50), default='intermediate'),
        sa.Column('learning_objectives', sa.JSON, nullable=True),
        sa.Column('prerequisites', sa.JSON, nullable=True),
        sa.Column('source_intent', sa.Text, nullable=True),
        sa.Column('source_conversation_id', sa.String(36), nullable=True),
        sa.Column('is_published', sa.Boolean, default=False),
        sa.Column('is_template', sa.Boolean, default=False),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_graph_courses_subject_grade', 'graph_courses', ['subject', 'grade_band'])
    
    # Concepts (taxonomy)
    op.create_table(
        'concepts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('subject', sa.String(100), nullable=False, index=True),
        sa.Column('grade_band', sa.String(50), nullable=True),
        sa.Column('parent_concept_id', sa.String(36), sa.ForeignKey('concepts.id'), nullable=True),
        sa.Column('priority', sa.Integer, default=5),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_concepts_subject', 'concepts', ['subject', 'grade_band'])
    op.create_unique_constraint('uq_concept_name_subject', 'concepts', ['name', 'subject'])
    
    # Learning Nodes (scenes)
    op.create_table(
        'learning_nodes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('course_id', sa.String(36), sa.ForeignKey('graph_courses.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('node_type', sa.String(50), nullable=False),
        sa.Column('content', sa.JSON, nullable=False, default=dict),
        sa.Column('objective_id', sa.String(36), nullable=True, index=True),
        sa.Column('concept_id', sa.String(36), sa.ForeignKey('concepts.id'), nullable=True),
        sa.Column('prerequisites', sa.JSON, nullable=True, default=list),
        sa.Column('estimated_seconds', sa.Integer, default=15),
        sa.Column('asset_tier', sa.String(20), default='abstract'),
        sa.Column('generated_asset_url', sa.String(500), nullable=True),
        sa.Column('generated_audio_url', sa.String(500), nullable=True),
        sa.Column('interaction_type', sa.String(50), nullable=True),
        sa.Column('skill_type', sa.String(50), nullable=True),
        sa.Column('misconception_tags', sa.JSON, nullable=True),
        sa.Column('remediation_budget', sa.Integer, default=2),
        sa.Column('fallback_node_id', sa.String(36), nullable=True),
        sa.Column('sequence_order', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_learning_nodes_course_sequence', 'learning_nodes', ['course_id', 'sequence_order'])
    
    # Learning Edges (branches)
    op.create_table(
        'learning_edges',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('course_id', sa.String(36), sa.ForeignKey('graph_courses.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('from_node_id', sa.String(36), sa.ForeignKey('learning_nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('to_node_id', sa.String(36), sa.ForeignKey('learning_nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('condition', sa.String(50), default='always'),
        sa.Column('mastery_threshold', sa.Float, nullable=True),
        sa.Column('weight', sa.Float, default=1.0),
    )
    op.create_index('ix_learning_edges_from', 'learning_edges', ['from_node_id'])
    op.create_index('ix_learning_edges_to', 'learning_edges', ['to_node_id'])
    op.create_unique_constraint('uq_edge_connection', 'learning_edges', ['from_node_id', 'to_node_id', 'condition'])
    
    # Misconceptions
    op.create_table(
        'misconceptions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('concept_id', sa.String(36), sa.ForeignKey('concepts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('label', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('example_wrong_beliefs', sa.JSON, nullable=True),
        sa.Column('remediation_strategy', sa.Text, nullable=True),
        sa.Column('suggested_analogy', sa.Text, nullable=True),
        sa.Column('occurrence_count', sa.Integer, default=0),
    )
    
    # Mastery States
    op.create_table(
        'mastery_states',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('concept_id', sa.String(36), sa.ForeignKey('concepts.id'), nullable=True),
        sa.Column('objective_id', sa.String(36), nullable=True),
        sa.Column('mastery_score', sa.Float, default=0.0),
        sa.Column('confidence', sa.Float, default=0.5),
        sa.Column('attempts', sa.Integer, default=0),
        sa.Column('correct_count', sa.Integer, default=0),
        sa.Column('incorrect_count', sa.Integer, default=0),
        sa.Column('error_pattern', sa.String(200), nullable=True),
        sa.Column('misconception_tags', sa.JSON, nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_correct', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trend', sa.String(20), default='stable'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_mastery_user_concept', 'mastery_states', ['user_id', 'concept_id'])
    op.create_index('ix_mastery_user_objective', 'mastery_states', ['user_id', 'objective_id'])
    op.create_unique_constraint('uq_user_concept_mastery', 'mastery_states', ['user_id', 'concept_id'])
    
    # Review Schedules (Spaced Repetition)
    op.create_table(
        'review_schedules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('node_id', sa.String(36), sa.ForeignKey('learning_nodes.id', ondelete='CASCADE'), nullable=True),
        sa.Column('concept_id', sa.String(36), sa.ForeignKey('concepts.id'), nullable=True),
        sa.Column('easiness_factor', sa.Float, default=2.5),
        sa.Column('interval_days', sa.Integer, default=1),
        sa.Column('repetition_number', sa.Integer, default=0),
        sa.Column('next_review_at', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('last_reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_quality', sa.Integer, default=3),
        sa.Column('streak', sa.Integer, default=0),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_review_user_next', 'review_schedules', ['user_id', 'next_review_at'])
    op.create_index('ix_review_active', 'review_schedules', ['user_id', 'is_active'])
    
    # Interaction Attempts
    op.create_table(
        'interaction_attempts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('node_id', sa.String(36), sa.ForeignKey('learning_nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_answer', sa.Text, nullable=False),
        sa.Column('is_correct', sa.Boolean, nullable=False),
        sa.Column('time_taken_seconds', sa.Float, nullable=True),
        sa.Column('attempt_number', sa.Integer, default=1),
        sa.Column('remediation_shown', sa.Boolean, default=False),
        sa.Column('detected_misconception_id', sa.String(36), sa.ForeignKey('misconceptions.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_attempts_user_node', 'interaction_attempts', ['user_id', 'node_id'])
    op.create_index('ix_attempts_created', 'interaction_attempts', ['created_at'])
    
    # Course Progress
    op.create_table(
        'course_progress',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('course_id', sa.String(36), sa.ForeignKey('graph_courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('current_node_id', sa.String(36), nullable=True),
        sa.Column('completed_node_ids', sa.JSON, default=list),
        sa.Column('total_time_seconds', sa.Integer, default=0),
        sa.Column('interactions_completed', sa.Integer, default=0),
        sa.Column('interactions_passed', sa.Integer, default=0),
        sa.Column('remediations_triggered', sa.Integer, default=0),
        sa.Column('status', sa.String(50), default='in_progress'),
        sa.Column('completion_percentage', sa.Float, default=0.0),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_active_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_progress_user_course', 'course_progress', ['user_id', 'course_id'])
    op.create_unique_constraint('uq_user_course_progress', 'course_progress', ['user_id', 'course_id'])
    
    # Celebration Configs
    op.create_table(
        'celebration_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('trigger_type', sa.String(50), nullable=False),
        sa.Column('min_streak', sa.Integer, default=1),
        sa.Column('avatar_url', sa.String(500), nullable=False),
        sa.Column('animation_type', sa.String(50), default='confetti'),
        sa.Column('sound_effect', sa.String(100), nullable=True),
        sa.Column('message_template', sa.String(500), default='Great job! 🎉'),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('weight', sa.Float, default=1.0),
    )
    
    # Ad Placement Configs
    op.create_table(
        'ad_placement_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('placement_type', sa.String(50), nullable=False),
        sa.Column('min_latency_ms', sa.Integer, default=2000),
        sa.Column('max_frequency_per_session', sa.Integer, default=3),
        sa.Column('cooldown_seconds', sa.Integer, default=300),
        sa.Column('ad_unit_id', sa.String(200), nullable=False),
        sa.Column('ad_format', sa.String(50), default='interstitial'),
        sa.Column('target_subjects', sa.JSON, nullable=True),
        sa.Column('exclude_premium', sa.Boolean, default=True),
        sa.Column('is_active', sa.Boolean, default=True),
    )


def downgrade() -> None:
    """Drop all AI Classroom tables."""
    op.drop_table('ad_placement_configs')
    op.drop_table('celebration_configs')
    op.drop_table('course_progress')
    op.drop_table('interaction_attempts')
    op.drop_table('review_schedules')
    op.drop_table('mastery_states')
    op.drop_table('misconceptions')
    op.drop_table('learning_edges')
    op.drop_table('learning_nodes')
    op.drop_table('concepts')
    op.drop_table('graph_courses')
