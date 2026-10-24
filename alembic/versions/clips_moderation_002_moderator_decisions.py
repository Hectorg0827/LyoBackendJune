"""Record moderators' decisions on Discover clips.

A moderator can now keep a reported clip, remove it or restore it. Each
clip records the last decision: when, by whom, and the moderator's note.
"removed" joins "active" and "hidden" in moderation_status, which is a plain
string, so no change is needed there.

Revision ID: clips_moderation_002
Revises: clips_moderation_001
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op

revision = "clips_moderation_002"
down_revision = "clips_moderation_001"
branch_labels = None
depends_on = None

FOREIGN_KEY = "fk_clips_moderated_by_id_users"


def _columns():
    return [
        sa.Column("moderated_at", sa.DateTime(), nullable=True),
        sa.Column("moderated_by_id", sa.Integer(), nullable=True),
        sa.Column("moderation_note", sa.String(length=500), nullable=True),
    ]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("clips"):
        return
    existing = {c["name"] for c in inspector.get_columns("clips")}
    for column in _columns():
        if column.name not in existing:
            op.add_column("clips", column)
    if FOREIGN_KEY not in {fk["name"] for fk in inspector.get_foreign_keys("clips")}:
        op.create_foreign_key(FOREIGN_KEY, "clips", "users", ["moderated_by_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("clips"):
        return
    if FOREIGN_KEY in {fk["name"] for fk in inspector.get_foreign_keys("clips")}:
        op.drop_constraint(FOREIGN_KEY, "clips", type_="foreignkey")
    existing = {c["name"] for c in inspector.get_columns("clips")}
    for column in reversed(_columns()):
        if column.name in existing:
            op.drop_column("clips", column.name)
