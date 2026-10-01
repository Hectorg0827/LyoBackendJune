"""The time of day an exam is sat.

Nullable on purpose. A learner sitting one exam on a date never needs to give
a time — the date alone orders their revision. The time earns its place only
when two exams share a date and something has to decide which is first, so it
is asked for then and left unset otherwise.

Revision ID: testprep_003
Revises: testprep_002
"""
from alembic import op
import sqlalchemy as sa

revision = "testprep_003"
down_revision = "testprep_002"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "test_profiles" in inspector.get_table_names():
        if "test_time" not in {c["name"] for c in inspector.get_columns("test_profiles")}:
            op.add_column("test_profiles", sa.Column("test_time", sa.Time(), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if "test_profiles" in inspector.get_table_names():
        if "test_time" in {c["name"] for c in inspector.get_columns("test_profiles")}:
            op.drop_column("test_profiles", "test_time")
