"""Reconcile the production Learning Around Me schema.

Revision ID: community_map_002
Revises: community_map_001
Create Date: 2026-08-23

The first map migration was intentionally tolerant of legacy environments.
This follow-up makes that tolerance observable and repeatable: if a production
database recorded the earlier revision while retaining partial schema drift,
the next deploy repairs the canonical account-level map contract.
"""

import sqlalchemy as sa
from alembic import op

revision = "community_map_002"
down_revision = "community_map_001"
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


def _primary_key_columns(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    constraint = sa.inspect(op.get_bind()).get_pk_constraint(table)
    return set(constraint.get("constrained_columns") or [])


def _has_unique_identity(table: str) -> bool:
    identity = {"user_id", "node_kind", "node_id"}
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints(table):
        if set(constraint.get("column_names") or []) == identity:
            return True
    return any(
        index.get("unique")
        and set(index.get("column_names") or []) == identity
        for index in inspector.get_indexes(table)
    )


def _add_column(table: str, column: sa.Column) -> None:
    if _has_table(table) and column.name not in _columns(table):
        op.add_column(table, column)


def _add_index(table: str, name: str, columns: list[str]) -> None:
    if (
        _has_table(table)
        and set(columns).issubset(_columns(table))
        and name not in _indexes(table)
    ):
        op.create_index(name, table, columns, unique=False)


def _create_saved_nodes_table() -> None:
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


def _next_backup_table_name() -> str:
    base = "community_saved_nodes_partial_backup_002"
    name = base
    suffix = 1
    while _has_table(name):
        suffix += 1
        name = f"{base}_{suffix}"
    return name


def _ensure_saved_node_indexes() -> None:
    for name, columns in (
        ("ix_community_saved_nodes_id", ["id"]),
        ("ix_community_saved_nodes_user_id", ["user_id"]),
        ("ix_community_saved_nodes_node_kind", ["node_kind"]),
        ("ix_community_saved_nodes_node_id", ["node_id"]),
    ):
        _add_index("community_saved_nodes", name, columns)


def _strip_backup_keys_and_indexes(table: str) -> None:
    """Keep backup rows without reserving canonical PostgreSQL index names."""
    inspector = sa.inspect(op.get_bind())
    if op.get_bind().dialect.name == "postgresql":
        for constraint in inspector.get_unique_constraints(table):
            if constraint.get("name"):
                op.drop_constraint(constraint["name"], table, type_="unique")
        primary_key = inspector.get_pk_constraint(table)
        if primary_key.get("name"):
            op.drop_constraint(primary_key["name"], table, type_="primary")

    # Explicit index names are schema-wide in both PostgreSQL and SQLite.
    # The backup is recovery-only, so removing its indexes preserves every row
    # while freeing the canonical names for the live table.
    for index in sa.inspect(op.get_bind()).get_indexes(table):
        if index.get("name"):
            op.drop_index(index["name"], table_name=table)


def _reconcile_saved_nodes_table() -> None:
    if not _has_table("community_saved_nodes"):
        _create_saved_nodes_table()
        _ensure_saved_node_indexes()
        return

    # Rows without these identity fields (or without an id primary key) cannot
    # be associated with an account safely. Preserve that table for recovery
    # and create a working canonical table instead of dropping unknown data.
    identity_columns = {"id", "user_id", "node_kind", "node_id"}
    if (
        not identity_columns.issubset(_columns("community_saved_nodes"))
        or _primary_key_columns("community_saved_nodes") != {"id"}
    ):
        backup_table = _next_backup_table_name()
        op.rename_table("community_saved_nodes", backup_table)
        _strip_backup_keys_and_indexes(backup_table)
        _create_saved_nodes_table()
        _ensure_saved_node_indexes()
        return

    _add_column(
        "community_saved_nodes",
        sa.Column("snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    # SQLite forbids adding a column with CURRENT_TIMESTAMP to an existing
    # table. Production PostgreSQL receives the real current-time default;
    # the constant is only a portable backfill for legacy SQLite databases.
    timestamp_default = (
        sa.text("'1970-01-01 00:00:00'")
        if op.get_bind().dialect.name == "sqlite"
        else sa.func.now()
    )
    _add_column(
        "community_saved_nodes",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=timestamp_default),
    )
    _add_column(
        "community_saved_nodes",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=timestamp_default),
    )

    if not _has_unique_identity("community_saved_nodes"):
        # A missing unique constraint may already have admitted duplicate
        # saves. They represent the same account-owned state, so preserve the
        # newest id before restoring the invariant.
        op.execute(
            sa.text(
                """
                DELETE FROM community_saved_nodes
                WHERE id IN (
                    SELECT id
                    FROM (
                        SELECT
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY user_id, node_kind, node_id
                                ORDER BY id DESC
                            ) AS duplicate_rank
                        FROM community_saved_nodes
                        WHERE user_id IS NOT NULL
                          AND node_kind IS NOT NULL
                          AND node_id IS NOT NULL
                    ) AS duplicate_saves
                    WHERE duplicate_rank > 1
                )
                """
            )
        )
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("community_saved_nodes") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_community_saved_node_user_kind_id",
                    ["user_id", "node_kind", "node_id"],
                )
        else:
            op.create_unique_constraint(
                "uq_community_saved_node_user_kind_id",
                "community_saved_nodes",
                ["user_id", "node_kind", "node_id"],
            )

    _ensure_saved_node_indexes()


def upgrade() -> None:
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

    _reconcile_saved_nodes_table()

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'OFFICE_HOURS'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'CLASS'")
        op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'SEMINAR'")


def downgrade() -> None:
    # This is a repair-only revision. community_map_001 owns the schema and
    # performs the canonical downgrade; removing repaired production columns
    # here would make a downgrade from 002 to 001 destructive.
    pass
