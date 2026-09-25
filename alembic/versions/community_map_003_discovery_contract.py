"""Community discovery contract: event details, moderation, idempotency, reports.

Revision ID: community_map_003
Revises: testprep_002
Create Date: 2026-09-25

Adds the event fields the shared map contract needs (visibility, pricing,
venue/address, attendance mode, moderation status, a client request id for
duplicate-free creation) plus the indexes discovery queries use.

It also repairs two production failures that tests on SQLite could not see:

* ``content_reports`` was created with PostgreSQL enum types that never held
  "event" or "group" and do not match the ORM's type names, and its notes
  column is ``resolution_notes`` while the model wrote ``resolution_note``, so
  every report returned 500. The enum columns become lowercase strings,
  which fits both historical shapes of the table.
* ``eventtype`` is one PostgreSQL type shared by ``community_events`` and
  ``learning_events`` (both SQLAlchemy enums default to that name). Whichever
  table created it first decided its labels, so the labels of both enums are
  ensured here. Adding an enum label is additive and never rejects a row.

Every step checks the live schema first, so the revision is safe on a
database that already has some of it.
"""

import sqlalchemy as sa
from alembic import op

revision = "community_map_003"
down_revision = "testprep_002"
branch_labels = None
depends_on = None

_COMMUNITY_EVENT_TYPES = (
    "STUDY_SESSION", "WORKSHOP", "CLASS", "SEMINAR", "LECTURE", "DISCUSSION",
    "PROJECT_SHOWCASE", "NETWORKING", "OFFICE_HOURS", "OTHER",
)
_LEARNING_EVENT_TYPES = (
    "QUIZ_ANSWER", "LESSON_COMPLETION", "AI_SESSION", "REFLECTION", "PROJECT",
    "VOICE_INTERACTION", "CLASSROOM_DEMONSTRATION",
)
_ENUM_LABELS = {
    "eventtype": _COMMUNITY_EVENT_TYPES + _LEARNING_EVENT_TYPES,
    "eventstatus": ("SCHEDULED", "ONGOING", "COMPLETED", "CANCELLED"),
    "attendancestatus": ("GOING", "MAYBE", "NOT_GOING", "ATTENDED", "NO_SHOW"),
}


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _columns(table: str) -> dict:
    if not _has_table(table):
        return {}
    return {column["name"]: column for column in _inspector().get_columns(table)}


def _index_names(table: str) -> set:
    if not _has_table(table):
        return set()
    inspector = _inspector()
    names = {index["name"] for index in inspector.get_indexes(table)}
    names.update(
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table)
        if constraint.get("name")
    )
    return names


def _add_column(table: str, column: sa.Column) -> None:
    if _has_table(table) and column.name not in _columns(table):
        op.add_column(table, column)


def _add_index(table: str, name: str, columns: list, unique: bool = False) -> None:
    if (
        _has_table(table)
        and set(columns).issubset(_columns(table))
        and name not in _index_names(table)
    ):
        op.create_index(name, table, columns, unique=unique)


def _upgrade_community_events() -> None:
    table = "community_events"
    if not _has_table(table):
        return
    _add_column(table, sa.Column("visibility", sa.String(20), nullable=False, server_default="public"))
    _add_column(table, sa.Column("price_type", sa.String(10), nullable=False, server_default="free"))
    _add_column(table, sa.Column("price_amount", sa.Float(), nullable=True))
    _add_column(table, sa.Column("currency", sa.String(10), nullable=True))
    _add_column(table, sa.Column("website_url", sa.String(500), nullable=True))
    _add_column(table, sa.Column("organizer_name", sa.String(200), nullable=True))
    _add_column(table, sa.Column("venue_name", sa.String(200), nullable=True))
    _add_column(table, sa.Column("address", sa.String(500), nullable=True))
    added_mode = "attendance_mode" not in _columns(table)
    _add_column(
        table,
        sa.Column("attendance_mode", sa.String(20), nullable=False, server_default="in_person"),
    )
    _add_column(
        table,
        sa.Column("moderation_status", sa.String(20), nullable=False, server_default="active"),
    )
    _add_column(table, sa.Column("client_request_id", sa.String(64), nullable=True))

    if added_mode:
        # Existing events already say whether they are online and whether
        # they have a pin; derive the mode from those facts once.
        op.execute(
            sa.text(
                """
                UPDATE community_events
                SET attendance_mode = CASE
                    WHEN is_online AND latitude IS NOT NULL THEN 'hybrid'
                    WHEN is_online THEN 'online'
                    ELSE 'in_person'
                END
                """
            )
        )

    _add_index(
        table,
        "uq_community_events_organizer_request",
        ["organizer_id", "client_request_id"],
        unique=True,
    )
    _add_index(table, "ix_community_events_status_end_time", ["status", "end_time"])
    _add_index(table, "ix_community_events_lat_lng", ["latitude", "longitude"])
    _add_index(table, "ix_community_events_visibility", ["visibility"])
    _add_index(table, "ix_community_events_event_type", ["event_type"])


def _repair_content_reports() -> None:
    table = "content_reports"
    columns = _columns(table)
    if not columns:
        return
    bind = op.get_bind()
    dialect = bind.dialect.name

    if "resolution_note" in columns and "resolution_notes" not in columns:
        op.alter_column(table, "resolution_note", new_column_name="resolution_notes")
    elif "resolution_notes" not in columns:
        op.add_column(table, sa.Column("resolution_notes", sa.Text(), nullable=True))

    for column in ("target_type", "reason", "status"):
        if column not in columns:
            continue
        if dialect == "postgresql":
            op.execute(
                sa.text(
                    f"ALTER TABLE content_reports ALTER COLUMN {column} "
                    f"TYPE VARCHAR(30) USING lower({column}::text)"
                )
            )
        else:
            op.execute(sa.text(f"UPDATE content_reports SET {column} = lower({column})"))

    if dialect == "postgresql":
        op.execute(sa.text("ALTER TABLE content_reports ALTER COLUMN status SET DEFAULT 'pending'"))
        target_id = columns.get("target_id")
        length = getattr(target_id["type"], "length", None) if target_id else None
        if length is not None and length < 100:
            op.execute(sa.text("ALTER TABLE content_reports ALTER COLUMN target_id TYPE VARCHAR(100)"))


def _ensure_enum_labels() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    existing_types = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT typname FROM pg_type WHERE typname = ANY(:names)"),
            {"names": list(_ENUM_LABELS)},
        )
    }
    # ADD VALUE cannot share a transaction with statements that use the new
    # label, so it runs in its own autocommit block (as evidence_001 does).
    with op.get_context().autocommit_block():
        for type_name, labels in _ENUM_LABELS.items():
            if type_name not in existing_types:
                continue
            for label in labels:
                op.execute(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{label}'")


def upgrade() -> None:
    _upgrade_community_events()
    _repair_content_reports()
    _ensure_enum_labels()


def downgrade() -> None:
    table = "community_events"
    existing = _columns(table)
    for index in (
        "ix_community_events_event_type",
        "ix_community_events_visibility",
        "ix_community_events_lat_lng",
        "ix_community_events_status_end_time",
        "uq_community_events_organizer_request",
    ):
        if index in _index_names(table):
            op.drop_index(index, table_name=table)
    for column in (
        "client_request_id", "moderation_status", "attendance_mode", "address",
        "venue_name", "organizer_name", "website_url", "currency", "price_amount",
        "price_type", "visibility",
    ):
        if column in existing:
            op.drop_column(table, column)
    # content_reports keeps its string columns and enum labels stay: both are
    # strictly wider than before and dropping them could lose report rows.
