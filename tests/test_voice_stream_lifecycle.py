"""Voice provider and canonical SSE lifecycle integration regressions."""
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

from tests.test_voice_turn_lifecycle import harness, event_payload

async def until_segment(response):
    events = []
    async for chunk in response.body_iterator:
        event = event_payload(chunk)
        events.append(event)
        if event['type'] == 'voice_text_segment':
            return events
    raise AssertionError(f'No early segment; events: {events}')

@pytest.mark.asyncio
async def test_combined_stream_is_early_canonical_and_persists_once(harness):
    response = await harness.response(state_summary={"voice_session": {"active": True, "delivery": "segments"}})
    events = await until_segment(response)
    assert not harness.completed
    assert not any(w['role'] == 'assistant' for w in harness.writes)
    harness.finish.set()
    events += [event_payload(c) async for c in response.body_iterator]
    segments = [e for e in events if e['type'] == 'voice_text_segment']
    ready = [e for e in events if e['type'] == 'voice_ready']
    answers = [e for e in events if e['type'] == 'answer']
    assert [e['sequence'] for e in segments] == [1, 2]
    assert ' '.join(e['text'] for e in segments) == harness.result
    assert len(ready) == len(answers) == 1
    assert ready[0]['text'] == answers[0]['block']['content']['text'] == harness.result
    assert ready[0]['speak'] is False
    assert {e['message_id'] for e in segments + ready + answers} == {ready[0]['message_id']}
    assert [w['content'] for w in harness.writes if w['role'] == 'assistant'] == [harness.result]

@pytest.mark.asyncio
async def test_closing_response_iterator_cancels_in_flight_executor(harness):
    response = await harness.response(state_summary={"voice_session": {"active": True, "delivery": "segments"}})
    await until_segment(response)
    await response.body_iterator.aclose()
    try:
        await asyncio.wait_for(harness.cancelled.wait(), timeout=0.15)
        was_cancelled = True
    except asyncio.TimeoutError:
        was_cancelled = False
    finally:
        harness.finish.set()
        await asyncio.sleep(0.02)
    assert was_cancelled, 'Closing SSE iterator left canonical generation running'

def failing_manager(monkeypatch, fail_after_output=True):
    from lyo_app.teaching_runtime import model_usage
    capture = AsyncMock()
    monkeypatch.setattr(model_usage, 'capture_model_usage', capture)
    manager = ai_resilience.AIResilienceManager()
    manager._initialized = True
    manager.session = object()
    manager.models = {
        name: ai_resilience.AIModelConfig(name=name, endpoint='openai', api_key='review-test-key')
        for name in ['gpt-4o-mini', 'gpt-4o']
    }
    manager.circuit_breakers = {n: ai_resilience.CircuitBreaker(ai_resilience.CircuitBreakerConfig()) for n in manager.models}
    calls = []

    async def fake_stream():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='This answer was cut off.'))],
                              usage=SimpleNamespace(total_tokens=37))
        if fail_after_output:
            raise RuntimeError('review simulated provider disconnect')

    async def create(**kwargs):
        calls.append(kwargs['model'])
        return fake_stream()

    manager.openai_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(ai_resilience, 'ai_resilience_manager', manager)
    return manager, capture, calls

@pytest.mark.asyncio
async def test_partial_provider_disconnect_is_not_a_successful_canonical_answer(monkeypatch):
    manager, capture, calls = failing_manager(monkeypatch)
    executor = LyoExecutor.__new__(LyoExecutor)
    executor._gemini = object()
    deltas = []

    async def emit(delta):
        deltas.append(delta)

    with pytest.raises(ai_resilience.StreamingIncompleteError) as interrupted:
        await executor.execute(
        user_id='42', plan=LyoPlan(steps=[PlannedAction(action_type=ActionType.GENERATE_TEXT, description='Review answer', parameters={})]),
        original_request='Explain the parts', interaction_contract={'mode': 'answer', 'depth': 'standard', 'fast_lane': True, 'delivery_mode': 'voice'},
        text_delta_callback=emit,
    )
    assert calls == ['gpt-4o-mini'], 'A partial answer must never restart at another provider'
    assert interrupted.value.partial_text == 'This answer was cut off.'

@pytest.mark.asyncio
async def test_usage_is_attributed_when_provider_fails_after_output(monkeypatch):
    manager, capture, calls = failing_manager(monkeypatch)
    with pytest.raises(ai_resilience.StreamingIncompleteError):
        _ = [d async for d in manager.stream_chat_completion([{'role': 'user', 'content': 'Explain'}], provider_order=['gpt-4o-mini', 'gpt-4o'])]
    assert capture.await_count == 1
    assert capture.await_args.kwargs['tokens_used'] == 37
    assert capture.await_args.kwargs['completion_status'] == 'incomplete'

@pytest.mark.asyncio
async def test_successful_stream_records_openai_usage(monkeypatch):
    manager, capture, calls = failing_manager(monkeypatch, fail_after_output=False)
    output = [d async for d in manager.stream_chat_completion([{'role': 'user', 'content': 'Explain'}], provider_order=['gpt-4o-mini'])]
    assert output
    assert capture.await_count == 1
    assert capture.await_args.kwargs['tokens_used'] == 37

def test_segmenter_preserves_decimal_across_provider_deltas():
    from lyo_app.teaching_runtime.voice_delivery import VoiceSegmenter
    segmenter = VoiceSegmenter()
    segments = segmenter.feed('The result equals 3.')
    segments += segmenter.feed('14 in decimal.')
    segments += segmenter.flush()
    assert ' '.join(segments) == 'The result equals 3.14 in decimal.', segments

@pytest.mark.asyncio
async def test_gemini_adapter_streams_real_sse_shape_and_records_usage(monkeypatch):
    from lyo_app.teaching_runtime import model_usage
    capture = AsyncMock()
    monkeypatch.setattr(model_usage, 'capture_model_usage', capture)
    release = asyncio.Event()

    async def content():
        yield b'data: {"candidates":[{"content":{"parts":[{"text":"First sentence. "}]}}]}\n'
        await release.wait()
        yield b'data: {"candidates":[{"content":{"parts":[{"text":"Second sentence."}]}}],"usageMetadata":{"totalTokenCount":60}}\n'

    class ResponseContext:
        async def __aenter__(self):
            return SimpleNamespace(status=200, content=content())

        async def __aexit__(self, *args):
            return False

    posted = []

    def post(endpoint, **kwargs):
        posted.append((endpoint, kwargs))
        return ResponseContext()

    manager = ai_resilience.AIResilienceManager()
    manager._initialized = True
    manager.session = SimpleNamespace(post=post)
    manager.models = {'gemini-test': ai_resilience.AIModelConfig(name='gemini-test', endpoint='https://example.invalid/model:generateContent', api_key='review-test-key')}
    manager.circuit_breakers = {'gemini-test': ai_resilience.CircuitBreaker(ai_resilience.CircuitBreakerConfig())}
    iterator = manager.stream_chat_completion([{'role': 'user', 'content': 'Explain'}], provider_order=['gemini-test'])
    assert await asyncio.wait_for(anext(iterator), 0.25) == 'First sentence. '
    assert capture.await_count == 0
    release.set()
    assert [d async for d in iterator] == ['Second sentence.']
    assert ':streamGenerateContent?alt=sse' in posted[0][0]
    assert capture.await_count == 1
    assert capture.await_args.kwargs['tokens_used'] == 60


@pytest.mark.asyncio
async def test_segments_require_explicit_client_delivery_support(harness):
    response = await harness.response()
    events = [event_payload(c) async for c in response.body_iterator]
    assert not any(e['type'] == 'voice_text_segment' for e in events)
    assert any(e['type'] == 'voice_ready' for e in events)


@pytest.mark.asyncio
async def test_asgi_disconnect_cancels_generation_and_marks_partial_history(harness):
    response = await harness.response(state_summary={
        'voice_session': {'active': True, 'delivery': 'segments'},
    })
    heard = asyncio.Event()

    async def send(message):
        if message['type'] == 'http.response.body' and message.get('body'):
            if event_payload(message['body'])['type'] == 'voice_text_segment':
                heard.set()

    async def receive():
        await heard.wait()
        return {'type': 'http.disconnect'}

    await asyncio.wait_for(response({'type': 'http', 'asgi': {'spec_version': '2.0'}}, receive, send), 1)
    await asyncio.wait_for(harness.cancelled.wait(), .25)
    await asyncio.sleep(.02)  # Independently retained write can finish after ASGI exits.
    assistant = [w for w in harness.writes if w['role'] == 'assistant']
    assert len(assistant) == 1
    assert assistant[0]['action_triggered'] == 'voice_incomplete'


@pytest.mark.asyncio
async def test_provider_cancel_closes_stream_and_records_observed_usage(monkeypatch):
    manager, capture, calls = failing_manager(monkeypatch, fail_after_output=False)
    closed = asyncio.Event()

    class Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Visible text'))],
                                   usage=SimpleNamespace(total_tokens=37))

        async def close(self):
            closed.set()

    async def create(**kwargs):
        return Stream()

    manager.openai_client.chat.completions.create = create
    iterator = manager.stream_chat_completion([{'role': 'user', 'content': 'Explain'}], provider_order=['gpt-4o-mini'])
    assert await anext(iterator) == 'Visible text'
    await iterator.aclose()
    assert closed.is_set()
    assert capture.await_count == 1
    assert capture.await_args.kwargs['completion_status'] == 'cancelled'
    assert capture.await_args.kwargs['tokens_used'] == 37
    assert manager.circuit_breakers['gpt-4o-mini'].failure_count == 0


@pytest.mark.asyncio
async def test_failed_stream_is_persisted_and_replayed_as_incomplete(harness, monkeypatch):
    class IncompleteExecutor:
        def __init__(self, db):
            pass

        async def execute(self, **kwargs):
            await kwargs['text_delta_callback']('This canonical answer was cut off. ')
            raise ai_resilience.StreamingIncompleteError('This canonical answer was cut off.', 'gpt-4o-mini')

    monkeypatch.setattr(stream, 'LyoExecutor', IncompleteExecutor)
    response = await harness.response(state_summary={'voice_session': {'active': True, 'delivery': 'segments'}})
    events = [event_payload(c) async for c in response.body_iterator]
    assert not any(e['type'] == 'voice_ready' for e in events)
    assert next(e for e in events if e['type'] == 'answer')['generation_status'] == 'incomplete'
    assert any(e['type'] == 'voice_incomplete' for e in events)
    assert next(w for w in harness.writes if w['role'] == 'assistant')['action_triggered'] == 'voice_incomplete'
    monkeypatch.setattr(stream.conversation_store, 'get_message_by_client_id', AsyncMock(return_value=SimpleNamespace(
        content='This canonical answer was cut off.', generation_status='incomplete',
    )))
    replay = await harness.response()
    replay_events = [event_payload(c) async for c in replay.body_iterator]
    assert not any(e['type'] == 'voice_ready' for e in replay_events)
    assert next(e for e in replay_events if e['type'] == 'answer')['generation_status'] == 'incomplete'
    assert next(e for e in replay_events if e['type'] == 'voice_incomplete')['replayed'] is True


@pytest.mark.asyncio
async def test_incomplete_history_survives_reload_with_status(db_session):
    from lyo_app.chat.stores import conversation_store
    from lyo_app.chat.schemas import ConversationMessageRead
    conversation = await conversation_store.create_conversation(db_session, session_id='partial-test')
    message = await conversation_store.add_message(
        db_session, conversation.id, role='assistant', content='A cut-off answer',
        action_triggered='voice_incomplete', client_message_id='partial-turn',
    )
    assert ConversationMessageRead.model_validate(message).generation_status == 'incomplete'


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['openai', 'gemini'])
async def test_token_limit_is_incomplete_without_poisoning_provider_health(monkeypatch, provider):
    manager, capture, calls = failing_manager(monkeypatch, fail_after_output=False)
    if provider == 'openai':
        async def chunks():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content='A truncated answer.'), finish_reason='length')],
                usage=SimpleNamespace(total_tokens=37),
            )

        async def create(**kwargs):
            calls.append(kwargs['model'])
            return chunks()

        manager.openai_client.chat.completions.create = create
    else:
        manager.models['gpt-4o-mini'].endpoint = 'https://example.invalid/model:generateContent'

        async def content():
            yield ('data: ' + json.dumps({
                'candidates': [{'content': {'parts': [{'text': 'A truncated answer.'}]}, 'finishReason': 'MAX_TOKENS'}],
                'usageMetadata': {'totalTokenCount': 37},
            }) + '\n').encode()

        class Context:
            async def __aenter__(self):
                return SimpleNamespace(status=200, content=content())

            async def __aexit__(self, *args):
                return False

        manager.session = SimpleNamespace(post=lambda *a, **kw: Context())

    with pytest.raises(ai_resilience.StreamingIncompleteError) as outcome:
        _ = [part async for part in manager.stream_chat_completion(
            [{'role': 'user', 'content': 'Explain'}], provider_order=['gpt-4o-mini', 'gpt-4o'],
        )]
    assert outcome.value.partial_text == 'A truncated answer.'
    assert manager.circuit_breakers['gpt-4o-mini'].failure_count == 0
    assert capture.await_count == 1
    assert capture.await_args.kwargs['completion_status'] == 'incomplete'
    assert capture.await_args.kwargs['tokens_used'] == 37
