"""Community event invitations: invite links and guest lists.

Revision ID: community_map_004
Revises: community_map_003
Create Date: 2026-09-25

Private events were visible only to their host and people who had already
RSVP'd, so there was no way to let anyone in. Hosts can now share invite
links (optionally limited by uses and expiry, revocable) and invite Lyo
members by name; either way the person joins the event's guest list, which
grants access to that one event.

Both tables are new and additive. Creation is skipped when a table already
exists, so the revision is safe to re-run.
"""

import sqlalchemy as sa
from alembic import op

revision = "community_map_004"
down_revision = "community_map_003"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("community_event_invites"):
        op.create_table(
            "community_event_invites",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "event_id",
                sa.Integer(),
                sa.ForeignKey("community_events.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token", sa.String(64), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_community_event_invites_id", "community_event_invites", ["id"])
        op.create_index("ix_community_event_invites_event_id", "community_event_invites", ["event_id"])
        op.create_index(
            "ix_community_event_invites_token", "community_event_invites", ["token"], unique=True
        )

    if not _has_table("community_event_guests"):
        op.create_table(
            "community_event_guests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "event_id",
                sa.Integer(),
                sa.ForeignKey("community_events.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("invited_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column(
                "invite_id",
                sa.Integer(),
                sa.ForeignKey("community_event_invites.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("source", sa.String(10), nullable=False, server_default="link"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("event_id", "user_id", name="uq_community_event_guest"),
        )
        op.create_index("ix_community_event_guests_id", "community_event_guests", ["id"])
        op.create_index("ix_community_event_guests_event_id", "community_event_guests", ["event_id"])
        op.create_index("ix_community_event_guests_user_id", "community_event_guests", ["user_id"])


def downgrade() -> None:
    if _has_table("community_event_guests"):
        op.drop_table("community_event_guests")
    if _has_table("community_event_invites"):
        op.drop_table("community_event_invites")
