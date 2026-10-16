"""Expand stored refresh JWTs for the auth_version claim.

Revision ID: auth_refresh_text_001
Revises: auth_epoch_001
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = "auth_refresh_text_001"
down_revision = "auth_epoch_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("refresh_tokens"):
        return
    columns = {col["name"]: col for col in inspector.get_columns("refresh_tokens")}
    if "token" not in columns:
        return
    # PostgreSQL VARCHAR(255) silently becomes incompatible once JWTs carry
    # auth_version. TEXT preserves existing signed tokens and their index.
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE refresh_tokens ALTER COLUMN token TYPE TEXT")


def downgrade() -> None:
    # Never truncate active signed credentials or reintroduce login failures.
    raise RuntimeError("Unsafe to narrow stored refresh JWTs; use forward-only migration")
