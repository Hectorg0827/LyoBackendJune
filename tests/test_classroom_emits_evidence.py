"""Drive the live pathway into the shared event stream, with AI and DB services stubbed."""
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS, session_progress_key
from lyo_app.ai_classroom.sdui_models import ActionIntent, InputField
from tests.adaptive_fixtures import action, context, engine, evaluation, seed


@pytest.fixture(autouse=True)
def clean_sessions():
    _SESSION_PROGRESS.clear()
    yield
    _SESSION_PROGRESS.clear()


@pytest.fixture
def capture(monkeypatch):
    log = AsyncMock()
    dkt = AsyncMock()
    monkeypatch.setattr("lyo_app.events.processor.log_learning_event", log)
    monkeypatch.setattr("lyo_app.personalization.service.DeepKnowledgeTracer.update_mastery", dkt)
    return log, dkt


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,rung", [("choose", "recognition"), ("apply", "application"), ("explain", "explanation")])
async def test_a_live_answer_reaches_the_shared_event_stream_at_the_right_rung(capture, kind, rung):
    log, dkt = capture
    ctx = context(topic="Compare fractions")
    instance = engine(ctx)
    component_id = seed(instance, ctx, kind)
    if kind == "choose":
        await instance.handle_quiz_submission("42", "fractions", component_id, "a", 4000)
    else:
        await instance.handle_transfer_submission("42", "fractions", component_id, "One half: fewer equal pieces.", 4000)
    log.assert_awaited_once()
    event = log.await_args.args[1]
    assert event.user_id == 42 and event.concept_id == "compare_fractions"
    assert event.source_surface == "classroom" and event.evidence_type == rung
    assert event.measurable_outcome == 1.0
    assert not event.skill_ids_json  # DKT is updated once directly, not again by the processor.
    assert event.metadata_json == {"classroom_checkpoint_id": component_id}
    assert "criteria" not in str(event.model_dump())
    assert "example_answer" not in str(event.model_dump())
    dkt.assert_awaited_once()
    assert dkt.await_args.args[4] == 4.0


@pytest.mark.asyncio
async def test_wrong_response_is_exposure_with_an_actual_misconception(capture):
    log, _ = capture
    ctx = context()
    instance = engine(ctx)
    component_id = seed(instance, ctx, "apply")
    instance.adaptive_teacher.evaluate.return_value = evaluation("incorrect",
        misconception="More cuts make bigger pieces", feedback="More equal cuts make smaller pieces.")
    await instance.handle_transfer_submission("42", "fractions", component_id, "A third because three is bigger.")
    event = log.await_args.args[1]
    assert event.measurable_outcome == 0.0 and event.evidence_type == "exposure"
    assert event.misconception == "More cuts make bigger pieces"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["choose", "apply"])
async def test_unowned_or_ungraded_question_never_reaches_evidence_or_dkt(capture, kind):
    log, dkt = capture
    instance, ctx = engine(), context()
    seed(instance, ctx, kind)
    if kind == "choose":
        await instance.handle_quiz_submission("42", "fractions", "missing-id", "a", 4000)
    else:
        await instance.handle_transfer_submission("42", "fractions", "missing-id", "Any response", 4000)
    log.assert_not_awaited()
    dkt.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_timing_is_not_fabricated(capture):
    log, dkt = capture
    instance, ctx = engine(), context()
    component_id = seed(instance, ctx)
    await instance.handle_quiz_submission("42", "fractions", component_id, "a")
    log.assert_awaited_once()
    dkt.assert_not_awaited()


@pytest.mark.asyncio
async def test_guest_has_no_durable_evidence_record(capture):
    log, dkt = capture
    ctx = context(user_id="guest-42")
    instance = engine(ctx)
    component_id = seed(instance, ctx)
    await instance.handle_quiz_submission(ctx.user_id, ctx.session_id, component_id, "a", 4000)
    log.assert_not_awaited()
    dkt.assert_not_awaited()


@pytest.mark.asyncio
async def test_logging_failure_keeps_the_next_turn_and_outbox_for_retry(capture):
    log, _ = capture
    log.side_effect = RuntimeError("DB offline")
    instance, ctx = engine(), context()
    component_id = seed(instance, ctx)
    scene = await instance.handle_quiz_submission("42", "fractions", component_id, "a", 4000)
    assert any(isinstance(c, InputField) for c in scene.components)
    progress = _SESSION_PROGRESS[session_progress_key("42", "fractions")]
    assert len(progress["guided_state"]["outbox"]) == 1
    log.side_effect = None
    await instance.process_trigger(action(welcome=True))
    assert progress["guided_state"]["outbox"] == []


@pytest.mark.asyncio
async def test_replayed_outbox_does_not_record_or_trace_the_same_checkpoint_twice(capture):
    log, dkt = capture
    instance = engine()
    instance.db.execute.return_value.scalar_one_or_none.return_value = 21
    assert await instance._record_adaptive_evidence(
        event_id="already-stored", user_id="42", concept_id="fractions",
        correct=True, hints_used=0, response_time_ms=4000)
    log.assert_not_awaited()
    dkt.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("wire,stored", [("transfer", "transfer"), ("retrieval", "retention")])
async def test_existing_event_vocabulary_is_preserved(capture, wire, stored):
    log, _ = capture
    instance = engine()
    await instance._log_classroom_evidence(user_id="42", concept_id="fractions",
        correct=True, hints_used=0, evidence_type=wire)
    assert log.await_args.args[1].evidence_type == stored
