import pytest
from types import SimpleNamespace

from lyo_app.ai.executor import _attachment_grounding, _presentation_blocks
from lyo_app.ai.interaction_contract import InteractionMode, resolve_interaction_contract
from lyo_app.ai.schemas.lyo2 import InputModality, Intent, MediaRef, RouterDecision, RouterRequest
from lyo_app.ai import multimodal
from lyo_app.ai.multimodal import load_media_attachments
from lyo_app.teaching_runtime.models import TeachingAction
from lyo_app.teaching_runtime.service import decide_for_chat


def decision(intent: Intent = Intent.EXPLAIN, **kwargs) -> RouterDecision:
    return RouterDecision(
        intent=intent,
        confidence=kwargs.pop("confidence", 0.95),
        needs_clarification=kwargs.pop("needs_clarification", False),
        suggested_tier="MEDIUM",
        **kwargs,
    )


def contract(text: str, *, intent: Intent = Intent.EXPLAIN, has_media: bool = False, has_current_media: bool = False, **decision_kwargs):
    return resolve_interaction_contract(
        RouterRequest(text=text),
        decision(intent, **decision_kwargs),
        has_media=has_media,
        has_current_media=has_current_media,
    )


def test_direct_question_is_answer_first_and_fast():
    result = contract("What is photosynthesis?")
    assert result.mode is InteractionMode.ANSWER
    assert result.answer_first is True
    assert result.fast_lane is True


def test_explanation_is_answer_first_not_a_diagnostic():
    result = contract("Explain photosynthesis")
    assert result.mode is InteractionMode.EXPLAIN
    assert result.answer_first is True
    assert result.fast_lane is True


@pytest.mark.asyncio
async def test_interaction_contract_prevents_first_contact_diagnostic():
    resolved = contract("Explain photosynthesis")
    teaching = await decide_for_chat(
        db=None,
        user_id=None,
        user_text="Explain photosynthesis",
        intent="EXPLAIN",
        concept_id="photosynthesis",
        interaction_contract=resolved.model_dump(mode="json"),
    )
    assert teaching.action is TeachingAction.EXPLAIN
    assert teaching.reason_code == "interaction_contract_answer_first"
    assert teaching.interaction_required is False


def test_explicit_teach_keeps_pedagogy_in_control():
    result = contract("Teach me fractions")
    assert result.mode is InteractionMode.TEACH
    assert result.answer_first is False
    assert result.fast_lane is False


def test_quiz_workflow_is_never_converted_to_answer():
    result = contract("Quiz me on this PDF", intent=Intent.QUIZ, has_media=True, has_current_media=True)
    assert result.mode is InteractionMode.QUIZ
    assert result.preserve_workflow is True
    assert result.answer_first is False


def test_compare_prefers_table_and_fast_lane():
    result = contract("Compare mitosis vs meiosis")
    assert result.mode is InteractionMode.COMPARE
    assert result.representation == "table"
    assert result.fast_lane is True


def test_summary_of_attachment_is_grounded_and_direct():
    result = contract("Summarize this PDF", intent=Intent.SUMMARIZE_NOTES, has_media=True, has_current_media=True)
    assert result.mode is InteractionMode.SUMMARIZE
    assert result.representation == "document"
    assert result.requires_grounding is True
    assert result.answer_first is True


def test_current_question_routes_to_live_search():
    result = contract("What is the latest news about quantum computing?")
    assert result.mode is InteractionMode.SEARCH
    assert result.requires_grounding is True
    assert result.answer_first is True
    assert result.fast_lane is False


def test_depth_controls_understand_chat_action_labels():
    assert contract("Explain deeper").depth == "deep"
    assert contract("Give me a quick concise answer about gravity").depth == "compact"


def test_media_actions_offer_classroom_quiz_and_test_prep():
    result = contract("What is this?", has_media=True, has_current_media=True)
    assert "Teach this in Classroom" in result.suggested_actions
    assert "Quiz me" in result.suggested_actions
    assert "I have a test on this" in result.suggested_actions


def test_classroom_handoff_preserves_course_workflow():
    result = contract("Teach this in Classroom", intent=Intent.COURSE, has_media=True)
    assert result.mode is InteractionMode.CREATE
    assert result.preserve_workflow is True
    assert result.fast_lane is False


def test_old_attachment_does_not_turn_unrelated_teaching_into_answer():
    result = contract("Teach me fractions", has_media=True, has_current_media=False)
    assert result.mode is InteractionMode.TEACH
    assert result.answer_first is False
    assert result.representation == "prose"
    assert result.requires_grounding is False


def test_old_attachment_does_not_ground_unrelated_direct_question():
    result = contract(
        "What is photosynthesis?",
        has_media=True,
        has_current_media=False,
    )
    assert result.mode is InteractionMode.ANSWER
    assert result.representation == "prose"
    assert result.requires_grounding is False


def test_electric_current_is_not_mistaken_for_current_events():
    result = contract("Explain electric current through a wire")
    assert result.mode is InteractionMode.EXPLAIN
    assert result.requires_grounding is False
    assert result.fast_lane is True


def test_current_price_still_uses_live_search():
    result = contract("What is the current price of gold?")
    assert result.mode is InteractionMode.SEARCH
    assert result.requires_grounding is True


@pytest.mark.asyncio
async def test_text_attachment_carries_source_section(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "settings", SimpleNamespace(upload_dir=str(tmp_path)))
    media_dir = tmp_path / "media" / "chat"
    media_dir.mkdir(parents=True)
    (media_dir / "notes.txt").write_text("Newton's second law is F = ma.", encoding="utf-8")
    parts = await load_media_attachments([
        MediaRef(
            modality=InputModality.DOCUMENT,
            uri="/api/v1/media/file/chat/notes.txt",
            mime_type="text/plain",
            name="notes.txt",
        )
    ])
    assert parts[0]["extracted_text"] == "Newton's second law is F = ma."
    assert parts[0]["source_sections"] == [{"label": "document", "text": "Newton's second law is F = ma."}]


def test_attachment_grounding_exposes_citable_labels():
    source_text, refs = _attachment_grounding([
        {"name": "lease.pdf", "source_sections": [
            {"label": "p. 1", "text": "Tenant: Alex"},
            {"label": "p. 2", "text": "Rent: $2,100"},
        ]}
    ])
    assert "[lease.pdf · p. 1]" in source_text
    assert "[lease.pdf · p. 2]" in source_text
    assert refs == [{"name": "lease.pdf", "label": "p. 1"}, {"name": "lease.pdf", "label": "p. 2"}]


def test_comparison_answer_becomes_table_smart_block():
    blocks = _presentation_blocks(
        "Key differences:\n\n| Feature | A | B |\n|---|---|---|\n| Speed | Fast | Slow |",
        "table",
    )
    assert any(block["type"] == "dataViz" and block["subtype"] == "table" for block in blocks)


def test_steps_answer_becomes_interactive_block():
    blocks = _presentation_blocks(
        "1. Gather the data: collect observations\n2. Analyze it: find the pattern\n3. Conclude: state the result",
        "steps",
    )
    assert len(blocks) == 1
    assert blocks[0]["type"] == "interactive"
    assert blocks[0]["subtype"] == "stepByStep"


def test_visual_answer_extracts_mermaid_diagram():
    blocks = _presentation_blocks(
        "A simple flow:\n```mermaid\ngraph LR\nA-->B\n```",
        "visual",
    )
    assert any(block["type"] == "dataViz" for block in blocks)
    diagram = next(block for block in blocks if block["type"] == "dataViz")
    assert "A-->B" in diagram["content"]["source"]
