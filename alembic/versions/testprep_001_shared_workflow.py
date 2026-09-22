"""Account-owned test preparation continuation state.

Revision ID: testprep_001
Revises: skillkey_001
"""
from alembic import op
import sqlalchemy as sa

revision = "testprep_001"
down_revision = "skillkey_001"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "test_profiles" in inspector.get_table_names():
        if "workflow_state" not in {c["name"] for c in inspector.get_columns("test_profiles")}:
            op.add_column("test_profiles", sa.Column("workflow_state", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if "test_profiles" in inspector.get_table_names():
        if "workflow_state" in {c["name"] for c in inspector.get_columns("test_profiles")}:
            op.drop_column("test_profiles", "workflow_state")
