"""Add private_lessons, bookings, reviews tables

Revision ID: booking_review_001
Revises: community_feed_001
Create Date: 2025-02-09 20:44:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "booking_review_001"
down_revision = "community_feed_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- private_lessons --
    op.create_table(
        "private_lessons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(200), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(100), nullable=False, index=True),
        sa.Column("price_per_hour", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("instructor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # -- bookings --
    booking_status = sa.Enum("pending", "confirmed", "cancelled", "completed", name="bookingstatus")
    booking_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("status", booking_status, nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("slot_start", sa.DateTime(), nullable=False, index=True),
        sa.Column("slot_end", sa.DateTime(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("private_lessons.id"), nullable=False, index=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # -- reviews --
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("target_type", sa.String(50), nullable=False, index=True),
        sa.Column("target_id", sa.String(50), nullable=False, index=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("bookings")
    sa.Enum(name="bookingstatus").drop(op.get_bind(), checkfirst=True)
    op.drop_table("private_lessons")
