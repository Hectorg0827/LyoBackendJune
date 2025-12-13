"""add_stack_items_table

Revision ID: stack_001
Revises: 156c634b5cea
Create Date: 2025-12-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'stack_001'
down_revision: Union[str, None] = '156c634b5cea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create stack_items table
    op.create_table('stack_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('item_type', sa.String(length=50), nullable=True, default='topic'),
        sa.Column('status', sa.String(length=50), nullable=True, default='not_started'),
        sa.Column('progress', sa.Float(), nullable=True, default=0.0),
        sa.Column('priority', sa.Integer(), nullable=True, default=0),
        sa.Column('content_id', sa.String(length=255), nullable=True),
        sa.Column('content_type', sa.String(length=50), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_stack_items_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_stack_items'))
    )
    op.create_index(op.f('ix_stack_items_id'), 'stack_items', ['id'], unique=False)
    op.create_index(op.f('ix_stack_items_user_id'), 'stack_items', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_stack_items_user_id'), table_name='stack_items')
    op.drop_index(op.f('ix_stack_items_id'), table_name='stack_items')
    op.drop_table('stack_items')
