"""Seed the shared starter learning catalog.

Revision ID: catalog_001
Revises: chat_003
Create Date: 2026-07-18
"""

from alembic import op

from lyo_app.learning.catalog import remove_starter_catalog, seed_starter_catalog


revision = "catalog_001"
down_revision = "chat_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed_starter_catalog(op.get_bind())


def downgrade() -> None:
    remove_starter_catalog(op.get_bind())

