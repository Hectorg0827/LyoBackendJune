"""Align the Community social-feed tables with the API's live post contract.

The original feed migration used PostgreSQL array/native-enum columns while
the ORM expected JSON, lower-case flexible post types, and moderation/likes
columns absent from the schema. Consequently creating or reading a post raised
HTTP 500 on a database created by `alembic upgrade head`.

This migration is additive or lossless: it preserves existing post text,
media, tags, historic post types, likes, comments and visibility.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "community_posts_002"
down_revision = "refresh_tokens_001"
branch_labels = None
depends_on = None


def _columns(table: str) -> dict:
    return {col["name"]: col for col in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Community feed schema reconciliation requires PostgreSQL")

    posts = _columns("community_posts")
    for name in ("media_urls", "tags"):
        if isinstance(posts[name]["type"], postgresql.ARRAY):
            # Text[] -> JSONB retains every array element and works with the
            # API's JSON lists; NULL remains NULL.
            op.alter_column(
                "community_posts",
                name,
                existing_type=posts[name]["type"],
                type_=postgresql.JSONB(),
                postgresql_using=f"to_jsonb({name})",
                existing_nullable=posts[name]["nullable"],
            )

    for name in ("post_type", "visibility"):
        if isinstance(posts[name]["type"], postgresql.ENUM):
            # Preserve legacy lower-case enum values, while supporting new
            # image, video, question_discussion and study_tip post types.
            op.alter_column(
                "community_posts",
                name,
                existing_type=posts[name]["type"],
                type_=sa.String(length=30),
                postgresql_using=f"{name}::text",
                existing_nullable=posts[name]["nullable"],
            )

    if "is_hidden" not in posts:
        op.add_column(
            "community_posts",
            sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    comments = _columns("post_comments")
    if "is_hidden" not in comments:
        op.add_column(
            "post_comments",
            sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    likes = _columns("post_likes")
    if "comment_id" not in likes:
        op.add_column("post_likes", sa.Column("comment_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_post_likes_comment_id_post_comments",
            "post_likes",
            "post_comments",
            ["comment_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index("ix_post_likes_comment_id", "post_likes", ["comment_id"])
    if not likes["post_id"]["nullable"]:
        # Comment likes reference comment_id instead of a post, and must be
        # allowed to leave post_id NULL.
        op.alter_column(
            "post_likes",
            "post_id",
            existing_type=likes["post_id"]["type"],
            nullable=True,
        )


def downgrade() -> None:
    # Reverting JSONB media arrays and expanded post-type values to the
    # historical enum/array schema could silently discard user content.
    raise RuntimeError(
        "community_posts_002 is intentionally forward-only; "
        "restore from a verified database backup if rollback is required"
    )
