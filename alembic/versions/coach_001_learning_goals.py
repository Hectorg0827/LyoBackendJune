"""Lyo Coach goal orchestration tables.

Revision ID: coach_001
Revises: classroom_packages_001
Create Date: 2026-10-04

The coach stores goals and disposable context caches only.  Learning evidence
continues to live in learning_events/mastery_states.
"""

from alembic import op
import sqlalchemy as sa

revision = "coach_001"
down_revision = "classroom_packages_001"
branch_labels = None
depends_on = None


def _has(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has("learning_goals"):
        op.create_table(
            "learning_goals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("goal_type", sa.String(32), nullable=False),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("subject", sa.String(120), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("deadline", sa.DateTime(), nullable=True),
            sa.Column("desired_outcome", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("constraints", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("source_surface", sa.String(32), nullable=True),
            sa.Column("source_ref_type", sa.String(40), nullable=True),
            sa.Column("source_ref_id", sa.String(80), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "source_ref_type", "source_ref_id", name="uq_learning_goal_source"),
        )
        op.create_index("ix_learning_goals_user_id", "learning_goals", ["user_id"])
        op.create_index("ix_learning_goals_goal_type", "learning_goals", ["goal_type"])
        op.create_index("ix_learning_goals_subject", "learning_goals", ["subject"])
        op.create_index("ix_learning_goals_status", "learning_goals", ["status"])
        op.create_index("ix_learning_goals_deadline", "learning_goals", ["deadline"])
        op.create_index(
            "ix_learning_goals_user_status_deadline",
            "learning_goals",
            ["user_id", "status", "deadline"],
        )

    if not _has("goal_skills"):
        op.create_table(
            "goal_skills",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("goal_id", sa.String(36), sa.ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("concept_id", sa.String(80), nullable=False),
            sa.Column("display_name", sa.String(240), nullable=False),
            sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
            sa.Column("required_rung", sa.String(32), nullable=False, server_default="transfer"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("parent_concept_id", sa.String(80), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("goal_id", "concept_id", name="uq_goal_skill_concept"),
        )
        op.create_index("ix_goal_skills_goal_id", "goal_skills", ["goal_id"])
        op.create_index("ix_goal_skills_user_id", "goal_skills", ["user_id"])
        op.create_index("ix_goal_skills_concept_id", "goal_skills", ["concept_id"])
        op.create_index("ix_goal_skills_user_goal", "goal_skills", ["user_id", "goal_id"])

    if not _has("coach_snapshots"):
        op.create_table(
            "coach_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("goal_id", sa.String(36), sa.ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_event_id", sa.Integer(), nullable=True),
            sa.Column("goal_updated_at", sa.DateTime(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("generated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "goal_id", name="uq_coach_snapshot_user_goal"),
        )
        op.create_index("ix_coach_snapshots_user_id", "coach_snapshots", ["user_id"])
        op.create_index("ix_coach_snapshots_goal_id", "coach_snapshots", ["goal_id"])


def downgrade() -> None:
    for table in ("coach_snapshots", "goal_skills", "learning_goals"):
        if _has(table):
            op.drop_table(table)
