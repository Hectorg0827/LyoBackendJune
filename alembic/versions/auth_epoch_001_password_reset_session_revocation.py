"""Ensure credential epochs exist before any password-reset or JWT validation.

Revision ID: auth_epoch_001
Revises: coach_001
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "auth_epoch_001"
down_revision = "coach_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return
    if "auth_version" not in {col["name"] for col in inspector.get_columns("users")}:
        op.add_column(
            "users",
            sa.Column("auth_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    # Deliberately do not remove a revocation epoch: that could resurrect old JWTs.
    raise RuntimeError("Credential epoch downgrade is unsafe; restore via a forward migration")
