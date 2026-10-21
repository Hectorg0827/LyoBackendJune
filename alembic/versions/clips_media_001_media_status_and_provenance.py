"""Track whether a clip's video exists, and where a library video came from.

Discover served every public clip row whether or not its video was still in
storage. Clips uploaded before durable storage lived on a container disk that
each redeploy erased, so their rows outlived their videos and the feed
offered videos that could only fail. A clip now carries media_status, and the
feed serves only "ready" ones. Existing rows start "unverified" until
scripts/discover_media_audit.py checks storage for them.

The provenance columns carry the source and licence of library videos, whose
Creative Commons terms are only met when the credit is shown with the video.

Two gaps between the migrations and the models are closed here too, because
a database built by migrations alone could not run Discover: clip_saves was
only ever made by the app's startup create_all, so saving failed; and
clip_views lacked the viewed_at and watch_duration_seconds columns the view
endpoint writes, so recording a view rolled back and view counts, which rank
the For You feed, never moved. Both steps are skipped where already present.

Revision ID: clips_media_001
Revises: coach_001
Create Date: 2026-10-21
"""
import sqlalchemy as sa
from alembic import op

revision = "clips_media_001"
down_revision = "coach_001"
branch_labels = None
depends_on = None


def _columns():
    """Fresh Column objects; a Column can only be attached to one table."""
    return [
        sa.Column("media_status", sa.String(length=16), nullable=False, server_default="unverified"),
        sa.Column("media_bytes", sa.BigInteger(), nullable=True),
        sa.Column("media_checked_at", sa.DateTime(), nullable=True),
        sa.Column("source_name", sa.String(length=120), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("license_name", sa.String(length=60), nullable=True),
        sa.Column("license_url", sa.String(length=500), nullable=True),
        sa.Column("attribution", sa.String(length=300), nullable=True),
    ]


# name -> (column, unique). A source URL is unique: one source is one video
# in the feed, and the index settles imports that race each other.
INDEXES = {"ix_clips_media_status": ("media_status", False), "ix_clips_source_url": ("source_url", True)}


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _existing_columns(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _existing_indexes(table: str) -> set:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if not _has_table("clips"):
        return
    existing = _existing_columns("clips")
    for column in _columns():
        if column.name not in existing:
            op.add_column("clips", column)
    indexes = _existing_indexes("clips")
    for name, (column, unique) in INDEXES.items():
        if name not in indexes:
            op.create_index(name, "clips", [column], unique=unique)

    if not _has_table("clip_saves"):
        op.create_table(
            "clip_saves",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clip_id", sa.Integer(), sa.ForeignKey("clips.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    if _has_table("clip_views"):
        views = _existing_columns("clip_views")
        if "viewed_at" not in views:
            op.add_column("clip_views", sa.Column("viewed_at", sa.DateTime(), nullable=True,
                                                  server_default=sa.text("now()")))
        if "watch_duration_seconds" not in views:
            op.add_column("clip_views", sa.Column("watch_duration_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    # clip_saves and the clip_views columns stay: the models need them, and
    # dropping clip_saves would delete what learners saved.
    if not _has_table("clips"):
        return
    indexes = _existing_indexes("clips")
    for name in INDEXES:
        if name in indexes:
            op.drop_index(name, table_name="clips")
    existing = _existing_columns("clips")
    for column in reversed(_columns()):
        if column.name in existing:
            op.drop_column("clips", column.name)
