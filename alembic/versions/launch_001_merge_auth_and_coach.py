"""Join credential revocation and Coach schema histories without dropping either.

Revision ID: launch_001
Revises: auth_refresh_text_001, coach_003
"""

revision = "launch_001"
down_revision = ("auth_refresh_text_001", "coach_003")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
