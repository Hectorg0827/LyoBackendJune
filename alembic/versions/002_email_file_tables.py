"""create email and file tables

Revision ID: 002_email_file_tables
Revises: 001_initial_migration
Create Date: 2025-06-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_email_file_tables'
down_revision = '001_initial_migration'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Email verification tokens table
    op.create_table('email_verification_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_email_verification_tokens_id'), 'email_verification_tokens', ['id'], unique=False)
    op.create_index(op.f('ix_email_verification_tokens_user_id'), 'email_verification_tokens', ['user_id'], unique=False)
    op.create_index(op.f('ix_email_verification_tokens_expires_at'), 'email_verification_tokens', ['expires_at'], unique=False)

    # Password reset tokens table
    op.create_table('password_reset_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_password_reset_tokens_id'), 'password_reset_tokens', ['id'], unique=False)
    op.create_index(op.f('ix_password_reset_tokens_user_id'), 'password_reset_tokens', ['user_id'], unique=False)
    op.create_index(op.f('ix_password_reset_tokens_expires_at'), 'password_reset_tokens', ['expires_at'], unique=False)

    # File uploads table
    op.create_table('file_uploads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=True),
        sa.Column('upload_purpose', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_file_uploads_id'), 'file_uploads', ['id'], unique=False)
    op.create_index(op.f('ix_file_uploads_user_id'), 'file_uploads', ['user_id'], unique=False)
    op.create_index(op.f('ix_file_uploads_upload_purpose'), 'file_uploads', ['upload_purpose'], unique=False)
    op.create_index(op.f('ix_file_uploads_created_at'), 'file_uploads', ['created_at'], unique=False)

    # Add is_verified column to users table if it doesn't exist
    try:
        op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'))
    except Exception:
        # Column might already exist
        pass


def downgrade() -> None:
    # Remove indexes and tables
    op.drop_index(op.f('ix_file_uploads_created_at'), table_name='file_uploads')
    op.drop_index(op.f('ix_file_uploads_upload_purpose'), table_name='file_uploads')
    op.drop_index(op.f('ix_file_uploads_user_id'), table_name='file_uploads')
    op.drop_index(op.f('ix_file_uploads_id'), table_name='file_uploads')
    op.drop_table('file_uploads')
    
    op.drop_index(op.f('ix_password_reset_tokens_expires_at'), table_name='password_reset_tokens')
    op.drop_index(op.f('ix_password_reset_tokens_user_id'), table_name='password_reset_tokens')
    op.drop_index(op.f('ix_password_reset_tokens_id'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    
    op.drop_index(op.f('ix_email_verification_tokens_expires_at'), table_name='email_verification_tokens')
    op.drop_index(op.f('ix_email_verification_tokens_user_id'), table_name='email_verification_tokens')
    op.drop_index(op.f('ix_email_verification_tokens_id'), table_name='email_verification_tokens')
    op.drop_table('email_verification_tokens')
    
    # Remove is_verified column
    try:
        op.drop_column('users', 'is_verified')
    except Exception:
        pass
