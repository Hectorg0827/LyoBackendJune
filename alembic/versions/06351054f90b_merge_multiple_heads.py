"""merge multiple heads

Revision ID: 06351054f90b
Revises: ai_classroom_001, booking_review_001, chat_001, clips_001, stack_001
Create Date: 2026-02-27 12:53:43.653301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06351054f90b'
down_revision: Union[str, None] = ('ai_classroom_001', 'booking_review_001', 'chat_001', 'clips_001', 'stack_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
