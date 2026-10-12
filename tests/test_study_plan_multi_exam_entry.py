"""Multi-exam Test Prep: a new intake must never reuse or mutate an old exam."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from lyo_app.study_plans.routes import NewTestStart, prep_state, start_new_test


@pytest.mark.asyncio
async def test_start_new_test_creates_separate_profile():
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            object(),  # User row lock
            SimpleNamespace(scalar_one_or_none=lambda: None),
        ]),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    db.add.side_effect = lambda profile: setattr(profile, "id", "new-exam-id")
    result = await start_new_test(
        body=NewTestStart(request_id="test-entry-12345678"),
        current_user=SimpleNamespace(id=72),
        db=db,
    )
    assert result == {"profile_id": "new-exam-id", "created": True}
    created = db.add.call_args.args[0]
    assert created.user_id == 72
    assert created.subject == "Pending Test"
    assert created.workflow_state["start_request_id"] == "test-entry-12345678"
    assert created.intake_transcript == []
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_uses_same_profile_and_never_adds_another():
    previous = SimpleNamespace(id="existing-exam-id")
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            object(),
            SimpleNamespace(scalar_one_or_none=lambda: previous),
        ]),
        add=Mock(),
        commit=AsyncMock(),
    )
    result = await start_new_test(
        body=NewTestStart(request_id="same-request-12345"),
        current_user=SimpleNamespace(id=72),
        db=db,
    )
    assert result == {"profile_id": "existing-exam-id", "created": False}
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_selecting_a_missing_or_other_user_profile_never_falls_back_to_latest():
    with patch("lyo_app.study_plans.routes.owned_profile", new=AsyncMock(return_value=None)) as lookup:
        with pytest.raises(HTTPException) as exc:
            await prep_state(profile_id="other-account-profile",
                             current_user=SimpleNamespace(id=72), db=AsyncMock())
        assert exc.value.status_code == 404
        lookup.assert_awaited_once()
        assert lookup.await_args.args[1] == 72
        assert lookup.await_args.args[2] == "other-account-profile"


@pytest.mark.asyncio
async def test_multiple_exams_survive_switch_and_idempotent_retry(db_session):
    """Exercise real ORM persistence rather than only mocked route objects."""
    from datetime import date, datetime, timedelta, timezone
    from sqlalchemy import func, select
    from lyo_app.auth.models import User
    from lyo_app.study_plans.models import TestProfile, StudyPlan, StudySession
    from lyo_app.study_plans.routes import list_test_profiles

    user = User(email="multiple-exams@example.test", username="multiple-exams", hashed_password="unused")
    other = User(email="other-exams@example.test", username="other-exams", hashed_password="unused")
    db_session.add_all([user, other])
    await db_session.flush()
    old = TestProfile(
        user_id=user.id, subject="Algebra", test_date=date.today() + timedelta(days=14),
        intake_complete=True, workflow_state={"timezone": "UTC", "revision": 0},
    )
    foreign = TestProfile(
        user_id=other.id, subject="Private Biology", test_date=date.today() + timedelta(days=14),
        workflow_state={"timezone": "UTC"},
    )
    db_session.add_all([old, foreign])
    await db_session.flush()
    plan = StudyPlan(user_id=user.id, test_profile_id=old.id)
    db_session.add(plan)
    await db_session.flush()
    session = StudySession(
        study_plan_id=plan.id, user_id=user.id,
        scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        duration_minutes=25, topic="Linear equations", session_type="practice",
        status="completed", performance_score=0.8,
    )
    db_session.add(session)
    await db_session.commit()

    request = NewTestStart(request_id="separate-exam-12345678")
    first = await start_new_test(body=request, current_user=user, db=db_session)
    retry = await start_new_test(body=request, current_user=user, db=db_session)
    assert first["created"] and first["profile_id"] != old.id
    assert retry == {"profile_id": first["profile_id"], "created": False}
    assert await db_session.scalar(
        select(func.count()).select_from(TestProfile).where(TestProfile.user_id == user.id)
    ) == 2

    fresh_state = await prep_state(current_user=user, db=db_session, profile_id=first["profile_id"])
    assert fresh_state["profile"].id == first["profile_id"]
    assert fresh_state["plan"] is None and fresh_state["sessions"] == []

    old_state = await prep_state(current_user=user, db=db_session, profile_id=old.id)
    assert old_state["profile"].subject == "Algebra"
    assert old_state["plan"].id == plan.id
    assert [row.id for row in old_state["sessions"]] == [session.id]
    assert old_state["sessions"][0].status == "completed"
    assert float(old_state["sessions"][0].performance_score) == 0.8
    assert (await list_test_profiles(current_user=user, db=db_session))[0].id == first["profile_id"]

    with pytest.raises(HTTPException) as exc:
        await prep_state(current_user=user, db=db_session, profile_id=foreign.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "archived"])
async def test_selected_history_exposes_saved_work_without_reactivating_it(db_session, status):
    from datetime import date, datetime, timedelta
    from lyo_app.auth.models import User
    from lyo_app.study_plans.models import TestProfile, StudyPlan, StudySession
    from lyo_app.study_plans.routes import profile_plan

    user = User(email="history@example.test", username="history", hashed_password="unused")
    db_session.add(user)
    await db_session.flush()
    profile = TestProfile(user_id=user.id, subject="Algebra", test_date=date.today() - timedelta(days=1),
                          intake_complete=True)
    db_session.add(profile)
    await db_session.flush()
    plan = StudyPlan(user_id=user.id, test_profile_id=profile.id, status=status)
    db_session.add(plan)
    await db_session.flush()
    session = StudySession(user_id=user.id, study_plan_id=plan.id, scheduled_at=datetime.utcnow(),
                           topic="Equations", duration_minutes=20, session_type="practice",
                           status="completed", performance_score=0.75)
    db_session.add(session)
    await db_session.commit()

    selected = await prep_state(user, db_session, profile.id)
    assert selected["plan"].id == plan.id and selected["plan"].status == status
    assert selected["sessions"][0].id == session.id
    assert float(selected["sessions"][0].performance_score) == 0.75
    # Legacy intake/generation helpers must not mistake history for an active plan.
    assert await profile_plan(db_session, user.id, profile.id) is None
    assert (await prep_state(user, db_session))["plan"] is None
    await db_session.refresh(plan)
    assert plan.status == status


@pytest.mark.asyncio
async def test_explicit_selection_prefers_resumable_plan_over_newer_history(db_session):
    from datetime import date, datetime, timedelta
    from lyo_app.auth.models import User
    from lyo_app.study_plans.models import TestProfile, StudyPlan

    user = User(email="active-history@example.test", username="active-history", hashed_password="unused")
    db_session.add(user)
    await db_session.flush()
    profile = TestProfile(user_id=user.id, subject="Algebra", test_date=date.today())
    db_session.add(profile)
    await db_session.flush()
    active = StudyPlan(user_id=user.id, test_profile_id=profile.id, status="paused",
                       created_at=datetime.utcnow() - timedelta(days=1))
    archived = StudyPlan(user_id=user.id, test_profile_id=profile.id, status="archived")
    db_session.add_all([active, archived])
    await db_session.commit()
    assert (await prep_state(user, db_session, profile.id))["plan"].id == active.id


@pytest.mark.asyncio
async def test_authenticated_multi_exam_http_contract(async_client, auth_headers, second_auth_headers):
    endpoint = "/api/v1/me/study_plans"
    start = await async_client.post(endpoint + "/profiles/start", headers=auth_headers,
                                   json={"request_id": "http-exam-12345678"})
    assert start.status_code == 201, start.text
    selected_id = start.json()["profile_id"]
    retry = await async_client.post(endpoint + "/profiles/start", headers=auth_headers,
                                   json={"request_id": "http-exam-12345678"})
    assert retry.status_code == 201
    assert retry.json() == {"profile_id": selected_id, "created": False}
    selected = await async_client.get(endpoint + "/state", headers=auth_headers,
                                      params={"profile_id": selected_id})
    assert selected.status_code == 200 and selected.json()["profile"]["id"] == selected_id
    profiles = await async_client.get(endpoint + "/profiles", headers=auth_headers)
    assert [p["id"] for p in profiles.json()] == [selected_id]
    foreign = await async_client.get(endpoint + "/state", headers=second_auth_headers,
                                     params={"profile_id": selected_id})
    assert foreign.status_code == 404
    other_profiles = await async_client.get(endpoint + "/profiles", headers=second_auth_headers)
    assert other_profiles.json() == []
    missing = await async_client.get(endpoint + "/state", headers=auth_headers,
                                     params={"profile_id": "missing-exam"})
    assert missing.status_code == 404
    invalid = await async_client.post(endpoint + "/profiles/start", headers=auth_headers,
                                     json={"request_id": "short"})
    assert invalid.status_code == 422
    anonymous = await async_client.get(endpoint + "/profiles")
    assert anonymous.status_code in (401, 403)
