"""Make legacy course/lesson storage compatible with durable generated-course writes.

Revision ID: launch_002
Revises: launch_001

Historical integer-ID learning tables were created without topic, status,
published_at and lesson topic/tags. The newer ORM maps those columns, so a
valid authenticated course save returned 503 on the real staging database.
Older PostgreSQL ENUM columns also reject the lowercase values emitted by
the current String-based ORM. Apply only additive columns and lossless enum
to text casts; keep all existing learner/course/lesson rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "launch_002"
down_revision = "launch_001"
branch_labels = None
depends_on = None


def _columns(table: str) -> dict:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        raise RuntimeError(f"Required learning table {table} is missing")
    return {column["name"]: column for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    course_cols = _columns("courses")
    lesson_cols = _columns("lessons")

    if "topic" not in course_cols:
        op.add_column("courses", sa.Column("topic", sa.String(200), nullable=True))
    if "published_at" not in course_cols:
        op.add_column("courses", sa.Column("published_at", sa.DateTime(), nullable=True))
    if "status" not in course_cols:
        op.add_column("courses", sa.Column("status", sa.String(20), nullable=False,
                                            server_default="draft"))
        # Preserve the historical published/unpublished distinction.
        bind.execute(sa.text(
            "UPDATE courses SET status = 'published' WHERE is_published = TRUE"
        ))

    if "topic" not in lesson_cols:
        op.add_column("lessons", sa.Column("topic", sa.String(200), nullable=True))
    if "tags" not in lesson_cols:
        op.add_column("lessons", sa.Column("tags", sa.JSON(), nullable=True))

    # The original PostgreSQL schema used capitalized enum member names.
    # The current ORM uses plain strings ("beginner", "text") rather than
    # SQLEnum, and lower-case writes would otherwise fail on PostgreSQL.
    # Converting these two columns to VARCHAR preserves every existing row
    # and leaves legacy ENUM types for other dependent tables, if any.
    if bind.dialect.name == "postgresql":
        course_cols = _columns("courses")
        lesson_cols = _columns("lessons")
        if isinstance(course_cols["difficulty_level"]["type"], sa.Enum):
            op.execute(
                "ALTER TABLE courses ALTER COLUMN difficulty_level "
                "TYPE VARCHAR(20) USING lower(difficulty_level::text)"
            )
        if isinstance(lesson_cols["content_type"]["type"], sa.Enum):
            op.execute(
                "ALTER TABLE lessons ALTER COLUMN content_type "
                "TYPE VARCHAR(50) USING lower(content_type::text)"
            )


def downgrade() -> None:
    # No destructive rollback: these additive compatibility columns and
    # lowercase strings can be read by both old and new clients. Reverse
    # migration requires an explicit data audit, never a silent row rewrite.
    pass
