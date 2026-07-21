"""Add clip_comments table and clips.comment_count.

Clients render a comment button and count on every reel, but no comments
API or storage existed for clips. Adds the denormalized-author comments
table (matching community post comments) and a comment_count column.

Revision ID: clips_sync_001
Revises: community_sync_001
Create Date: 2026-07-20
"""
import sqlalchemy as sa
from alembic import op

revision = "clips_sync_001"
down_revision = "community_sync_001"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _existing_columns(table: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    if _has_table("clips") and "comment_count" not in _existing_columns("clips"):
        op.add_column("clips", sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"))

    if not _has_table("clip_comments"):
        op.create_table(
            "clip_comments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clip_id", sa.Integer(), sa.ForeignKey("clips.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("author_name", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("author_avatar", sa.String(length=500), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    if _has_table("clip_comments"):
        op.drop_table("clip_comments")
    if _has_table("clips") and "comment_count" in _existing_columns("clips"):
        op.drop_column("clips", "comment_count")
