"""
Account-deletion (GDPR / App Store 5.1.1(v)) tests.

Verifies that anonymizing an account scrubs personal data, blocks login, and
revokes sessions without raising foreign-key violations from other users'
rows that reference the deleted user's content.
"""

import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long-xx")

import datetime
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Import the model modules so the shared declarative registry is fully
# populated before init_db() / create_all().
_MODEL_MODULES = [
    "lyo_app.models.enhanced", "lyo_app.models.social", "lyo_app.models.clips",
    "lyo_app.auth.models", "lyo_app.auth.rbac", "lyo_app.feeds.models",
    "lyo_app.community.models", "lyo_app.learning.models", "lyo_app.ai_study.models",
    "lyo_app.ai_agents.models", "lyo_app.gamification.models", "lyo_app.classroom.models",
    "lyo_app.tenants.models", "lyo_app.stack.models", "lyo_app.chat.models",
    "lyo_app.personalization.models", "lyo_app.skills.models",
    "lyo_app.evolution.goals_models", "lyo_app.events.models",
    "lyo_app.learning_profile.models", "lyo_app.study_plans.models",
    "lyo_app.models.notebook", "lyo_app.ai_chat.mentor_models",
]


@pytest_asyncio.fixture
async def session_factory():
    for m in _MODEL_MODULES:
        try:
            __import__(m)
        except Exception:
            pass
    import lyo_app.core.database as dbmod
    from lyo_app.core.database import init_db

    engine = create_async_engine(
        "sqlite+aiosqlite:///file:acctdel?mode=memory&cache=shared&uri=true"
    )
    dbmod.engine = engine
    await init_db()
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_anonymize_scrubs_pii_and_preserves_others(session_factory):
    from lyo_app.auth.models import User, RefreshToken
    from lyo_app.feeds.models import Post, Comment, PostType
    from lyo_app.auth.account_deletion import anonymize_user_account

    async with session_factory() as db:
        victim = User(
            email="real@x.com", username="realuser", first_name="Real",
            last_name="Person", bio="bio", hashed_password="$2b$realhash",
            is_active=True, is_verified=True, firebase_uid="fb123",
        )
        bystander = User(
            email="b@x.com", username="bystander", hashed_password="x",
            is_active=True, is_verified=True,
        )
        db.add_all([victim, bystander])
        await db.flush()
        vid, bid = victim.id, bystander.id

        post = Post(author_id=vid, content="post", post_type=PostType.TEXT)
        db.add(post)
        await db.flush()
        db.add(Comment(author_id=bid, post_id=post.id, content="bystander reply"))
        db.add(RefreshToken(user_id=vid, token="t", expires_at=datetime.datetime.utcnow()))
        await db.commit()

    async with session_factory() as db:
        summary = await anonymize_user_account(db, vid)
        await db.commit()
        assert summary["users_anonymized"] == 1

    async with session_factory() as db:
        from sqlalchemy import select, func
        victim = await db.get(User, vid)
        # PII scrubbed
        assert "deleted" in victim.email and victim.email != "real@x.com"
        assert victim.username == f"deleted_user_{vid}"
        assert victim.first_name is None and victim.bio is None
        assert victim.firebase_uid is None
        # Login blocked
        assert victim.is_active is False
        assert victim.hashed_password == "!"
        # Sessions revoked
        tokens = (await db.execute(
            select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == vid)
        )).scalar()
        assert tokens == 0
        # Other users untouched, no FK violation orphaning
        bystander = await db.get(User, bid)
        assert bystander.email == "b@x.com"
        assert (await db.execute(select(func.count()).select_from(Comment))).scalar() == 1


@pytest.mark.asyncio
async def test_anonymize_missing_user_is_noop(session_factory):
    from lyo_app.auth.account_deletion import anonymize_user_account
    async with session_factory() as db:
        summary = await anonymize_user_account(db, 999999)
        assert summary["users_anonymized"] == 0
