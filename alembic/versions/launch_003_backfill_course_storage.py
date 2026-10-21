"""Finish additive legacy learning-table upgrade after launch_002.

Revision ID: launch_003
Revises: launch_002

launch_002 was already applied to isolated staging before tenant-field
compatibility was discovered. Never edit applied migrations to repair live
schemas: this new revision works for both existing upgraded databases and
fresh baseline -> head rehearsals. Preserve all learner/course/lesson rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "launch_003"
down_revision = "launch_002"
branch_labels = None
depends_on = None


def _columns(table):
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        raise RuntimeError(f"Required {table} table is missing")
    return {column["name"]: column for column in inspector.get_columns(table)}


def _add_missing(table, name, column):
    if name not in _columns(table):
        op.add_column(table, column)


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("organizations"):
        raise RuntimeError("Tenant table is required before learning schema upgrade")
    if bind.execute(sa.text("SELECT id FROM organizations WHERE id=1")).scalar_one_or_none() is None:
        raise RuntimeError("Default tenant missing; cannot safely assign historical learning rows")

    for table in ("courses", "lessons"):
        if "organization_id" not in _columns(table):
            op.add_column(table, sa.Column(
                "organization_id", sa.Integer(), nullable=False, server_default="1"
            ))
            op.create_foreign_key(
                f"fk_{table}_organization_id_organizations",
                table, "organizations", ["organization_id"], ["id"]
            )
            op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])

    course_missing = {
        "summary": sa.Column("summary", sa.Text(), nullable=True),
        "topic": sa.Column("topic", sa.String(200), nullable=True),
        "interests": sa.Column("interests", sa.JSON(), nullable=True),
        "target_duration_hours": sa.Column("target_duration_hours", sa.Float(), nullable=True),
        "generation_metadata": sa.Column("generation_metadata", sa.JSON(), nullable=True),
        "published_at": sa.Column("published_at", sa.DateTime(), nullable=True),
    }
    for name, column in course_missing.items():
        _add_missing("courses", name, column)

    lesson_missing = {
        "summary": sa.Column("summary", sa.Text(), nullable=True),
        "ai_summary": sa.Column("ai_summary", sa.Text(), nullable=True),
        "estimated_duration_minutes": sa.Column("estimated_duration_minutes", sa.Float(), nullable=True),
        "topic": sa.Column("topic", sa.String(200), nullable=True),
        "tags": sa.Column("tags", sa.JSON(), nullable=True),
        "difficulty_score": sa.Column("difficulty_score", sa.Float(), nullable=True),
        "generation_prompt": sa.Column("generation_prompt", sa.Text(), nullable=True),
    }
    for name, column in lesson_missing.items():
        _add_missing("lessons", name, column)

    # Vector fields are ORM-mapped, including nullable INSERTs. They need
    # real PostgreSQL columns even when staging generation has no embedding.
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        for table in ("courses", "lessons"):
            if "embedding" not in _columns(table):
                op.execute(f"ALTER TABLE {table} ADD COLUMN embedding vector(768)")
        # Original lesson titles were varchar(200); the durable model permits
        # 500. Widening does not discard or reinterpret existing titles.
        op.execute("ALTER TABLE lessons ALTER COLUMN title TYPE VARCHAR(500)")
        # Preserve original hour counts while permitting fractions.
        op.execute(
            "ALTER TABLE courses ALTER COLUMN estimated_duration_hours "
            "TYPE DOUBLE PRECISION USING estimated_duration_hours::double precision"
        )


def downgrade():
    # Avoid dropping added columns or tenant backfill that may now hold real
    # generated content; rollback requires a separate evidence-led migration.
    pass
