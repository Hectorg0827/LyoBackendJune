"""Reconcile legacy Community events missing the max_attendees column.

Revision ID: community_capacity_001
Revises: refresh_tokens_001
Create Date: 2026-10-30

Older databases have community_events but not the nullable capacity field
used by the Community discovery service. Preserve existing event data.
"""

import sqlalchemy as sa
from alembic import op

revision = "community_capacity_001"
down_revision = "refresh_tokens_001"
branch_labels = None
depends_on = None


def _has_capacity_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("community_events"):
        raise RuntimeError(
            "community_events is missing; migrate the Community base schema first"
        )
    return any(
        column["name"] == "max_attendees"
        for column in inspector.get_columns("community_events")
    )


def upgrade() -> None:
    if not _has_capacity_column():
        op.add_column(
            "community_events", sa.Column("max_attendees", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    # Rollback removes this field (and any data subsequently written to it).
    if _has_capacity_column():
        op.drop_column("community_events", "max_attendees")
