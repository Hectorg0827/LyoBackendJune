"""Let learner reports take a clip out of Discover.

Discover had no way to report a video. A learner can now report one; it
leaves their own feed at once, and once three different learners have
reported it, moderation_status becomes "hidden" and the feed stops serving
it to anyone but its owner until a moderator decides. Every existing clip
starts "active", so nothing in the feed changes when this runs.

Reports themselves go in content_reports, whose target_type is a plain
string since community_map_003, so "clip" needs no change there.

Revision ID: clips_moderation_001
Revises: clips_media_001
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op

revision = "clips_moderation_001"
down_revision = "clips_media_001"
branch_labels = None
depends_on = None

INDEX = "ix_clips_moderation_status"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("clips"):
        return
    inspector = sa.inspect(op.get_bind())
    if "moderation_status" not in {c["name"] for c in inspector.get_columns("clips")}:
        op.add_column(
            "clips",
            sa.Column("moderation_status", sa.String(length=16), nullable=False, server_default="active"),
        )
    if INDEX not in {i["name"] for i in inspector.get_indexes("clips")}:
        op.create_index(INDEX, "clips", ["moderation_status"])


def downgrade() -> None:
    if not _has_table("clips"):
        return
    inspector = sa.inspect(op.get_bind())
    if INDEX in {i["name"] for i in inspector.get_indexes("clips")}:
        op.drop_index(INDEX, table_name="clips")
    if "moderation_status" in {c["name"] for c in inspector.get_columns("clips")}:
        op.drop_column("clips", "moderation_status")
