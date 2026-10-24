"""One-time password reset links.

A learner who forgot their password asks for a reset link by email. Each
link carries a random token; only its SHA-256 is stored here, so the table
alone cannot be used to reset anyone's password. A link works once, for an
hour.

Revision ID: password_reset_001
Revises: clips_moderation_002
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op

revision = "password_reset_001"
down_revision = "clips_moderation_002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_password_resets_token_hash"),
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])


def downgrade():
    op.drop_index("ix_password_resets_user_id", table_name="password_resets")
    op.drop_table("password_resets")
