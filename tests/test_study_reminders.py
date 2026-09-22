"""A provider failure must never be recorded as a delivered reminder."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from lyo_app.study_plans.models import TestProfile as Profile, StudyPlan, StudySession, SessionReminder
from lyo_app.auth.models import User


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted,expected", [(1, "sent"), (0, "pending")])
async def test_reminder_state_requires_provider_acceptance(db_session, monkeypatch, accepted, expected):
    from lyo_app.workers import reminder_worker as worker
    user = User(email="reminder@example.test", username="reminder", hashed_password="unused")
    db_session.add(user); await db_session.flush()
    profile = Profile(user_id=user.id, subject="Math", test_date=datetime.utcnow().date() + timedelta(days=5))
    db_session.add(profile); await db_session.flush()
    plan = StudyPlan(user_id=user.id, test_profile_id=profile.id)
    db_session.add(plan); await db_session.flush()
    session = StudySession(user_id=user.id, study_plan_id=plan.id, topic="Fractions", duration_minutes=15,
        scheduled_at=datetime.utcnow() + timedelta(minutes=20), session_type="learn")
    db_session.add(session); await db_session.flush()
    reminder = SessionReminder(user_id=user.id, session_id=session.id, fire_at=datetime.utcnow() - timedelta(minutes=1), reminder_type="thirty_min")
    db_session.add(reminder); await db_session.commit()

    @asynccontextmanager
    async def session_factory():
        yield db_session

    monkeypatch.setattr(worker, "AsyncSessionLocal", session_factory)
    send = AsyncMock(return_value=accepted)
    monkeypatch.setattr(worker.push_service, "send_to_user", send)
    await worker.fire_due_reminders()
    assert reminder.status == expected
    assert (reminder.sent_at is not None) == (accepted > 0)
    if not accepted:
        await worker.fire_due_reminders()
        await worker.fire_due_reminders()
        assert reminder.status == "failed" and reminder.sent_at is None
    else:
        await worker.fire_due_reminders()
        assert send.await_count == 1


@pytest.mark.asyncio
async def test_unconfigured_apns_is_not_success(monkeypatch):
    from lyo_app.services.push_notifications import push_service, PushNotification
    for key in ("APNS_PRIVATE_KEY", "APNS_KEY_FILE", "APNS_KEY_PATH", "APNS_KEY_ID", "APNS_TEAM_ID"):
        monkeypatch.delenv(key, raising=False)
    assert not await push_service.send_notification("test-device", PushNotification("Test", "Test"), "ios")
