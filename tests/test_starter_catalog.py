"""Regression tests for the production starter-course data migration."""

import sqlalchemy as sa

from lyo_app.learning.catalog import STARTER_COURSES, seed_starter_catalog


def _catalog_database():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "organizations",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("slug", sa.String, nullable=False, unique=True),
        sa.Column("plan_tier", sa.String, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("contact_email", sa.String),
        sa.Column("monthly_api_calls", sa.Integer, nullable=False),
        sa.Column("monthly_ai_tokens", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("username", sa.String, nullable=False, unique=True),
        sa.Column("hashed_password", sa.String, nullable=False),
        sa.Column("first_name", sa.String),
        sa.Column("last_name", sa.String),
        sa.Column("bio", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("is_verified", sa.Boolean, nullable=False),
        sa.Column("is_superuser", sa.Boolean, nullable=False),
        sa.Column("auth_provider", sa.String),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "courses",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("short_description", sa.String),
        sa.Column("topic", sa.String),
        sa.Column("difficulty_level", sa.String, nullable=False),
        sa.Column("category", sa.String),
        sa.Column("tags", sa.JSON),
        sa.Column("estimated_duration_hours", sa.Float),
        sa.Column("target_duration_hours", sa.Float),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("is_published", sa.Boolean, nullable=False),
        sa.Column("is_featured", sa.Boolean, nullable=False),
        sa.Column("generation_metadata", sa.JSON),
        sa.Column("instructor_id", sa.Integer, nullable=False),
        sa.Column("organization_id", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("published_at", sa.DateTime),
    )
    sa.Table(
        "lessons",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("content", sa.Text),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("course_id", sa.Integer, nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("duration_minutes", sa.Integer),
        sa.Column("estimated_duration_minutes", sa.Float),
        sa.Column("topic", sa.String),
        sa.Column("tags", sa.JSON),
        sa.Column("is_published", sa.Boolean, nullable=False),
        sa.Column("is_preview", sa.Boolean, nullable=False),
        sa.Column("organization_id", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    metadata.create_all(engine)
    return engine


def test_starter_catalog_is_published_complete_and_idempotent():
    engine = _catalog_database()
    expected_lessons = sum(len(course["lessons"]) for course in STARTER_COURSES)

    with engine.begin() as connection:
        first = seed_starter_catalog(connection)
        second = seed_starter_catalog(connection)

        assert first == {"courses": len(STARTER_COURSES), "lessons": expected_lessons}
        assert second == {"courses": 0, "lessons": 0}
        assert connection.scalar(sa.text("SELECT count(*) FROM courses")) == len(STARTER_COURSES)
        assert connection.scalar(sa.text("SELECT count(*) FROM lessons")) == expected_lessons
        assert connection.scalar(
            sa.text("SELECT count(*) FROM courses WHERE is_published = 1")
        ) == len(STARTER_COURSES)
        assert connection.scalar(
            sa.text("SELECT count(*) FROM lessons WHERE length(content) < 200")
        ) == 0

