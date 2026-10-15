"""Study-session navigation must remain confined to the selected, owned exam."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lyo_app.coach.models import LearningGoal
from lyo_app.coach.journey_models import JourneyHandoff, LearningJourney
from lyo_app.coach.journey_schemas import JourneyContext, JourneyStart, JourneyHandoffRequest
from lyo_app.coach.journeys import start_journey, handoff, get_journey
from lyo_app.study_plans.models import StudyPlan, StudySession, TestProfile


@pytest.mark.asyncio
async def test_study_session_return_binds_exact_exam_and_user():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            for table in (LearningGoal.__table__, TestProfile.__table__, StudyPlan.__table__,
                          StudySession.__table__, LearningJourney.__table__, JourneyHandoff.__table__):
                await conn.run_sync(table.create)

        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(LearningGoal(
                id="goal-one", user_id=7, title="Chemistry exam", goal_type="test",
                status="active", subject="Chemistry", desired_outcome={}, constraints={},
                source_ref_type="test_profile", source_ref_id="exam-one",
            ))
            for pid in ("exam-one", "exam-other"):
                db.add(TestProfile(id=pid, user_id=7, subject="Chemistry",
                                   test_date=date.today() + timedelta(days=10)))
                db.add(StudyPlan(id="plan-"+pid, test_profile_id=pid, user_id=7))
                db.add(StudySession(id="session-"+pid, user_id=7, study_plan_id="plan-"+pid,
                                    topic="Molecules", session_type="practice",
                                    scheduled_at=datetime.utcnow(), duration_minutes=10))
            # Cross-account session: a guessed ID must not be accepted,
            # even when the requesting learner owns the selected exam.
            db.add(TestProfile(id="exam-foreign", user_id=8, subject="Chemistry",
                               test_date=date.today() + timedelta(days=10)))
            db.add(StudyPlan(id="plan-exam-foreign", test_profile_id="exam-foreign", user_id=8))
            db.add(StudySession(id="session-exam-foreign", user_id=8,
                                study_plan_id="plan-exam-foreign", topic="Molecules",
                                session_type="practice", scheduled_at=datetime.utcnow(),
                                duration_minutes=10))
            await db.commit()

            async def create_with_context(key, ctx):
                return await start_journey(
                    JourneyStart(request_id=key, goal_id="goal-one", origin_surface="test_prep",
                                 origin_ref="exam-one", context=ctx),
                    current_user=SimpleNamespace(id=7), db=db,
                )

            for study_id in ("session-exam-other", "session-exam-foreign", "not-a-real-session"):
                with pytest.raises(HTTPException) as error:
                    await create_with_context(
                        "attempt-" + study_id,
                        JourneyContext(test_profile_id="exam-one", study_session_id=study_id),
                    )
                assert error.value.status_code == 422

            with pytest.raises(HTTPException) as error:
                await create_with_context(
                    "missing-profile",
                    JourneyContext(study_session_id="session-exam-one"),
                )
            assert error.value.status_code == 422

            started = await create_with_context(
                "valid-session-start", JourneyContext(
                    test_profile_id="exam-one", study_session_id="session-exam-one"
                ),
            )
            assert started.context.study_session_id == "session-exam-one"
            event = await handoff(
                started.id,
                JourneyHandoffRequest(
                    request_id="to-classroom-0001",
                    expected_revision=0,
                    target_surface="classroom",
                    target_ref="molecules",
                ),
                current_user=SimpleNamespace(id=7), db=db,
            )
            assert event.context.study_session_id == "session-exam-one"

            with pytest.raises(HTTPException) as error:
                await handoff(
                    started.id,
                    JourneyHandoffRequest(
                        request_id="switch-other-session",
                        expected_revision=1,
                        target_surface="test_prep",
                        target_ref="exam-one",
                        context=JourneyContext(study_session_id="session-exam-other"),
                    ),
                    current_user=SimpleNamespace(id=7), db=db,
                )
            assert error.value.status_code == 422
            reread = await get_journey(started.id, current_user=SimpleNamespace(id=7), db=db)
            assert reread.revision == 1
            back = await handoff(
                started.id,
                JourneyHandoffRequest(request_id="back-to-same-exam",
                                      expected_revision=1, target_surface="test_prep",
                                      target_ref="exam-one"),
                current_user=SimpleNamespace(id=7), db=db,
            )
            assert back.context.test_profile_id == "exam-one"
            assert back.context.study_session_id == "session-exam-one"
    finally:
        await engine.dispose()
