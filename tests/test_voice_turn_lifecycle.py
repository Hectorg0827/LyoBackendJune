"""Canonical voice readiness, replay, and disconnect persistence regressions."""
import asyncio

import json

from types import SimpleNamespace

from unittest.mock import AsyncMock

import pytest

from starlette.requests import Request

from lyo_app.ai.schemas.lyo2 import ActionType, Intent, LyoPlan, PlannedAction, RouterRequest

from lyo_app.ai.executor import LyoExecutor

from lyo_app.api.v1 import stream_lyo2 as stream

from lyo_app.core import ai_resilience

from lyo_app.teaching_runtime.models import TeachingAction, TeachingDecision

def event_payload(chunk):
    if isinstance(chunk, bytes):
        chunk = chunk.decode()
    value = chunk.removeprefix('data: ').strip()
    return {'type': 'DONE'} if value == '[DONE]' else json.loads(value)

@pytest.fixture
def harness(monkeypatch):
    import lyo_app.teaching_runtime as runtime
    from lyo_app.study_plans import routes as prep_routes

    control = SimpleNamespace(
        finish=asyncio.Event(), cancelled=asyncio.Event(), completed=False,
        writes=[], replay=None, result='The first part is the root. The second part is the stem.',
    )

    async def add_message(*args, **kwargs):
        control.writes.append(dict(kwargs))

    monkeypatch.setattr(stream.conversation_store, 'get_owned_conversation', AsyncMock(return_value=SimpleNamespace(id='review-conversation')))
    monkeypatch.setattr(stream.conversation_store, 'get_messages', AsyncMock(return_value=[]))

    async def replay(*args, **kwargs):
        return SimpleNamespace(content=control.replay) if control.replay else None

    monkeypatch.setattr(stream.conversation_store, 'get_message_by_client_id', replay)
    monkeypatch.setattr(stream.conversation_store, 'add_message', add_message)
    monkeypatch.setattr(prep_routes, 'owned_profile', AsyncMock(return_value=None))
    monkeypatch.setattr(stream, 'ai_performance_optimizer', SimpleNamespace(
        initialize=AsyncMock(), optimize_request=AsyncMock(return_value={'cache_key': 'review-cache'}),
        optimize_response=AsyncMock(side_effect=lambda **kw: kw['response']),
        cache_manager=SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock()),
    ))
    monkeypatch.setattr(runtime, 'decide_for_chat', AsyncMock(return_value=TeachingDecision(
        action=TeachingAction.ANSWER, reason_code='review-direct-answer', policy_version='review',
    )))
    monkeypatch.setattr(runtime, 'record_policy_decision', AsyncMock())

    class FakeExecutor:
        def __init__(self, db):
            pass

        async def execute(self, **kwargs):
            callback = kwargs.get('text_delta_callback')
            try:
                if callback:
                    await callback('The first part is the root. ')
                    await control.finish.wait()
                    await callback('The second part is the stem.')
                control.completed = True
                return SimpleNamespace(
                    answer_block=SimpleNamespace(content={'text': control.result}),
                    artifact_block=None, open_classroom_payload=None, next_actions=[], metadata={},
                )
            except asyncio.CancelledError:
                control.cancelled.set()
                raise

    monkeypatch.setattr(stream, 'LyoExecutor', FakeExecutor)

    async def response(**overrides):
        params = dict(text='Just answer: name the parts', forced_intent=Intent.CHAT,
                      conversation_id='review-conversation', client_message_id='review-turn',
                      state_summary={'voice_session': {'active': True, 'delivery': 'ready'}})
        params.update(overrides)
        return await stream.stream_lyo2_chat(
            RouterRequest(**params), Request({'type': 'http', 'headers': []}),
            SimpleNamespace(id=42), SimpleNamespace(),
        )

    control.response = response
    return control

@pytest.mark.asyncio
async def test_authenticated_retry_replays_voice_ready(harness):
    harness.replay = 'This canonical answer is already persisted.'
    response = await harness.response()
    events = [event_payload(c) async for c in response.body_iterator]
    assert any(e['type'] == 'answer' for e in events)
    assert any(e['type'] == 'voice_ready' for e in events), [e['type'] for e in events]

@pytest.mark.asyncio
async def test_closing_after_voice_ready_retains_canonical_assistant_history(harness):
    harness.finish.set()
    response = await harness.response()
    async for chunk in response.body_iterator:
        event = event_payload(chunk)
        if event['type'] == 'voice_ready':
            break
    else:
        raise AssertionError('Expected voice_ready before closing stream')
    await response.body_iterator.aclose()
    assert [w['content'] for w in harness.writes if w['role'] == 'assistant'] == [harness.result], 'Canonical answer was delivered but disappeared before the deferred persistence step'

@pytest.mark.asyncio
async def test_test_prep_ready_uses_canonical_text_before_assistant_write(harness, monkeypatch):
    from lyo_app.study_plans import chat as prep_chat
    text = 'Use this code:\n```python\nx = 2\n```'
    monkeypatch.setattr(prep_chat, 'process_chat_turn', AsyncMock(return_value=text))
    response = await harness.response(text='I have a test', forced_intent=Intent.TEST_PREP)
    events = []
    async for c in response.body_iterator:
        event = event_payload(c)
        events.append(event)
        if event['type'] == 'voice_ready':
            assert event['text'] == text
            assert not any(w['role'] == 'assistant' for w in harness.writes)
    assert [w['content'] for w in harness.writes if w['role'] == 'assistant'] == [text]
    assert next(e for e in events if e['type'] == 'answer')['block']['content']['text'] == text


@pytest.mark.asyncio
async def test_lesson_close_preserves_unredacted_gradeable_blocks(harness):
    text = 'A canonical lesson with a server-graded check.'
    blocks = [{'type': 'quiz', 'content': {'correct_index': 1, 'question': 'Which?'}}]
    lesson = SimpleNamespace(to_plain_text=lambda: text, next_directions=[])
    iterator = stream._emit_composed_lesson(
        SimpleNamespace(), lesson, blocks, [], SimpleNamespace(id='review-conversation'),
        'lesson-turn', 'general', voice_delivery=True,
    )
    assert event_payload(await anext(iterator))['type'] == 'voice_ready'
    await iterator.aclose()
    saved = [w for w in harness.writes if w['role'] == 'assistant']
    assert len(saved) == 1
    assert saved[0]['blocks'] == blocks
    assert saved[0]['client_message_id'] == 'lesson-turn'


@pytest.mark.asyncio
async def test_assistant_write_owns_session_after_request_session_closes(db_session, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from lyo_app.chat.persistence import schedule_assistant_message
    from lyo_app.chat.stores import conversation_store

    conversation = await conversation_store.create_conversation(
        db_session, session_id='voice-write', topic='Session lifetime',
    )
    request_db = AsyncSession(bind=db_session.bind, expire_on_commit=False)
    started, release = asyncio.Event(), asyncio.Event()
    original = conversation_store.add_message

    async def blocked_write(write_db, *args, **kwargs):
        assert write_db is not request_db
        started.set()
        await release.wait()
        return await original(write_db, *args, **kwargs)

    monkeypatch.setattr(conversation_store, 'add_message', blocked_write)
    write = schedule_assistant_message(
        request_db, conversation.id, content='Completed answer',
        mode_used='general', client_message_id='voice-completed-turn',
    )
    await started.wait()
    await request_db.close()
    release.set()
    await write
    # A retried delivery uses the same identity and creates no duplicate row.
    await schedule_assistant_message(
        request_db, conversation.id, content='Completed answer',
        mode_used='general', client_message_id='voice-completed-turn',
    )
    saved = await conversation_store.get_messages(db_session, conversation.id)
    assert [(m.role, m.content) for m in saved] == [('assistant', 'Completed answer')]
