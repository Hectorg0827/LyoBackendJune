"""A provider failure must never be recorded as a delivered reminder."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from lyo_app.study_plans.models import TestProfile as Profile, StudyPlan, StudySession, SessionReminder
from lyo_app.auth.models import User


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted,expected", [(1, "sent"), (0, "pending"), (1, "cancelled")])
async def test_reminder_state_requires_provider_acceptance(db_session, monkeypatch, accepted, expected):
    from lyo_app.workers import reminder_worker as worker
    user = User(email="reminder@example.test", username="reminder", hashed_password="unused")
    if expected == "cancelled":
        user.learning_profile = {"notification_preferences": {"course_reminders": False}}
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
    assert (reminder.sent_at is not None) == (expected == "sent")
    if expected == "cancelled":
        assert send.await_count == 0
    elif not accepted:
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


@pytest.mark.asyncio
async def test_registration_persists_model_fields_and_switches_account(db_session):
    from lyo_app.api.v1 import push
    from lyo_app.models.enhanced import PushDevice
    from sqlalchemy import select
    first = User(email="first@example.test", username="first", hashed_password="unused")
    second = User(email="second@example.test", username="second", hashed_password="unused")
    db_session.add_all([first, second]); await db_session.commit()
    request = push.DeviceRegistrationRequest(device_token="same-physical-device", device_type="android")
    registered = await push.register_device(request, first, db_session)
    repeated = await push.register_device(request, first, db_session)
    assert registered.id == repeated.id and registered.device_type == "android"
    assert registered.registered_at
    switched = await push.register_device(request, second, db_session)
    devices = (await db_session.execute(select(PushDevice))).scalars().all()
    assert len(devices) == 2
    assert [d.user_id for d in devices if d.is_active] == [second.id]
    await push.unregister_device(int(switched.id), second, db_session)
    assert not any(d.is_active for d in devices)


@pytest.mark.asyncio
async def test_test_push_cannot_report_unaccepted_delivery(db_session, monkeypatch):
    from lyo_app.api.v1 import push
    from fastapi import HTTPException
    user = User(email="testpush@example.test", username="testpush", hashed_password="unused")
    db_session.add(user); await db_session.commit()
    await push.register_device(push.DeviceRegistrationRequest(device_token="test-device", device_type="ios"), user, db_session)
    monkeypatch.setattr(push.push_service, "send_to_user", AsyncMock(return_value=0))
    with pytest.raises(HTTPException) as rejected:
        await push.send_test_notification(push.PushNotificationRequest(title="Test", body="Test"), user, db_session)
    assert rejected.value.status_code == 503


@pytest.mark.asyncio
async def test_reminder_preferences_persist_on_user(db_session):
    from lyo_app.api.v1 import push
    user = User(email="prefs@example.test", username="prefs", hashed_password="unused")
    db_session.add(user); await db_session.commit()
    await push.update_notification_preferences(push.NotificationPreferencesRequest(course_reminders=False), user, db_session)
    await db_session.refresh(user)
    saved = await push.get_notification_preferences(user)
    assert saved.course_reminders is False


def test_quiet_hours_cross_midnight_in_saved_timezone():
    from lyo_app.study_plans.workflow import quiet_until
    preferences = {"quiet_hours_start": "22:00", "quiet_hours_end": "07:00", "timezone": "America/New_York"}
    assert quiet_until(datetime(2026, 9, 22, 3), preferences) == datetime(2026, 9, 22, 11)
    assert quiet_until(datetime(2026, 9, 22, 15), preferences) is None
