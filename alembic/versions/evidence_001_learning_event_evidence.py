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
    ("concept_id", sa.String(length=80), {"nullable": True}),
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


def _add_enum_value_if_postgres() -> None:
    """Teach the database enum about CLASSROOM_DEMONSTRATION.

    `LearningEvent.event_type` is a SQLAlchemy `Enum`, which on PostgreSQL is
    a native `eventtype` type. Adding a member to the Python enum does not
    add it to the database type, so the first insert carrying the new value
    fails with `invalid input value for enum eventtype`. That would not
    surface until the classroom starts emitting demonstrations — in
    production, on a learner's turn.

    SQLite and other backends store the value as text and need nothing.

    `ALTER TYPE ... ADD VALUE` cannot run inside the transaction that later
    uses the new value, so it goes in an autocommit block. `IF NOT EXISTS`
    keeps the migration re-runnable.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'CLASSROOM_DEMONSTRATION'"
        )


def _widen_mastery_objective_id() -> None:
    """Let `mastery_states.objective_id` hold a slug.

    The projection records slug-identified concepts here rather than in
    `concept_id`, which is foreign-keyed to `concepts.id` and so can only hold
    UUIDs. Chat's `slugify_skill` produces up to 80 characters, and the column
    was `String(36)`.

    Widening a varchar is not a table rewrite on PostgreSQL, so this is cheap
    even on a large table. Skipped when the column is already wide enough, and
    on SQLite, which does not enforce varchar length and has no ALTER for it.
    """
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    insp = sa.inspect(bind)
    if not insp.has_table("mastery_states"):
        return

    for column in insp.get_columns("mastery_states"):
        if column["name"] != "objective_id":
            continue
        length = getattr(column["type"], "length", None)
        if length is not None and length >= 80:
            return
        op.alter_column(
            "mastery_states",
            "objective_id",
            existing_type=sa.String(length=length or 36),
            type_=sa.String(length=80),
            existing_nullable=True,
        )
        return


def upgrade() -> None:
    _add_enum_value_if_postgres()
    _widen_mastery_objective_id()

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
    # The enum value is deliberately not removed. PostgreSQL has no
    # `ALTER TYPE ... DROP VALUE`, and rebuilding the type would require
    # rewriting every row that references it. An unused extra enum member is
    # harmless; a destructive downgrade is not.
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
