"""Add users columns that exist on the ORM model but never got a migration.

firebase_uid / auth_provider / learning_profile / user_context_summary were
added to lyo_app.auth.models.User without an accompanying migration, so any
database built purely from the alembic chain 500s on every ORM users query
(column users.firebase_uid does not exist).

Revision ID: users_sync_001
Revises: facf1e28b4e6, chat_002
Create Date: 2026-07-12
"""
import sqlalchemy as sa
from alembic import op

revision = "users_sync_001"
down_revision = ("facf1e28b4e6", "chat_002")
branch_labels = None
depends_on = None


def _existing_columns() -> set:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns("users")}


def upgrade() -> None:
    existing = _existing_columns()

    if "firebase_uid" not in existing:
        op.add_column("users", sa.Column("firebase_uid", sa.String(length=128), nullable=True))
        op.create_index("ix_users_firebase_uid", "users", ["firebase_uid"], unique=True)
    if "auth_provider" not in existing:
        op.add_column("users", sa.Column("auth_provider", sa.String(length=50), nullable=True))
    if "learning_profile" not in existing:
        op.add_column("users", sa.Column("learning_profile", sa.JSON(), nullable=True))
    if "user_context_summary" not in existing:
        op.add_column("users", sa.Column("user_context_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    existing = _existing_columns()
    if "user_context_summary" in existing:
        op.drop_column("users", "user_context_summary")
    if "learning_profile" in existing:
        op.drop_column("users", "learning_profile")
    if "auth_provider" in existing:
        op.drop_column("users", "auth_provider")
    if "firebase_uid" in existing:
        op.drop_index("ix_users_firebase_uid", table_name="users")
        op.drop_column("users", "firebase_uid")
