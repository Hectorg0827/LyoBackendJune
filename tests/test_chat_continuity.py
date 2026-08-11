"""Contract tests for authenticated, cross-device AI chat continuity."""

import pytest

from lyo_app.chat.models import ChatMode
from lyo_app.chat.stores import conversation_store


@pytest.mark.asyncio
async def test_conversation_history_survives_a_second_client_session(
    async_client, auth_headers, db_session
):
    created = await async_client.post(
        "/api/v1/chat/conversations",
        headers=auth_headers,
        json={"title": "Spanish practice", "device_id": "web"},
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    # Simulate the streaming layer persisting a turn on device A.
    await conversation_store.add_message(
        db_session, conversation_id, "user", "Teach me how to order coffee", ChatMode.GENERAL.value
    )
    await conversation_store.add_message(
        db_session, conversation_id, "assistant", "Start with: Quisiera un café.", ChatMode.GENERAL.value
    )

    # Device B knows only the conversation ID and receives canonical history.
    resumed = await async_client.get(
        f"/api/v1/chat/conversations/{conversation_id}", headers=auth_headers
    )
    assert resumed.status_code == 200, resumed.text
    payload = resumed.json()
    assert payload["title"] == "Spanish practice"
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
    assert payload["messages"][1]["content"] == "Start with: Quisiera un café."


@pytest.mark.asyncio
async def test_conversation_history_is_private_between_users(
    async_client, auth_headers, second_auth_headers
):
    created = await async_client.post(
        "/api/v1/chat/conversations", headers=auth_headers, json={"title": "Private tutor"}
    )
    conversation_id = created.json()["id"]

    hidden = await async_client.get(
        f"/api/v1/chat/conversations/{conversation_id}", headers=second_auth_headers
    )
    assert hidden.status_code == 404

    deleted = await async_client.delete(
        f"/api/v1/chat/conversations/{conversation_id}", headers=second_auth_headers
    )
    assert deleted.status_code == 404


@pytest.mark.asyncio
async def test_archive_removes_chat_from_active_history(async_client, auth_headers):
    created = await async_client.post(
        "/api/v1/chat/conversations", headers=auth_headers, json={"title": "Temporary"}
    )
    conversation_id = created.json()["id"]

    archived = await async_client.delete(
        f"/api/v1/chat/conversations/{conversation_id}", headers=auth_headers
    )
    assert archived.status_code == 204

    listing = await async_client.get("/api/v1/chat/conversations", headers=auth_headers)
    assert listing.status_code == 200
    assert conversation_id not in {item["id"] for item in listing.json()["conversations"]}


@pytest.mark.asyncio
async def test_retried_client_turn_is_persisted_exactly_once(
    async_client, auth_headers, db_session
):
    created = await async_client.post(
        "/api/v1/chat/conversations", headers=auth_headers, json={"title": "Retry proof"}
    )
    conversation_id = created.json()["id"]

    first = await conversation_store.add_message(
        db_session,
        conversation_id,
        "user",
        "Explain gravity",
        client_message_id="device-a-turn-1",
    )
    retried = await conversation_store.add_message(
        db_session,
        conversation_id,
        "user",
        "Explain gravity",
        client_message_id="device-a-turn-1",
    )

    assert retried.id == first.id
    messages = await conversation_store.get_messages(db_session, conversation_id)
    assert [(message.role, message.content) for message in messages] == [
        ("user", "Explain gravity")
    ]


@pytest.mark.asyncio
async def test_get_all_messages_is_not_capped_at_the_default_window(
    async_client, auth_headers, db_session
):
    """get_messages()'s default limit=50 exists for chat history/context
    building, where only the recent tail matters. A read over the *whole*
    conversation — e.g. the session-close summary's graded-check count —
    must use get_all_messages instead, or it silently drops anything
    earlier than the last 50 messages. Regression test for exactly that:
    a 55-message conversation must report 55 through get_all_messages, not
    the 50 get_messages() would cap it at.
    """
    created = await async_client.post(
        "/api/v1/chat/conversations",
        headers=auth_headers,
        json={"title": "Long lesson", "device_id": "web"},
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    total_messages = 55
    for i in range(total_messages):
        await conversation_store.add_message(
            db_session, conversation_id, "user", f"message {i}", ChatMode.GENERAL.value
        )

    windowed = await conversation_store.get_messages(db_session, conversation_id, limit=50)
    assert len(windowed) == 50

    everything = await conversation_store.get_all_messages(db_session, conversation_id)
    assert len(everything) == total_messages
