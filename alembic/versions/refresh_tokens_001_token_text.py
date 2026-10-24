"""Let refresh tokens be longer than 255 characters.

A login stores its refresh JWT in refresh_tokens.token, which was
VARCHAR(255). The JWT carries the user id twice, so it is 251 characters for
user 7 and 256 for user 123: from the 100th account on, every email and
password login failed with "value too long". TEXT has no limit; in
PostgreSQL the change rewrites nothing.

The server creates refresh_tokens at startup (lyo_app.core.database), so on
a new database the table may not exist yet; it is then created as TEXT.

Revision ID: refresh_tokens_001
Revises: password_reset_001
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op

revision = "refresh_tokens_001"
down_revision = "password_reset_001"
branch_labels = None
depends_on = None


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table("refresh_tokens")


def upgrade():
    if _has_table():
        op.alter_column("refresh_tokens", "token", type_=sa.Text(),
                        existing_type=sa.String(length=255), existing_nullable=False)


def downgrade():
    if _has_table():
        op.alter_column("refresh_tokens", "token", type_=sa.String(length=255),
                        existing_type=sa.Text(), existing_nullable=False)
