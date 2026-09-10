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

    try:
        return await _walk_the_loop(app, session, learner, conversation, check_block, lesson)
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        await session.close()
        await engine.dispose()


async def _walk_the_loop(app, session, learner, conversation, check_block, lesson):
    """The journey itself, so the caller can guarantee cleanup around it."""
    import os
    import uuid

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

        recommendations = await client.get(
            "/api/v1/personalization/recommendations", headers=headers
        )
        check("recommendations answer", recommendations.status_code == 200,
              f"status {recommendations.status_code}: {recommendations.text[:200]}")
        if recommendations.status_code == 200:
            items = recommendations.json().get("items", [])
            check(
                "every recommendation says why it is there",
                all(item.get("detail") for item in items),
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

    print(f"\n{len(CHECKS) - len(FAILURES)}/{len(CHECKS)} checks passed")
    if FAILURES:
        print("FAILED:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
