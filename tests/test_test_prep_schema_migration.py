"""Exercise production's legacy-table collision without importing the app."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid
from datetime import datetime, date

import sqlalchemy as sa


class TestPrepSchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parents[1] / "alembic/versions/testprep_002_namespaced_tables.py"
        spec = importlib.util.spec_from_file_location("prep_migration", path)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.engine = sa.create_engine(os.getenv("TEST_PREP_MIGRATION_DATABASE_URL", "sqlite://"))
        self.conn = self.engine.connect()
        self.transaction = self.conn.begin()
        if self.engine.dialect.name == "postgresql":
            schema = "test_prep_check_" + uuid.uuid4().hex
            self.conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            self.conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
        else:
            self.conn.execute(sa.text("PRAGMA foreign_keys=ON"))
        self.conn.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        self.conn.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
        self.migration.op = SimpleNamespace(get_bind=lambda: self.conn)

    def tearDown(self):
        self.transaction.rollback()
        self.conn.close()
        self.engine.dispose()

    def seed_prep(self):
        profile, plan, session, reminder, event = self.migration.prep_tables()
        now = datetime(2026, 9, 22, 12)
        self.conn.execute(profile.insert().values(id="profile", user_id=1, created_at=now,
            subject="Math", test_date=date(2026, 10, 1), topics=[], materials=[],
            intake_complete=True, intake_transcript=[], workflow_state={"revision": 4}))
        self.conn.execute(plan.insert().values(id="plan", user_id=1, test_profile_id="profile",
            created_at=now, updated_at=now, status="active", version=2,
            total_sessions=1, weekly_milestones=[]))
        self.conn.execute(session.insert().values(id="session", user_id=1, study_plan_id="plan",
            scheduled_at=now, duration_minutes=20, topic="Fractions", session_type="practice",
            status="completed", completed_at=now, performance_score=0.75))
        self.conn.execute(reminder.insert().values(id="reminder", user_id=1, session_id="session",
            fire_at=now, reminder_type="thirty_min", status="sent", sent_at=now, payload={"attempts": 1}))
        self.conn.execute(event.insert().values(id="event", user_id=1, study_plan_id="plan",
            created_at=now, event_type="session_completed", payload={"receipt": "saved"}))

    def test_fresh_database_has_complete_foreign_key_chain(self):
        self.migration.upgrade()
        self.seed_prep()
        self.assertEqual(self.conn.scalar(sa.text("SELECT count(*) FROM test_prep_sessions")), 1)
        fk = sa.inspect(self.conn).get_foreign_keys("test_prep_sessions")
        self.assertIn("test_prep_plans", [f["referred_table"] for f in fk])

    def test_legacy_integer_plans_and_records_are_untouched(self):
        self.conn.execute(sa.text("CREATE TABLE study_plans (id INTEGER PRIMARY KEY, title VARCHAR(100))"))
        self.conn.execute(sa.text("INSERT INTO study_plans VALUES (7, 'Keep my original plan')"))
        self.migration.upgrade()
        self.seed_prep()
        self.migration.upgrade()
        self.assertEqual(self.conn.execute(sa.text("SELECT id, title FROM study_plans")).one(),
                         (7, "Keep my original plan"))
        self.assertEqual(self.conn.scalar(sa.text("SELECT count(*) FROM test_prep_plans")), 1)

    def test_existing_uuid_plan_and_completed_evidence_survive_once(self):
        self.migration.upgrade()
        self.seed_prep()
        old_names = ("study_plans", "study_plan_sessions", "session_reminders", "plan_events")
        tables = self.migration.prep_tables()[1:]
        for old, table in zip(old_names, tables):
            self.conn.execute(sa.text(f'CREATE TABLE "{old}" AS SELECT * FROM "{table.name}"'))
        for table in reversed(tables):
            table.drop(self.conn)
        self.migration.upgrade()
        self.migration.upgrade()
        self.assertEqual(self.conn.scalar(sa.text("SELECT count(*) FROM test_prep_sessions")), 1)
        row = self.conn.execute(sa.text("SELECT status, performance_score FROM test_prep_sessions")).one()
        self.assertEqual(row.status, "completed")
        self.assertEqual(float(row.performance_score), 0.75)
        self.assertEqual(self.conn.scalar(sa.text("SELECT status FROM test_prep_reminders")), "sent")
        self.assertEqual(self.conn.scalar(sa.text("SELECT count(*) FROM plan_events")), 1)


if __name__ == "__main__":
    unittest.main()
