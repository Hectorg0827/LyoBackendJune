import pytest

from lyo_app.ai.executor import LyoExecutor, _source_descriptors
from lyo_app.ai.schemas.lyo2 import Intent
from lyo_app.teaching_runtime.interaction_contract import (
    DeliveryMode,
    InteractionMode,
    ResponseDepth,
    interaction_contract_for_request,
)
from lyo_app.teaching_runtime.models import (
    LearnerSnapshot,
    SessionSnapshot,
    TeachingAction,
    TeachingContext,
    TeachingSurface,
)
from lyo_app.teaching_runtime.policy import TeachingPolicy


def _policy_context(mode: str, depth: str = "standard") -> TeachingContext:
    return TeachingContext(
        intent="EXPLAIN",
        user_text="explain fractions",
        learner=LearnerSnapshot(
            concept_id="fractions",
            evidence_state="NOT_SEEN",
            attempts=0,
        ),
        session=SessionSnapshot(surface=TeachingSurface.CHAT),
        metadata={
            "interaction_mode": mode,
            "response_depth": depth,
            "has_media": False,
            "has_current_media": False,
        },
    )


@pytest.mark.parametrize(
    ("text", "has_media", "has_current", "mode", "fast"),
    [
        ("what is this?", True, True, InteractionMode.ANALYZE, True),
        ("summarize this PDF", True, True, InteractionMode.SUMMARIZE, True),
        ("compare these two ideas", False, False, InteractionMode.COMPARE, True),
        ("explain photosynthesis", False, False, InteractionMode.EXPLAIN, True),
        ("teach me fractions", False, False, InteractionMode.TEACH, False),
        ("quiz me on fractions", False, False, InteractionMode.QUIZ, False),
    ],
)
def test_interaction_contract_matches_explicit_user_goal(
    text, has_media, has_current, mode, fast
):
    contract = interaction_contract_for_request(
        text=text,
        has_media=has_media,
        has_current_media=has_current,
    )
    assert contract.mode is mode
    assert contract.fast_lane is fast


def test_explicit_explain_outranks_incorrect_routed_quiz_guess():
    contract = interaction_contract_for_request(
        text="explain photosynthesis",
        routed_intent=Intent.QUIZ,
    )

    assert contract.mode is InteractionMode.EXPLAIN
    assert contract.workflow_intent is None
    assert contract.reason_code == "explicit_explain"


def test_explicit_quiz_outranks_incorrect_routed_explain_guess():
    contract = interaction_contract_for_request(
        text="quiz me on photosynthesis",
        routed_intent=Intent.EXPLAIN,
    )

    assert contract.mode is InteractionMode.QUIZ
    assert contract.workflow_intent is Intent.QUIZ


def test_explicit_cross_surface_handoffs_own_the_turn():
    classroom = interaction_contract_for_request(
        text="Teach this in Classroom",
        routed_intent=Intent.CHAT,
        has_media=True,
    )
    prep = interaction_contract_for_request(
        text="Use this for Test Prep",
        routed_intent=Intent.CHAT,
        has_media=True,
    )

    assert classroom.workflow_intent is Intent.COURSE
    assert classroom.mode is InteractionMode.CREATE
    assert prep.workflow_intent is Intent.TEST_PREP
    assert prep.mode is InteractionMode.WORKFLOW


def test_depth_is_explicit_and_deterministic():
    deep = interaction_contract_for_request(text="go deeper")
    brief = interaction_contract_for_request(text="briefly explain gravity")

    assert deep.mode is InteractionMode.CONTINUE
    assert deep.depth is ResponseDepth.DEEP
    assert brief.depth is ResponseDepth.CONCISE


def test_direct_explanation_cannot_be_replaced_by_first_contact_quiz():
    decision = TeachingPolicy.decide(_policy_context("explain"))
    assert decision.action is TeachingAction.EXPLAIN
    assert decision.interaction_required is False
    assert decision.reason_code == "interaction_contract_explain"


def test_direct_answer_contract_cannot_be_replaced_by_first_contact_quiz():
    decision = TeachingPolicy.decide(_policy_context("answer"))
    assert decision.action is TeachingAction.ANSWER
    assert decision.interaction_required is False
    assert decision.reason_code == "interaction_contract_answer"


def test_deep_contract_expands_budget_without_changing_activity():
    standard = TeachingPolicy.decide(_policy_context("explain", "standard"))
    deep = TeachingPolicy.decide(_policy_context("explain", "deep"))

    assert deep.action is standard.action is TeachingAction.EXPLAIN
    assert deep.max_exposition_words > standard.max_exposition_words


def test_old_attachment_does_not_hijack_unrelated_teaching_request():
    contract = interaction_contract_for_request(
        text="teach me fractions",
        routed_intent=Intent.EXPLAIN,
        has_media=True,
        has_current_media=False,
    )
    assert contract.mode is InteractionMode.TEACH
    assert contract.attachment_authoritative is False


def test_source_descriptors_expose_locations_without_document_text():
    sources = _source_descriptors([
        {
            "name": "lease.pdf",
            "mime_type": "application/pdf",
            "page_count": 3,
            "source_pages": [
                {"page": 1, "text": "private contents"},
                {"page": 3, "text": "more private contents"},
            ],
            "uri": "/api/v1/media/file/chat/lease.pdf",
        }
    ])

    assert sources == [{
        "name": "lease.pdf",
        "mime_type": "application/pdf",
        "page_count": 3,
        "available_pages": [1, 3],
        "kind": "attachment",
        "url": "/api/v1/media/file/chat/lease.pdf",
    }]
    assert "private contents" not in str(sources)


def test_attachment_actions_create_real_learning_handoffs():
    executor = LyoExecutor.__new__(LyoExecutor)
    actions = executor._contextual_actions(
        "EXPLAIN",
        interaction_contract={"mode": "analyze"},
        has_media=True,
    )
    labels = actions[0].content["actions"]

    assert labels == [
        "Go Deeper",
        "Teach this in Classroom",
        "Use this for Test Prep",
    ]


def test_voice_uses_same_interaction_contract_with_spoken_delivery():
    contract = interaction_contract_for_request(
        text="explain photosynthesis",
        routed_intent=Intent.EXPLAIN,
        voice_mode=True,
    )

    assert contract.mode is InteractionMode.EXPLAIN
    assert contract.delivery_mode is DeliveryMode.VOICE
    assert contract.fast_lane is True


def test_voice_does_not_turn_answer_into_separate_voice_workflow():
    contract = interaction_contract_for_request(
        text="what is this?",
        routed_intent=Intent.EXPLAIN,
        has_media=True,
        has_current_media=True,
        voice_mode=True,
    )

    assert contract.mode is InteractionMode.ANALYZE
    assert contract.delivery_mode is DeliveryMode.VOICE
    assert contract.workflow_intent is None


def test_voice_prompt_is_spoken_friendly_without_changing_mode():
    from lyo_app.teaching_runtime.interaction_contract import contract_prompt

    contract = interaction_contract_for_request(
        text="compare mitosis and meiosis",
        voice_mode=True,
    )
    prompt = contract_prompt(contract)

    assert "Mode: compare" in prompt
    assert "Delivery: voice" in prompt
    assert "live spoken turn" in prompt
    assert "Do not announce" in prompt
