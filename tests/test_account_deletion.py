"""Account deletion over every table the app creates, on SQLite.

Production also creates tables at startup from the models (push devices, AI
chat...), beyond what migrations make. This builds the schema the same way,
with foreign keys enforced, and checks that after deleting an account no
table still names it, while another person's rows stay.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from lyo_app.auth import account_deletion
from lyo_app.auth.firebase_auth import firebase_auth_service


def _user_columns(metadata):
    """(table, column) for every column that holds a users.id."""
    for table in metadata.sorted_tables:
        for column in table.columns:
            if any(fk.column.table.name == "users" and fk.column.name == "id" for fk in column.foreign_keys):
                yield table, column
            elif not column.foreign_keys and re.match(r"^(?:\w+_)?user_id$", column.name):
                yield table, column


@pytest_asyncio.fixture
async def db(monkeypatch):
    import lyo_app.enhanced_main  # noqa: F401 — registers every model the app mounts
    from lyo_app.core.database import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Tenant-scoped rows default to the first organization.
        await conn.execute(text("INSERT INTO organizations (id, name, slug, plan_tier, is_active, monthly_api_calls, "
                                "monthly_ai_tokens, created_at, updated_at) VALUES (1, 'Lyo', 'lyo', 'free', 1, 0, 0, "
                                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    deleted_firebase = []
    monkeypatch.setattr(firebase_auth_service, "delete_firebase_user", lambda uid: deleted_firebase.append(uid) or True)
    yield sessions, Base.metadata, deleted_firebase
    await engine.dispose()


async def _add_user(session, name, **extra):
    from lyo_app.auth.models import RefreshToken, User
    from lyo_app.chat.models import ChatConversation
    from lyo_app.models.enhanced import PushDevice, PushPlatform

    user = User(email=f"{name}@example.com", username=name, hashed_password="x", **extra)
    session.add(user)
    await session.flush()
    session.add(RefreshToken(user_id=user.id, token=f"refresh-{name}", expires_at=datetime.utcnow() + timedelta(days=1)))
    session.add(PushDevice(user_id=user.id, device_token=f"apns-{name}", platform=PushPlatform.IOS))
    session.add(ChatConversation(id=f"chat-{name}", user_id=str(user.id), session_id=f"session-{name}"))
    await session.commit()
    return user.id


@pytest.mark.asyncio
async def test_no_table_names_a_deleted_account(db):
    sessions, metadata, deleted_firebase = db
    async with sessions() as session:
        alice = await _add_user(session, "alice", firebase_uid="firebase-alice")
        bob = await _add_user(session, "bob")

    async with sessions() as session:
        assert await account_deletion.delete_account(session, alice) is True

    async with sessions() as session:
        leftovers = []
        for table, column in _user_columns(metadata):
            value = str(alice) if column.type.python_type is str else alice
            if await session.scalar(select(func.count()).select_from(table).where(column == value)):
                leftovers.append(f"{table.name}.{column.name}")
        assert leftovers == []
        for table, column in _user_columns(metadata):
            if table.name in {"users", "refresh_tokens", "push_devices", "chat_conversations"} and column.name in {"id", "user_id"}:
                value = str(bob) if column.type.python_type is str else bob
                assert await session.scalar(select(func.count()).select_from(table).where(column == value)) == 1, table.name
        assert await session.scalar(text("SELECT count(*) FROM users WHERE id = :id"), {"id": bob}) == 1
    assert deleted_firebase == ["firebase-alice"]


@pytest.mark.asyncio
async def test_deleting_a_missing_account_reports_it(db):
    sessions, _metadata, deleted_firebase = db
    async with sessions() as session:
        assert await account_deletion.delete_account(session, 999_999) is False
    assert deleted_firebase == []
