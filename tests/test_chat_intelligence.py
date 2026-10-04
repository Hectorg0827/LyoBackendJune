import pytest

from lyo_app.ai.chat_intelligence import (
    InteractionMode,
    ResponseDepth,
    contextual_action_labels,
    derive_interaction_contract,
    enforce_interaction_contract,
    memory_should_be_personalized,
    presentation_blocks,
)
from lyo_app.ai.schemas.lyo2 import Intent, RouterDecision


@pytest.mark.parametrize(
    "text,expected_mode,expected_intent,answer_first,fast_lane",
    [
        ("What is photosynthesis?", InteractionMode.ANSWER, Intent.EXPLAIN, True, True),
        ("Explain gravity", InteractionMode.EXPLAIN, Intent.EXPLAIN, True, True),
        ("Compare mitosis vs meiosis", InteractionMode.COMPARE, Intent.EXPLAIN, True, True),
        ("Summarize these notes", InteractionMode.SUMMARIZE, Intent.SUMMARIZE_NOTES, True, True),
        ("Teach me fractions", InteractionMode.TEACH, Intent.EXPLAIN, False, False),
        ("Quiz me on fractions", InteractionMode.QUIZ, Intent.QUIZ, False, False),
        ("I have a test Friday", InteractionMode.TEST_PREP, Intent.TEST_PREP, False, False),
        ("Create a course on geometry", InteractionMode.CREATE, Intent.COURSE, False, False),
    ],
)
def test_chat_quality_contract_matrix(
    text, expected_mode, expected_intent, answer_first, fast_lane
):
    contract = derive_interaction_contract(text)

    assert contract.mode is expected_mode
    assert contract.router_intent is expected_intent
    assert contract.answer_first is answer_first
    assert contract.fast_lane is fast_lane


def test_attachment_question_is_analysis_not_calibration():
    contract = derive_interaction_contract(
        "what is this?",
        has_media=True,
        has_current_media=True,
    )

    assert contract.mode is InteractionMode.ANALYZE
    assert contract.answer_first is True
    assert contract.allow_assessment is False
    assert contract.fast_lane is True
    assert contract.router_intent is Intent.EXPLAIN


def test_attachment_teach_transition_opens_classroom_workflow():
    contract = derive_interaction_contract(
        "Teach this",
        has_media=True,
        has_current_media=False,
    )

    assert contract.mode is InteractionMode.TEACH
    assert contract.reason == "attachment_to_classroom"
    assert contract.router_intent is Intent.COURSE
    assert contract.fast_lane is False


def test_attachment_test_prep_transition_owns_workflow():
    contract = derive_interaction_contract(
        "Use this for Test Prep",
        has_media=True,
        has_current_media=False,
    )

    assert contract.mode is InteractionMode.TEST_PREP
    assert contract.router_intent is Intent.TEST_PREP


def test_stale_attachment_cannot_hijack_unrelated_teaching():
    contract = derive_interaction_contract(
        "Teach me fractions",
        has_media=True,
        has_current_media=False,
    )

    assert contract.mode is InteractionMode.TEACH
    assert contract.reason == "explicit_teaching"
    assert contract.router_intent is Intent.EXPLAIN


def test_contract_overrides_router_that_wants_to_quiz_direct_question():
    router = RouterDecision(
        intent=Intent.QUIZ,
        confidence=0.75,
        needs_clarification=True,
        clarification_question="What level?",
        suggested_tier="MEDIUM",
    )
    contract = derive_interaction_contract("Why is the sky blue?")

    resolved = enforce_interaction_contract(router, contract)

    assert resolved.intent is Intent.EXPLAIN
    assert resolved.needs_clarification is False
    assert resolved.clarification_question is None
    assert resolved.confidence >= contract.confidence


@pytest.mark.parametrize(
    "text,depth",
    [
        ("Explain this briefly", ResponseDepth.CONCISE),
        ("Explain this", ResponseDepth.STANDARD),
        ("Give me a detailed deep dive on this", ResponseDepth.DEEP),
    ],
)
def test_response_depth_is_explicitly_adaptive(text, depth):
    assert derive_interaction_contract(text).response_depth is depth


def test_comparison_answer_gets_workspace_table_block():
    contract = derive_interaction_contract("Compare mitosis vs meiosis")
    answer = (
        "| Feature | Mitosis | Meiosis |\n"
        "|---|---|---|\n"
        "| Divisions | 1 | 2 |\n"
        "| Cells | 2 | 4 |"
    )

    blocks = presentation_blocks(
        contract=contract,
        answer_text=answer,
    )

    assert any(
        block.get("type") == "dataViz" and block.get("subtype") == "table"
        for block in blocks
    )


def test_document_answer_gets_source_workspace_block():
    contract = derive_interaction_contract(
        "what is this?",
        has_media=True,
        has_current_media=True,
    )

    blocks = presentation_blocks(
        contract=contract,
        answer_text="It is a payment record.",
        media_attachments=[
            {
                "name": "rent.pdf",
                "mime_type": "application/pdf",
                "source_pages": [
                    {"page": 1, "text": "Rent"},
                    {"page": 2, "text": "Payments"},
                ],
            }
        ],
    )

    source = next(block for block in blocks if block.get("subtype") == "notes")
    assert source["content"]["title"] == "Source material"
    assert source["content"]["items"][0]["label"] == "rent.pdf"
    assert "1" in source["content"]["items"][0]["detail"]
    assert "2" in source["content"]["items"][0]["detail"]


def test_followup_actions_connect_chat_to_learning_surfaces():
    contract = derive_interaction_contract(
        "summarize this",
        has_media=True,
        has_current_media=True,
    )

    actions = contextual_action_labels(contract, has_media=True)

    assert "Teach this" in actions
    assert "Use this for Test Prep" in actions


def test_personal_memory_is_selective_not_global():
    factual = derive_interaction_contract("What is the speed of light?")
    teaching = derive_interaction_contract("Teach me calculus")

    assert memory_should_be_personalized(factual, "What is the speed of light?") is False
    assert memory_should_be_personalized(teaching, "Teach me calculus") is True
    assert memory_should_be_personalized(
        factual,
        "Do you remember what I struggled with last time?",
    ) is True
