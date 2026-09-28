"""Cache validated classroom unit content by scoped skill, level and language.

Revision ID: classroom_packages_001
Revises: classroom_identity_001
"""

from alembic import op
import sqlalchemy as sa

revision = "classroom_packages_001"
down_revision = "classroom_identity_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classroom_unit_packages",
        sa.Column("cache_key", sa.String(64), primary_key=True),
        sa.Column("skill_id", sa.String(36), sa.ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_band", sa.Integer(), nullable=False),
        sa.Column("language_code", sa.String(35), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_classroom_unit_packages_skill_id", "classroom_unit_packages", ["skill_id"])
    op.create_table(
        "classroom_question_exposures",
        sa.Column("learner_hash", sa.String(64), primary_key=True),
        sa.Column("skill_id", sa.String(36), sa.ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("question_hash", sa.String(64), primary_key=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("classroom_question_exposures")
    op.drop_index("ix_classroom_unit_packages_skill_id", table_name="classroom_unit_packages")
    op.drop_table("classroom_unit_packages")
