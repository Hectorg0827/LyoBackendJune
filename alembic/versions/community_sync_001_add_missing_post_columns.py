"""Add community_posts / post_comments columns the service layer requires.

The community service writes denormalized author info (author_name,
author_avatar, author_level) and soft-deletes via is_deleted, but those
columns never got a migration — every posts/comments query 500s on a
database built from the alembic chain (and CommunityPost(...) raises for
unknown kwargs on create).

Revision ID: community_sync_001
Revises: users_sync_001
Create Date: 2026-07-20
"""
import sqlalchemy as sa
from alembic import op

revision = "community_sync_001"
down_revision = "users_sync_001"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    posts = _existing_columns("community_posts")
    if "author_name" not in posts:
        op.add_column("community_posts", sa.Column("author_name", sa.String(length=150), nullable=False, server_default=""))
    if "author_avatar" not in posts:
        op.add_column("community_posts", sa.Column("author_avatar", sa.String(length=500), nullable=True))
    if "author_level" not in posts:
        op.add_column("community_posts", sa.Column("author_level", sa.Integer(), nullable=False, server_default="1"))
    if "is_deleted" not in posts:
        op.add_column("community_posts", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))

    comments = _existing_columns("post_comments")
    if "author_name" not in comments:
        op.add_column("post_comments", sa.Column("author_name", sa.String(length=150), nullable=False, server_default=""))
    if "author_avatar" not in comments:
        op.add_column("post_comments", sa.Column("author_avatar", sa.String(length=500), nullable=True))
    if "is_deleted" not in comments:
        op.add_column("post_comments", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for table, cols in (
        ("post_comments", ("is_deleted", "author_avatar", "author_name")),
        ("community_posts", ("is_deleted", "author_level", "author_avatar", "author_name")),
    ):
        existing = _existing_columns(table)
        for col in cols:
            if col in existing:
                op.drop_column(table, col)
