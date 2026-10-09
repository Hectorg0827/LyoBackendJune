"""Real HTTP/database persistence, including competing PostgreSQL writers."""

import asyncio
import os
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Header
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lyo_app.ai.schemas.smart_block import SmartBlock
from lyo_app.ai_classroom.teaching_visuals import TeachingVisual
from lyo_app.api.v1 import stream_lyo2 as stream
from lyo_app.chat.models import ChatConversation, ChatMessage
from lyo_app.chat.stores import conversation_store
from lyo_app.chat.visuals import refresh_message_for_block_update, update_visual_blocks
from lyo_app.tenants.models import Organization


@pytest_asyncio.fixture
async def saved_visual(tmp_path):
    url = os.getenv("CHAT_VISUAL_POSTGRES_URL")
    schema = "visual_test_" + uuid4().hex
    admin = None
    if url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        admin = create_async_engine(url)
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'visual.db'}")
    tables = [Organization.__table__, ChatConversation.__table__, ChatMessage.__table__]
    try:
        async with engine.begin() as conn:
            for table in tables:
                await conn.run_sync(table.create)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        visual = SmartBlock.teaching_visual(TeachingVisual(
            kind="fraction_pie", title="Explore fractions", caption="Tap the slices to shade them.",
            description="Three of four equal parts are shaded.", parts=4, value=3,
        )).model_dump(mode="json")
        quiz = {"id": "quiz-1", "type": "quiz", "content": {"correct_index": 0}, "metadata": {}}
        async with sessions() as db:
            db.add(Organization(id=1, name="Test", slug=schema))
            await db.flush()
            conversation = ChatConversation(user_id="42", session_id="test-device")
            db.add(conversation)
            await db.flush()
            message = ChatMessage(conversation_id=conversation.id, role="assistant",
                                  content="The fraction 3/4.", blocks=[visual, quiz])
            db.add(message)
            await db.commit()
            conversation_id, message_id = conversation.id, message.id
        app = FastAPI()
        app.include_router(stream.router, prefix="/api/v1/lyo2")

        async def get_db():
            async with sessions() as db:
                yield db

        def current_user(x_test_user: str = Header(default="42")):
            return SimpleNamespace(id=x_test_user)

        app.dependency_overrides[stream.get_db] = get_db
        app.dependency_overrides[stream.get_current_user_or_guest] = current_user
        yield SimpleNamespace(app=app, sessions=sessions, conversation_id=conversation_id,
                              message_id=message_id, visual=visual, quiz=quiz,
                              postgres=engine.dialect.name == "postgresql")
    finally:
        await engine.dispose()
        if admin:
            async with admin.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()


@pytest.mark.asyncio
async def test_http_save_survives_new_client_and_new_database_session(saved_visual):
    saved = saved_visual
    body = {"conversation_id": saved.conversation_id, "block_id": saved.visual["id"],
            "values": {"parts": 8, "value": 2}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=saved.app), base_url="http://test") as client:
        response = await client.post("/api/v1/lyo2/chat/visual", json=body)
        assert response.status_code == 200, response.text
    async with saved.sessions() as device_b:
        messages = await conversation_store.get_messages(device_b, saved.conversation_id)
        assert messages[0].blocks[0] == response.json()["block"]
        assert messages[0].blocks[1] == saved.quiz
    # A second client's invalid or unauthorized edit must leave storage intact.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=saved.app), base_url="http://test") as client:
        for values in [{"parts": 2, "value": 3}, {"value": True}, {"value": 1, "correct_index": 1}]:
            bad = await client.post("/api/v1/lyo2/chat/visual", json={**body, "values": values})
            assert bad.status_code == 422
        for user, status in [("43", 404), ("0", 401)]:
            denied = await client.post("/api/v1/lyo2/chat/visual", json=body, headers={"x-test-user": user})
            assert denied.status_code == status
    async with saved.sessions() as reopened:
        message = await reopened.get(ChatMessage, saved.message_id)
        assert message.blocks[0] == response.json()["block"]
        assert message.blocks[1] == saved.quiz


@pytest.mark.asyncio
@pytest.mark.parametrize("first_writer", ["visual", "quiz"])
async def test_postgres_row_lock_preserves_visual_and_grade_in_either_order(saved_visual, first_writer):
    saved = saved_visual
    if not saved.postgres:
        pytest.skip("CHAT_VISUAL_POSTGRES_URL is required; SQLite cannot verify row locks")
    verdict = stream.CheckAnswerResponse(correct=False, correct_index=0, selected_index=1,
                                         explanation="Two quarters make half.")
    async with saved.sessions() as first, saved.sessions() as second:
        # Both writers deliberately start with the same stale JSON snapshot.
        first_message = await first.get(ChatMessage, saved.message_id)
        second_message = await second.get(ChatMessage, saved.message_id)
        assert first_message.blocks == second_message.blocks
        await refresh_message_for_block_update(first, first_message)
        if first_writer == "visual":
            first_message.blocks, _ = update_visual_blocks(first_message.blocks, saved.visual["id"],
                                                          {"parts": 8, "value": 2})
            competing = asyncio.create_task(stream._persist_check_result(second, second_message, "quiz-1", verdict))
        else:
            blocks = deepcopy(first_message.blocks)
            blocks[1]["metadata"]["result"] = verdict.model_dump()
            first_message.blocks = blocks
            competing = asyncio.create_task(stream.update_chat_visual(
                stream.VisualUpdateRequest(conversation_id=saved.conversation_id, block_id=saved.visual["id"],
                                           values={"parts": 8, "value": 2}), SimpleNamespace(id=42), second))
        try:
            completed, _ = await asyncio.wait({competing}, timeout=0.1)
            assert not completed, "The competing writer must wait for the locked row"
            await first.commit()
            await asyncio.wait_for(competing, timeout=5)
        finally:
            if not competing.done():
                competing.cancel()
                await asyncio.gather(competing, return_exceptions=True)
    async with saved.sessions() as reopened:
        message = await reopened.get(ChatMessage, saved.message_id)
        assert message.blocks[0]["content"]["visual"]["parts"] == 8
        assert message.blocks[0]["content"]["visual"]["value"] == 2
        assert message.blocks[1]["metadata"]["result"] == verdict.model_dump()
        assert message.blocks[1]["content"]["correct_index"] == 0
