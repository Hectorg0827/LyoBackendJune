"""Typed and legacy voice delivery share one authoritative Chat contract."""
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from lyo_app.ai.schemas.lyo2 import Intent, RouterRequest
from lyo_app.api.v1 import chat_lyo2 as chat, stream_lyo2 as stream
from lyo_app.teaching_runtime.interaction_contract import (
    DeliveryMode, contract_prompt, interaction_contract_for_request,
)
from tests.test_voice_turn_lifecycle import harness, event_payload


@pytest.mark.parametrize('text', [
    'Just answer: what is a root?', 'Explain photosynthesis',
    'Give a deep dive into gravity', 'Summarize this document',
    'Compare roots and stems', 'Quiz me on fractions',
    'I have a test on Friday', 'Create a course on algebra',
    'Teach me fractions', 'Continue',
])
def test_voice_changes_delivery_without_changing_interaction(text):
    text_contract = asdict(interaction_contract_for_request(text=text))
    voice_contract = asdict(interaction_contract_for_request(text=text, voice_mode=True))
    assert text_contract.pop('delivery_mode') is DeliveryMode.TEXT
    assert voice_contract.pop('delivery_mode') is DeliveryMode.VOICE
    assert text_contract == voice_contract


def test_typed_metadata_overrides_legacy_activation_and_capability():
    request = RouterRequest(
        text='Explain roots', voice_session={'active': False},
        state_summary={'voice_session': {'active': True, 'delivery': 'segments'}},
    )
    assert request.resolved_voice_session.active is False
    assert request.resolved_voice_session.delivery == 'answer'


@pytest.mark.parametrize('legacy', [None, 'invalid', {'locale': 'x' * 25}])
def test_malformed_optional_legacy_hint_cannot_break_chat(legacy):
    request = RouterRequest(text='Explain roots', state_summary={'voice_session': legacy})
    assert request.resolved_voice_session.active is False


def test_legacy_clients_keep_voice_and_default_to_whole_turn_delivery():
    request = RouterRequest(text='Explain roots', state_summary={'voice_session': {
        'active': True, 'transport': 'client_stt_tts',
    }})
    assert request.resolved_voice_session.active is True
    assert request.resolved_voice_session.delivery == 'answer'


def test_typed_segment_delivery_and_turn_metadata_are_bounded():
    request = RouterRequest(text='Explain roots', voice_session={
        'delivery': 'segments', 'turn_id': 'turn-42', 'locale': 'en-US',
        'interrupted_previous_turn': True,
    })
    assert request.resolved_voice_session.delivery == 'segments'
    assert request.resolved_voice_session.turn_id == 'turn-42'
    with pytest.raises(ValidationError):
        RouterRequest(text='Explain', voice_session={'turn_id': 'x' * 129})
    with pytest.raises(ValidationError):
        RouterRequest(text='Explain', voice_session={'delivery': 'unknown'})


def test_interrupt_metadata_only_affects_spoken_turn_taking():
    text = 'Explain roots'
    interrupted = interaction_contract_for_request(text=text, voice_mode=True, voice_interrupted_previous_turn=True)
    uninterrupted = interaction_contract_for_request(text=text, voice_mode=True)
    assert interrupted.mode == uninterrupted.mode
    assert interrupted.depth == uninterrupted.depth
    assert 'without restarting the old answer' in contract_prompt(interrupted)
    text_contract = interaction_contract_for_request(text=text, voice_interrupted_previous_turn=True)
    assert text_contract.voice_interrupted_previous_turn is False


@pytest.mark.asyncio
async def test_typed_voice_replay_emits_readiness(harness):
    harness.replay = 'An already persisted canonical answer.'
    response = await harness.response(state_summary={}, voice_session={'active': True, 'delivery': 'ready'})
    events = [event_payload(c) async for c in response.body_iterator]
    assert next(e for e in events if e['type'] == 'voice_ready')['text'] == harness.replay
    assert next(e for e in events if e['type'] == 'answer')['replayed'] is True


@pytest.mark.asyncio
async def test_both_routes_pass_typed_voice_through_existing_delivery_contract(harness, monkeypatch):
    captured = []

    class Executor:
        def __init__(self, db):
            pass

        async def execute(self, **kwargs):
            captured.append(kwargs['interaction_contract'])
            return SimpleNamespace(
                answer_block=SimpleNamespace(content={'text': 'Roots anchor the plant.'}),
                artifact_block=None, open_classroom_payload=None, next_actions=[], metadata={},
            )

    monkeypatch.setattr(stream, 'LyoExecutor', Executor)
    monkeypatch.setattr(chat, 'LyoExecutor', Executor)
    voice = {'active': True, 'interrupted_previous_turn': True, 'delivery': 'ready'}
    response = await harness.response(state_summary={}, voice_session=voice)
    events = [event_payload(c) async for c in response.body_iterator]
    assert any(e['type'] == 'voice_ready' for e in events)
    assert not any(e['type'] == 'voice_text_segment' for e in events)
    await chat._process_lyo2_request(
        RouterRequest(text='Just answer: name the parts', forced_intent=Intent.CHAT, voice_session=voice),
        SimpleNamespace(id=0), SimpleNamespace(),
    )
    assert len(captured) == 2
    for contract in captured:
        assert contract['delivery_mode'] == 'voice'
        assert contract['voice_interrupted_previous_turn'] is True
        assert contract['mode'] == 'answer'
        assert contract['voice_session']['interrupted_previous_turn'] is True
        assert 'channel' not in contract


@pytest.mark.asyncio
@pytest.mark.parametrize('voice_metadata', [
    {'state_summary': {'voice_session': {'active': True, 'transport': 'client_stt_tts'}}},
    {'state_summary': {}, 'voice_session': {'active': True}},
])
async def test_legacy_or_uncapable_client_receives_one_canonical_text_answer(harness, voice_metadata):
    response = await harness.response(**voice_metadata)
    events = [event_payload(c) async for c in response.body_iterator]
    assert not any(e['type'] in {'voice_ready', 'voice_text_segment'} for e in events)
    # Android's legacy parser turns any top-level text field into a Chat chunk.
    # There must be just one text-bearing response on that fallback path.
    text_events = [e for e in events if e['type'] == 'answer' or isinstance(e.get('text'), str)]
    assert len(text_events) == 1
    assert text_events[0]['block']['content']['text'] == harness.result


@pytest.mark.asyncio
async def test_ready_capability_marks_final_answer_as_non_speaking(harness):
    response = await harness.response(voice_session={'active': True, 'delivery': 'ready'})
    events = [event_payload(c) async for c in response.body_iterator]
    ready = next(e for e in events if e['type'] == 'voice_ready')
    answer = next(e for e in events if e['type'] == 'answer')
    assert ready['text'] == answer['block']['content']['text']
    assert ready['message_id'] == answer['message_id']
    assert answer['speak'] is False


@pytest.mark.asyncio
async def test_legacy_lesson_delivery_does_not_emit_an_extra_text_hint(harness):
    lesson = SimpleNamespace(to_plain_text=lambda: 'A canonical lesson.', next_directions=[])
    iterator = stream._emit_composed_lesson(
        SimpleNamespace(), lesson, [], [], SimpleNamespace(id='review-conversation'),
        'lesson-turn', 'general', voice_delivery=True, voice_ready_delivery=False,
    )
    events = [event_payload(c) async for c in iterator]
    assert not any(e['type'] == 'voice_ready' for e in events)
    answer = next(e for e in events if e['type'] == 'answer')
    assert answer['message_id'] == 'lesson-turn'
    assert answer['speak'] is True
