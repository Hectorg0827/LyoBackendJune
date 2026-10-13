"""Add server-owned learning journeys and typed handoff history.

Revision ID: coach_002
Revises: coach_001
Create Date: 2026-10-12

Additive to Coach's canonical goals: this is navigation continuity only, not
a second learner-memory or evidence-scoring system.
"""
from alembic import op
import sqlalchemy as sa

revision = "coach_002"
down_revision = "coach_001"
branch_labels = None
depends_on = None


def _has(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has("learning_journeys"):
        op.create_table(
            "learning_journeys",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("goal_id", sa.String(36), sa.ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=False),
            sa.Column("start_request_id", sa.String(80), nullable=False),
            sa.Column("origin_surface", sa.String(24), nullable=False),
            sa.Column("origin_ref", sa.String(160), nullable=True),
            sa.Column("active_surface", sa.String(24), nullable=False),
            sa.Column("active_ref", sa.String(160), nullable=True),
            sa.Column("initial_context_json", sa.JSON(), nullable=False),
            sa.Column("context_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "start_request_id", name="uq_learning_journey_start"),
        )
        op.create_index("ix_learning_journeys_user_id", "learning_journeys", ["user_id"])
        op.create_index("ix_learning_journeys_goal_id", "learning_journeys", ["goal_id"])
        op.create_index("ix_learning_journeys_user_goal", "learning_journeys", ["user_id", "goal_id"])

    if not _has("journey_handoffs"):
        op.create_table(
            "journey_handoffs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("journey_id", sa.String(36), sa.ForeignKey("learning_journeys.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("request_id", sa.String(80), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("from_surface", sa.String(24), nullable=False),
            sa.Column("from_ref", sa.String(160), nullable=True),
            sa.Column("to_surface", sa.String(24), nullable=False),
            sa.Column("to_ref", sa.String(160), nullable=True),
            sa.Column("requested_context", sa.JSON(), nullable=False),
            sa.Column("context_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("journey_id", "request_id", name="uq_journey_handoff_request"),
            sa.UniqueConstraint("journey_id", "revision", name="uq_journey_handoff_revision"),
        )
        op.create_index("ix_journey_handoffs_journey_id", "journey_handoffs", ["journey_id"])
        op.create_index("ix_journey_handoffs_user_id", "journey_handoffs", ["user_id"])


def downgrade() -> None:
    if _has("journey_handoffs"):
        op.drop_table("journey_handoffs")
    if _has("learning_journeys"):
        op.drop_table("learning_journeys")
