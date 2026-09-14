"""Drive one learner through the loop, against the real app.

WHY THIS EXISTS

Everything else in this effort is proven by unit and integration tests. That
is not the same as the thing working. A learner answering a question in Chat
and the Classroom then knowing about it crosses the check endpoint, the event
processor, two projections, two mastery tables and three read endpoints — and
a test for each of those can pass while the chain between them does not.

So this boots the real FastAPI application over a real database, registers a
real learner, and walks them through:

    answer a check  ->  evidence recorded  ->  concept summary reflects it
                                           ->  recommendations reflect it
                                           ->  the classroom's mastery table
                                               has the row it teaches from

and checks, on the way out, that the answer key never appears in anything the
learner's client can see.

Run:  python scripts/e2e_learner_loop.py
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Runnable as `python scripts/e2e_learner_loop.py` from the repo root without
# PYTHONPATH set, which is how anyone reaching for it will actually run it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./e2e_learner_loop.db")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "e2e-secret-key-at-least-32-characters-long-ok")

FAILURES = []
CHECKS = []


def check(label, condition, detail=""):
    CHECKS.append(label)
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")
        FAILURES.append(label)


async def main() -> int:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from lyo_app.ai.lesson_composer import ChatLesson, CheckOption, CheckItem, LessonSection, SectionKind
    from lyo_app.api.v1.stream_lyo2 import _lesson_to_smart_blocks
    from lyo_app.core.database import Base, get_db
    from lyo_app.enhanced_main import app

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()

    async def _override_db():
        yield session

    # `app` is a module-level singleton shared with every other test in the
    # suite. An override left in place hands them this script's session, which
    # is closed by the time they run — so it is restored in the `finally`
    # below rather than merely set. Leaving it set made four unrelated auth
    # tests fail the first time this ran.
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_db

    # Everything from here is inside the guard. The first version of this
    # started the `try` only at the walk itself, so an exception while
    # building the learner, the lesson or the conversation still leaked the
    # override — the same suite poisoning it was written to stop, just moved
    # a few lines earlier.
    try:
        return await _prepare_and_walk(app, session)
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        await session.close()
        await engine.dispose()


async def _prepare_and_walk(app, session):
    """Build the fixtures and walk the loop, with the override already guarded."""
    import uuid

    from lyo_app.ai.lesson_composer import (
        ChatLesson,
        CheckItem,
        CheckOption,
        LessonSection,
        SectionKind,
    )
    from lyo_app.api.v1.stream_lyo2 import _lesson_to_smart_blocks

    # ── a real learner ───────────────────────────────────────────────────────
    from lyo_app.models.enhanced import User

    learner = User(
        email=f"e2e-{uuid.uuid4().hex[:8]}@example.com",
        username=f"e2e{uuid.uuid4().hex[:8]}",
        hashed_password="x" * 20,
        is_active=True,
        is_verified=True,
    )
    session.add(learner)
    await session.flush()

    from lyo_app.auth.jwt_auth import create_access_token

    token = create_access_token(str(learner.id))
    headers = {"Authorization": f"Bearer {token}", "X-API-Key": os.environ.get("API_KEY", "")}

    # ── a real lesson with a gradeable check ─────────────────────────────────
    lesson = ChatLesson(
        skill_id="compare_fractions",
        topic="Compare fractions",
        sections=[
            LessonSection(
                kind=SectionKind.core,
                text="A common denominator lets you compare fractions directly.",
            )
        ],
        check=CheckItem(
            question="Which is larger?",
            options=[
                CheckOption(text="1/2"),
                CheckOption(text="1/3", reveals="bigger_denominator_is_bigger"),
            ],
            correct_index=0,
            explanation="Halves are bigger pieces than thirds.",
            hint="Think about the size of one piece.",
        ),
    )
    blocks = _lesson_to_smart_blocks(lesson, source_surface="chat")
    check_block = next(b for b in blocks if b.get("type") == "quiz")

    from lyo_app.chat.models import ChatConversation, ChatMessage

    conversation = ChatConversation(
        id=str(uuid.uuid4()),
        user_id=str(learner.id),
        session_id=f"e2e-{uuid.uuid4().hex[:8]}",
        topic="Compare fractions",
    )
    session.add(conversation)
    await session.flush()
    message = ChatMessage(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        role="assistant",
        content=lesson.to_plain_text(),
        mode_used="general",
        blocks=blocks,
    )
    session.add(message)
    await session.commit()

    return await _walk_the_loop(app, session, learner, conversation, check_block, lesson)


async def _walk_the_loop(app, session, learner, conversation, check_block, lesson):
    """The journey itself, so the caller can guarantee cleanup around it."""
    import os
    import uuid

    from datetime import datetime, timedelta

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from lyo_app.api.v1.stream_lyo2 import _lesson_to_smart_blocks
    from lyo_app.auth.jwt_auth import create_access_token
    from lyo_app.chat.models import ChatMessage

    token = create_access_token(str(learner.id))
    headers = {"Authorization": f"Bearer {token}", "X-API-Key": os.environ.get("API_KEY", "")}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://e2e") as client:
        print("\n1. The learner answers a check")
        response = await client.post(
            "/api/v1/lyo2/chat/check",
            headers=headers,
            json={
                "conversation_id": conversation.id,
                "block_id": check_block["id"],
                "selected_index": 0,
                "time_taken_ms": 4200,
                "hint_used": False,
            },
        )
        check("the check endpoint answers", response.status_code == 200,
              f"status {response.status_code}: {response.text[:200]}")
        if response.status_code != 200:
            return 1
        verdict = response.json()
        check("the server graded it correct", verdict.get("correct") is True)
        check("the verdict names the right option", verdict.get("correct_index") == 0)

        print("\n2. A wrong answer is graded wrong, by the server")
        message2 = ChatMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            role="assistant",
            content="second",
            mode_used="general",
            blocks=_lesson_to_smart_blocks(lesson, source_surface="chat"),
        )
        session.add(message2)
        await session.commit()
        wrong_block = next(b for b in message2.blocks if b.get("type") == "quiz")
        wrong = await client.post(
            "/api/v1/lyo2/chat/check",
            headers=headers,
            json={
                "conversation_id": conversation.id,
                "block_id": wrong_block["id"],
                "selected_index": 1,
            },
        )
        check("a wrong answer is refused", wrong.json().get("correct") is False)
        check(
            "the misconception behind it is named",
            wrong.json().get("misconception") == "bigger_denominator_is_bigger",
        )

        print("\n3. The evidence reached the learner's record")
        from lyo_app.events.models import LearningEvent

        events = (
            await session.execute(
                select(LearningEvent).where(LearningEvent.user_id == learner.id)
            )
        ).scalars().all()
        check("a learning event was written", len(events) >= 1, f"found {len(events)}")
        if events:
            check(
                "it names the concept the way chat keys it",
                any(e.concept_id == "compare_fractions" for e in events),
                f"got {[e.concept_id for e in events]}",
            )
            check(
                "it carries a rung",
                any(e.evidence_type for e in events),
                f"got {[e.evidence_type for e in events]}",
            )
            check(
                "it does not ask for a second mastery update",
                all(not e.skill_ids_json for e in events),
            )

        print("\n4. The table the Classroom teaches from has the row")
        from lyo_app.ai_classroom.models import MasteryState

        states = (
            await session.execute(
                select(MasteryState).where(MasteryState.user_id == str(learner.id))
            )
        ).scalars().all()
        check("the classroom's mastery table was filled", len(states) >= 1,
              f"found {len(states)}")
        if states:
            check(
                "keyed by the same concept name",
                any(
                    (s.objective_id or s.concept_id) == "compare_fractions"
                    for s in states
                ),
                f"got {[(s.concept_id, s.objective_id) for s in states]}",
            )

        print("\n5. What the learner is told about themselves")
        summary = await client.get(
            "/api/v1/personalization/concepts/summary", headers=headers
        )
        check("the concept summary answers", summary.status_code == 200,
              f"status {summary.status_code}: {summary.text[:200]}")
        if summary.status_code == 200:
            body = summary.json()
            check("it counts the concept they met", body.get("total", 0) >= 1, str(body))
            check(
                "one correct multiple choice is not 'mastered'",
                body.get("mastered", 0) == 0,
                str(body),
            )

        # Answering a check schedules the concept for tomorrow, so a
        # recommendation list read right now is legitimately empty — and
        # `all([])` is True, so the original version of this check passed
        # whether or not recommendations worked at all. Backdate the schedule
        # to put the learner in the state the endpoint exists to serve.
        from lyo_app.personalization.models import SpacedRepetitionSchedule

        schedules = (
            await session.execute(
                select(SpacedRepetitionSchedule).where(
                    SpacedRepetitionSchedule.user_id == learner.id
                )
            )
        ).scalars().all()
        check("answering the check scheduled a review", len(schedules) >= 1,
              f"found {len(schedules)}")
        for schedule in schedules:
            schedule.next_review = datetime.utcnow() - timedelta(days=2)
        await session.commit()

        recommendations = await client.get(
            "/api/v1/personalization/recommendations", headers=headers
        )
        check("recommendations answer", recommendations.status_code == 200,
              f"status {recommendations.status_code}: {recommendations.text[:200]}")
        if recommendations.status_code == 200:
            items = recommendations.json().get("items", [])
            check("the overdue concept is recommended back", len(items) >= 1, str(items))
            check(
                "every recommendation says why it is there",
                items and all(item.get("detail") for item in items),
                str(items),
            )
            check(
                "it is the concept they actually worked on",
                any(item.get("concept_id") == "compare_fractions" for item in items),
                str(items),
            )

        print("\n6. The answer key never leaves the server")
        history = await client.get(
            f"/api/v1/chat/conversations/{conversation.id}", headers=headers
        )
        if history.status_code == 200:
            raw = history.text
            check("no correct_index in the reloaded conversation's blocks",
                  '"correct_index"' not in raw.split('"result"')[0])
            check("no misconception tag on the options", "bigger_denominator_is_bigger"
                  not in raw.split('"result"')[0])
        else:
            print(f"  skip conversation reload (status {history.status_code})")

        print("\n7. The study plan sees the same learner")
        # Phase E: a plan used to keep its own opinion of a learner, averaged
        # from scores their own device had reported. It should now be reading
        # the record the rest of this walk just filled in.
        from lyo_app.study_plans.models import StudyPlan, StudySession, TestProfile

        profile = TestProfile(
            user_id=learner.id,
            subject="Maths",
            test_date=(datetime.utcnow() + timedelta(days=14)).date(),
            topics=[
                {"name": "Compare fractions", "weight": 3},
                {"name": "Long division", "weight": 1},
            ],
        )
        session.add(profile)
        await session.flush()
        plan = StudyPlan(test_profile_id=profile.id, user_id=learner.id)
        session.add(plan)
        await session.flush()
        study_session = StudySession(
            study_plan_id=plan.id,
            user_id=learner.id,
            # Deliberately in the future: this learner did the work early and
            # is ticking the session off ahead of its slot, which is an
            # ordinary thing to do and which an earlier version of the window
            # turned into `[slot, now]` — inverted, matching nothing, and
            # reporting someone who had just proved the topic as unmeasured.
            scheduled_at=datetime.utcnow() + timedelta(hours=2),
            duration_minutes=45,
            topic="Compare fractions",
            session_type="practice",
        )
        session.add(study_session)
        await session.commit()

        readiness = await client.get(
            f"/api/v1/me/study_plans/plans/{plan.id}/readiness", headers=headers
        )
        check("readiness answers", readiness.status_code == 200,
              f"status {readiness.status_code}: {readiness.text[:200]}")
        if readiness.status_code == 200:
            body = readiness.json()
            check("it counts both topics of the test", body.get("topics_total") == 2, str(body))
            check(
                "only the topic they worked on has been assessed",
                body.get("topics_assessed") == 1,
                str(body),
            )
            check(
                "readiness is somewhere between nothing and everything",
                isinstance(body.get("readiness"), float)
                and 0.0 < body["readiness"] < 1.0,
                str(body.get("readiness")),
            )
            check("it knows how long they have", body.get("days_remaining") == 14, str(body))
            untouched = [t for t in body.get("topics", []) if t["mastery"] is None]
            check(
                "the untouched topic reports no mastery rather than zero",
                len(untouched) == 1 and untouched[0]["topic"] == "Long division",
                str(body.get("topics")),
            )
            check(
                "it sends them to the topic they have not opened",
                body.get("focus_next", [None])[0] == "Long division",
                str(body.get("focus_next")),
            )

        completed = await client.post(
            f"/api/v1/me/study_plans/sessions/{study_session.id}/complete"
            "?performance_score=1.0",
            headers=headers,
        )
        check("completing a session answers", completed.status_code == 200,
              f"status {completed.status_code}: {completed.text[:200]}")
        if completed.status_code == 200:
            body = completed.json()
            check(
                "the score came from the graded answer, not the query string",
                body.get("graded", 0) >= 1,
                str(body),
            )
            # The request above declared 1.0. The learner answered one
            # multiple-choice question correctly, which the ladder scores as
            # recognition — worth something, but not full marks.
            check(
                "the client's declared 1.0 was not stored",
                body.get("performance_score") is not None
                and body["performance_score"] < 1.0,
                str(body),
            )

        stats = await client.get(
            f"/api/v1/me/study_plans/plans/{plan.id}/stats", headers=headers
        )
        check("plan stats answer", stats.status_code == 200,
              f"status {stats.status_code}: {stats.text[:200]}")
        if stats.status_code == 200:
            by_topic = stats.json().get("mastery_by_topic", {})
            check(
                "the plan reports the concept from the learner's record",
                "Compare fractions" in by_topic,
                str(by_topic),
            )
            check(
                "and says nothing about the topic they never opened",
                "Long division" not in by_topic,
                str(by_topic),
            )

        print("\n8. A Classroom session on a planned topic reaches that plan")
        # The link Test Prep exists to make: tap a scheduled session, get
        # taught, and have the plan know. Section 7 proved a *Chat* answer
        # reaches readiness; this is the Classroom's own grading, which took a
        # different route to the learner's record and, until this change, a
        # different name for the concept once it got there.
        #
        # "Long division" is deliberately the topic section 7 just asserted was
        # untouched, so the only thing that can make it assessed is this.
        from unittest.mock import AsyncMock, patch

        from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
        from lyo_app.ai_classroom.adaptive_teaching import (
            GuidedState, LearningPlan, LearningUnit, LearningTask, PendingTask,
            TaskOption,
        )
        from lyo_app.ai_classroom.scene_lifecycle_engine import (
            ContextSnapshot,
            SceneLifecycleEngine,
            Trigger,
            TriggerType,
            _SESSION_PROGRESS,
            session_progress_key,
        )
        from lyo_app.ai_classroom.sdui_models import ActionIntent

        planned_topic = "Long division"
        engine = SceneLifecycleEngine(session)
        # The only stub in this step. Assembling a real context would need an
        # authored course behind the session, which is not what this is about;
        # everything downstream of here — grading, the evidence outbox, the
        # projections and the readiness endpoint — runs for real.
        #
        # `topic` is what the adaptive session files evidence under, and it is
        # deliberately not the objective: slugified, "Practise and apply Long
        # division" reads `practise_and_apply_long_division`, the pseudo-concept
        # this walk exists to keep out of the learner's record.
        ctx = ContextSnapshot(
            user_id=str(learner.id),
            session_id="e2e-classroom",
            topic=planned_topic,
            learning_objective=f"Practise and apply {planned_topic}",
        )
        engine.context_assembler.assemble_context = AsyncMock(return_value=ctx)

        # Seed the checkpoint the learner is about to answer. Recognition —
        # picking the right quotient from prepared candidates — is deliberately
        # the weakest positive rung, so this also pins that the product records
        # it as recognition rather than inflating it.
        pending = PendingTask(
            task=LearningTask(
                kind="choose",
                scenario="A baker splits 144 rolls evenly between 12 identical boxes.",
                question="How many rolls go in each box?",
                response_hint="Pick the number per box.",
                criteria=["Divides 144 by 12 correctly"],
                example_answer="12 rolls per box.",
                options=[
                    TaskOption(id="a", label="12 rolls", correct=True,
                               feedback="144 split 12 ways leaves 12 in each box."),
                    TaskOption(id="b", label="14 rolls", correct=False,
                               misconception="Reads the digits rather than dividing.",
                               feedback="That takes the digits of 144 rather than dividing it."),
                ],
            ),
            speech="Splitting a total evenly is division.",
            board_title="Sharing a total evenly",
            board_content="144 rolls shared between 12 boxes is 144 \u00f7 12.",
        )
        seeded = GuidedState(
            owner=ctx.user_id,
            plan=LearningPlan(units=[
                LearningUnit(title="Divide by a two-digit number",
                             objective="Share a total evenly between equal groups.",
                             material="Splitting 144 rolls between 12 boxes gives 12 rolls per box."),
                LearningUnit(title="Interpret a remainder",
                             objective="Say what is left over once equal groups are filled.",
                             material="Sharing 145 rolls between 12 boxes fills each box and leaves one over."),
            ]),
            pending=pending,
            remaining_units=[1],
        )
        key = session_progress_key(ctx.user_id, ctx.session_id)
        progress = {}
        AdaptiveSession(None).save(progress, seeded, AdaptiveSession(None).checkpoint(ctx, seeded))
        _SESSION_PROGRESS[key] = progress

        # DKT is the one collaborator held back: it is exercised by its own
        # tests, and its absence must not be what makes this step pass.
        personalization = AsyncMock()
        with patch("lyo_app.personalization.service.PersonalizationEngine", personalization):
            await engine.process_trigger(Trigger(
                trigger_type=TriggerType.USER_ACTION,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                component_id=pending.id,
                action_data={
                    "action_intent": ActionIntent.SUBMIT_ANSWER,
                    "answer_data": {"selected_option_id": "a"},
                    "response_time_ms": 5000,
                },
            ))
        _SESSION_PROGRESS.pop(key, None)
        await session.commit()

        after = await client.get(
            f"/api/v1/me/study_plans/plans/{plan.id}/readiness", headers=headers
        )
        check("readiness still answers after a classroom session",
              after.status_code == 200,
              f"status {after.status_code}: {after.text[:200]}")
        if after.status_code == 200:
            body = after.json()
            check(
                "the classroom's work reached the plan",
                body.get("topics_assessed") == 2,
                str(body),
            )
            taught = [t for t in body.get("topics", []) if t["topic"] == planned_topic]
            check(
                "the topic they were just taught now reports mastery",
                len(taught) == 1 and taught[0]["mastery"] is not None,
                str(body.get("topics")),
            )
            check(
                "and it is filed under the concept the plan names",
                len(taught) == 1 and taught[0]["concept_id"] == "long_division",
                str(taught),
            )
            check(
                "one right multiple-choice pick does not retire the topic",
                # `focus_next` is "what is most worth your next hour", not
                # "what you have not touched" — so a topic stays on it while
                # the learner is still weak at it. This walk first asserted
                # the opposite, which would have had the plan declare someone
                # done with long division on the strength of one recognition
                # answer. That is the fabrication this whole effort is against,
                # pointed the other way.
                planned_topic in body.get("focus_next", []),
                str(body.get("focus_next")),
            )
            check(
                "recognition moved mastery without claiming mastery",
                len(taught) == 1
                and 0.0 < (taught[0]["mastery"] or 0.0) < 0.75,
                str(taught),
            )

    print(f"\n{len(CHECKS) - len(FAILURES)}/{len(CHECKS)} checks passed")
    if FAILURES:
        print("FAILED:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
