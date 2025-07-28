"""Create educational resources tables

Revision ID: 003_educational_resources
Revises: 002_email_file_tables
Create Date: 2025-07-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers
revision = '003_educational_resources'
down_revision = '002_email_file_tables'
branch_labels = None
depends_on = None

def upgrade():
    """Create educational resources tables"""
    
    # Create educational_resources table
    op.create_table(
        'educational_resources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('author', sa.String(length=200), nullable=True),
        sa.Column('publisher', sa.String(length=200), nullable=True),
        sa.Column('resource_type', sa.Enum('ebook', 'video', 'podcast', 'course', 'article', 'document', name='resourcetype'), nullable=False),
        sa.Column('provider', sa.Enum('youtube', 'khan_academy', 'mit_ocw', 'coursera', 'edx', 'internet_archive', 'project_gutenberg', 'open_library', 'google_books', 'openstax', 'spotify', 'ted', 'vimeo', 'listen_notes', 'custom', name='resourceprovider'), nullable=False),
        sa.Column('subject_area', sa.String(length=100), nullable=True),
        sa.Column('difficulty_level', sa.String(length=50), nullable=True),
        sa.Column('external_id', sa.String(length=200), nullable=True),
        sa.Column('external_url', sa.String(length=1000), nullable=False),
        sa.Column('thumbnail_url', sa.String(length=1000), nullable=True),
        sa.Column('download_url', sa.String(length=1000), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('isbn', sa.String(length=20), nullable=True),
        sa.Column('quality_score', sa.Integer(), nullable=True),
        sa.Column('is_curated', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('raw_api_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_verified', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_educational_resources_id', 'educational_resources', ['id'])
    op.create_index('ix_educational_resources_title', 'educational_resources', ['title'])
    op.create_index('ix_educational_resources_resource_type', 'educational_resources', ['resource_type'])
    op.create_index('ix_educational_resources_provider', 'educational_resources', ['provider'])
    op.create_index('ix_educational_resources_subject_area', 'educational_resources', ['subject_area'])
    op.create_index('ix_educational_resources_external_id', 'educational_resources', ['external_id'])
    
    # Create resource_tags table
    op.create_table(
        'resource_tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('tag', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['resource_id'], ['educational_resources.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create index for tags
    op.create_index('ix_resource_tags_tag', 'resource_tags', ['tag'])
    
    # Create course_resources table
    op.create_table(
        'course_resources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('resource_order', sa.Integer(), nullable=True),
        sa.Column('is_required', sa.Boolean(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['resource_id'], ['educational_resources.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create resource_collections table
    op.create_table(
        'resource_collections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    """Drop educational resources tables"""
    op.drop_table('resource_collections')
    op.drop_table('course_resources')
    op.drop_index('ix_resource_tags_tag', table_name='resource_tags')
    op.drop_table('resource_tags')
    op.drop_index('ix_educational_resources_external_id', table_name='educational_resources')
    op.drop_index('ix_educational_resources_subject_area', table_name='educational_resources')
    op.drop_index('ix_educational_resources_provider', table_name='educational_resources')
    op.drop_index('ix_educational_resources_resource_type', table_name='educational_resources')
    op.drop_index('ix_educational_resources_title', table_name='educational_resources')
    op.drop_index('ix_educational_resources_id', table_name='educational_resources')
    op.drop_table('educational_resources')
