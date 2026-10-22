"""Bootstrap the default organization required by Chat tenant records.

Revision ID: coach_003
Revises: coach_002

Chat models inherit TenantMixin, whose historical default organization_id=1.
A fresh database has no organization with ID 1 unless it was manually seeded,
so a first authenticated Chat turn otherwise fails with a foreign-key error.

This migration inserts only the missing default. Existing organizations,
billing settings and user-to-tenant mappings are never changed.
"""
from alembic import op
import sqlalchemy as sa

revision = "coach_003"
down_revision = "coach_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("organizations"):
        raise RuntimeError("Organization table is missing before tenant bootstrap")
    bind.execute(sa.text(
        """
        INSERT INTO organizations
            (id, name, slug, plan_tier, is_active,
             monthly_api_calls, monthly_ai_tokens, created_at, updated_at)
        VALUES
            (1, 'Lyo Default', 'lyo-default-tenant', 'free', TRUE,
             0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT DO NOTHING
        """
    ))
    if bind.execute(sa.text("SELECT id FROM organizations WHERE id = 1")).scalar_one_or_none() is None:
        raise RuntimeError("Default Chat tenant could not be initialized safely")


def downgrade() -> None:
    # Do not remove an organization that may now own real chat sessions.
    # The tenant bootstrap is data-safe and intentionally irreversible.
    pass
