"""Add evidence columns to learning_events.

These let one LearningEvent say what it proves about one concept, in the
vocabulary of lyo_app/events/evidence.py, so the same evidence can be
projected into both mastery tables instead of each surface keeping its own
private record.

Every column is nullable (hints_used defaults to 0), so existing rows stay
valid and simply contribute no rung to mastery. Nothing is migrated and
nothing is dropped.

Written idempotently, following users_sync_001: this codebase also runs
`Base.metadata.create_all` at startup, so on an environment that has already
booted the new ORM model these columns may exist before alembic reaches this
revision. Adding a column that is already there would otherwise abort the
whole upgrade.

Revision ID: evidence_001
Revises: community_map_002
Create Date: 2026-09-09
"""
import sqlalchemy as sa
from alembic import op

revision = "evidence_001"
down_revision = "community_map_002"
branch_labels = None
depends_on = None


TABLE = "learning_events"

# (name, type, extra kwargs) — kept in one place so upgrade and downgrade
# cannot drift apart.
COLUMNS = (
    ("concept_id", sa.String(length=64), {"nullable": True}),
    ("evidence_type", sa.String(length=32), {"nullable": True}),
    ("evidence_confidence", sa.Float(), {"nullable": True}),
    ("hints_used", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("misconception", sa.String(length=500), {"nullable": True}),
    ("source_surface", sa.String(length=32), {"nullable": True}),
)

INDEXES = (
    ("ix_learning_events_concept_id", "concept_id"),
    ("ix_learning_events_source_surface", "source_surface"),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _existing_columns() -> set:
    insp = _inspector()
    if not insp.has_table(TABLE):
        return set()
    return {c["name"] for c in insp.get_columns(TABLE)}


def _existing_indexes() -> set:
    insp = _inspector()
    if not insp.has_table(TABLE):
        return set()
    return {i["name"] for i in insp.get_indexes(TABLE)}


def upgrade() -> None:
    insp = _inspector()
    # A database built without the events module at all has nothing to alter;
    # create_all will build the table complete when it first appears.
    if not insp.has_table(TABLE):
        return

    present = _existing_columns()
    for name, type_, kwargs in COLUMNS:
        if name not in present:
            op.add_column(TABLE, sa.Column(name, type_, **kwargs))

    present_indexes = _existing_indexes()
    columns_now = _existing_columns()
    for index_name, column in INDEXES:
        if index_name not in present_indexes and column in columns_now:
            op.create_index(index_name, TABLE, [column])


def downgrade() -> None:
    insp = _inspector()
    if not insp.has_table(TABLE):
        return

    present_indexes = _existing_indexes()
    for index_name, _column in INDEXES:
        if index_name in present_indexes:
            op.drop_index(index_name, table_name=TABLE)

    present = _existing_columns()
    for name, _type, _kwargs in COLUMNS:
        if name in present:
            op.drop_column(TABLE, name)
