"""Give guided classroom skills stable concept IDs and explicit dependencies.

Existing concepts, learner events, DKT estimates and review schedules stay in
place. A legacy slug can represent more than one original title, so automatic
backfilling would risk awarding evidence to a different skill. New plans use
real Concept IDs; older evidence remains readable under its original key.

Revision ID: classroom_identity_001
Revises: messaging_001
"""

from alembic import op
import sqlalchemy as sa

revision = "classroom_identity_001"
down_revision = "messaging_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("concepts", sa.Column("identity_key", sa.String(64), nullable=True))
    op.add_column("concepts", sa.Column("display_name", sa.String(200), nullable=True))
    op.create_index("uq_concept_subject_identity", "concepts", ["subject", "identity_key"], unique=True)
    op.create_table(
        "concept_prerequisites",
        sa.Column("concept_id", sa.String(36), sa.ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("prerequisite_id", sa.String(36), sa.ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True),
        sa.CheckConstraint("concept_id <> prerequisite_id", name="ck_concept_prerequisite_distinct"),
    )
    op.create_index("ix_concept_prerequisites_prerequisite", "concept_prerequisites", ["prerequisite_id"])


def downgrade() -> None:
    op.drop_index("ix_concept_prerequisites_prerequisite", table_name="concept_prerequisites")
    op.drop_table("concept_prerequisites")
    op.drop_index("uq_concept_subject_identity", table_name="concepts")
    op.drop_column("concepts", "display_name")
    op.drop_column("concepts", "identity_key")
