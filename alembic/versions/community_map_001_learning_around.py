"""Add the cross-platform Learning Around Me account contract.

Revision ID: community_map_001
Revises: chat_blocks_001
Create Date: 2026-08-20
"""

import sqlalchemy as sa
from alembic import op

revision = "community_map_001"
down_revision = "chat_blocks_001"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if _has_table(table) and column.name not in _columns(table):
        op.add_column(table, column)


def _add_index(table: str, name: str, columns: list[str]) -> None:
    if _has_table(table) and name not in _indexes(table):
        op.create_index(name, table, columns, unique=False)


def upgrade() -> None:
    # These event fields existed in the ORM/client contract but never had a
    # canonical migration, which is why created map pins could disappear in
    # production even though tests built from metadata passed.
    _add_column(
        "community_events",
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _add_column("community_events", sa.Column("latitude", sa.Float(), nullable=True))
    _add_column("community_events", sa.Column("longitude", sa.Float(), nullable=True))
    _add_column("community_events", sa.Column("room_id", sa.String(100), nullable=True))
    _add_column("community_events", sa.Column("image_url", sa.String(500), nullable=True))
    _add_index("community_events", "ix_community_events_latitude", ["latitude"])
    _add_index("community_events", "ix_community_events_longitude", ["longitude"])

    _add_column("study_groups", sa.Column("location", sa.String(300), nullable=True))
    _add_column(
        "study_groups",
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _add_column("study_groups", sa.Column("meeting_url", sa.String(500), nullable=True))
    _add_column("study_groups", sa.Column("latitude", sa.Float(), nullable=True))
    _add_column("study_groups", sa.Column("longitude", sa.Float(), nullable=True))
    _add_column("study_groups", sa.Column("image_url", sa.String(500), nullable=True))
    _add_index("study_groups", "ix_study_groups_latitude", ["latitude"])
    _add_index("study_groups", "ix_study_groups_longitude", ["longitude"])

    _add_column(
        "private_lessons",
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _add_column("private_lessons", sa.Column("meeting_url", sa.String(500), nullable=True))
    _add_column("private_lessons", sa.Column("image_url", sa.String(500), nullable=True))

    if not _has_table("community_saved_nodes"):
        op.create_table(
            "community_saved_nodes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("node_kind", sa.String(50), nullable=False),
            sa.Column("node_id", sa.String(255), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                "user_id",
                "node_kind",
                "node_id",
                name="uq_community_saved_node_user_kind_id",
            ),
        )
        op.create_index("ix_community_saved_nodes_id", "community_saved_nodes", ["id"])
        op.create_index("ix_community_saved_nodes_user_id", "community_saved_nodes", ["user_id"])
        op.create_index("ix_community_saved_nodes_node_kind", "community_saved_nodes", ["node_kind"])
        op.create_index("ix_community_saved_nodes_node_id", "community_saved_nodes", ["node_id"])

    # SQLAlchemy persists enum member names for this legacy type.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'OFFICE_HOURS'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'CLASS'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'SEMINAR'")


def downgrade() -> None:
    if _has_table("community_saved_nodes"):
        op.drop_table("community_saved_nodes")

    for table, columns in (
        ("private_lessons", ["image_url", "meeting_url", "is_online"]),
        (
            "study_groups",
            ["image_url", "longitude", "latitude", "meeting_url", "is_online", "location"],
        ),
        (
            "community_events",
            ["image_url", "room_id", "longitude", "latitude", "is_online"],
        ),
    ):
        existing = _columns(table)
        for column in columns:
            if column in existing:
                op.drop_column(table, column)

    # PostgreSQL enum values cannot be safely removed in a downgrade.
