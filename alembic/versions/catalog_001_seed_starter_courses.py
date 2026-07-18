"""Seed the shared starter learning catalog.

Revision ID: catalog_001
Revises: chat_003
Create Date: 2026-07-18
"""

import sqlalchemy as sa
from alembic import op

from lyo_app.learning.catalog import remove_starter_catalog, seed_starter_catalog


revision = "catalog_001"
down_revision = "chat_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "organizations" not in sa.inspect(bind).get_table_names():
        # Legacy databases created this ORM table during app startup rather
        # than through Alembic.  Pre-deploy migrations run before startup, so
        # a clean PostgreSQL release must establish it here first.
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
            sa.Column("plan_tier", sa.String(length=50), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("contact_email", sa.String(length=255), nullable=True),
            sa.Column("monthly_api_calls", sa.Integer(), nullable=False),
            sa.Column("monthly_ai_tokens", sa.Integer(), nullable=False),
            sa.Column("usage_reset_at", sa.DateTime(), nullable=True),
            sa.Column("custom_rate_limit", sa.Integer(), nullable=True),
            sa.Column("custom_ai_limit", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    seed_starter_catalog(bind)


def downgrade() -> None:
    remove_starter_catalog(op.get_bind())
