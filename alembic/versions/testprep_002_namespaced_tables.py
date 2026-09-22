"""Isolate UUID Test Prep tables from legacy integer study plans.

Revision ID: testprep_002
Revises: testprep_001
"""
from alembic import op
import sqlalchemy as sa

revision = "testprep_002"
down_revision = "testprep_001"
branch_labels = None
depends_on = None


def prep_tables():
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))

    def identity():
        return [sa.Column("id", sa.String(36), primary_key=True),
                sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True)]

    profile = sa.Table("test_profiles", metadata, *identity(),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("test_date", sa.Date, nullable=False),
        sa.Column("test_format", sa.String(50)),
        sa.Column("topics", sa.JSON, nullable=False),
        sa.Column("materials", sa.JSON, nullable=False),
        sa.Column("baseline_confidence", sa.Integer),
        sa.Column("daily_minutes_available", sa.Integer),
        sa.Column("study_days_per_week", sa.Integer),
        sa.Column("stress_level", sa.Integer),
        sa.Column("intake_complete", sa.Boolean, nullable=False),
        sa.Column("intake_transcript", sa.JSON, nullable=False),
        sa.Column("workflow_state", sa.JSON, nullable=False, server_default="{}"))
    plan = sa.Table("test_prep_plans", metadata, *identity(),
        sa.Column("test_profile_id", sa.String(36), sa.ForeignKey("test_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("total_sessions", sa.Integer),
        sa.Column("weekly_milestones", sa.JSON, nullable=False),
        sa.Column("generated_by_agent", sa.String(50)),
        sa.Column("generation_notes", sa.String(500)))
    session = sa.Table("test_prep_sessions", metadata, *identity(),
        sa.Column("study_plan_id", sa.String(36), sa.ForeignKey("test_prep_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime, nullable=False, index=True),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("session_type", sa.String(50), nullable=False),
        sa.Column("module_id", sa.String(36)),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("performance_score", sa.Numeric(3, 2)),
        sa.Column("user_notes", sa.String(500)),
        sa.Column("agent_notes", sa.String(500)))
    reminder = sa.Table("test_prep_reminders", metadata, *identity(),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("test_prep_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fire_at", sa.DateTime, nullable=False, index=True),
        sa.Column("reminder_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("sent_at", sa.DateTime),
        sa.Column("payload", sa.JSON, nullable=False))
    event = sa.Table("test_prep_events", metadata, *identity(),
        sa.Column("study_plan_id", sa.String(36), sa.ForeignKey("test_prep_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("reasoning", sa.String(500)),
        sa.Column("payload", sa.JSON, nullable=False))
    return profile, plan, session, reminder, event


def upgrade():
    bind = op.get_bind()
    tables = prep_tables()
    for table in tables:
        table.create(bind, checkfirst=True)
    # Preserve working UUID deployments too. Never alter/drop the older integer
    # study_plans table or its records. IDs, completion evidence and receipts stay
    # unchanged when the previous UUID tables have the matching Test Prep shape.
    legacy_names = ("study_plans", "study_plan_sessions", "session_reminders", "plan_events")
    for old_name, target in zip(legacy_names, tables[1:]):
        inspector = sa.inspect(bind)
        if not inspector.has_table(old_name):
            continue
        columns = {c["name"]: c for c in inspector.get_columns(old_name)}
        if not isinstance(columns.get("id", {}).get("type"), sa.String):
            continue
        if not set(target.c.keys()).issubset(columns):
            continue
        source = sa.Table(old_name, sa.MetaData(), autoload_with=bind)
        names = list(target.c.keys())
        missing = ~sa.exists(sa.select(target.c.id).where(target.c.id == source.c.id))
        bind.execute(target.insert().from_select(names, sa.select(*(source.c[n] for n in names)).where(missing)))


def downgrade():
    # Data-preserving downgrade: the previous generic names may belong to a
    # different product schema. Retain the additive tables and learner records.
    pass
