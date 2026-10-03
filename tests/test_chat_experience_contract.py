import pytest

from lyo_app.ai.schemas.lyo2 import Intent
from lyo_app.chat.experience import (
    InteractionMode,
    MemoryScope,
    ResponseDepth,
    ResponseRepresentation,
    effective_intent,
    fast_lane_plan,
    resolve_interaction_contract,
)


@pytest.mark.parametrize(
    ("text", "intent", "mode"),
    [
        ("what is this?", Intent.EXPLAIN, InteractionMode.EXPLAIN),
        ("Explain photosynthesis", Intent.EXPLAIN, InteractionMode.EXPLAIN),
        ("Teach me photosynthesis", Intent.EXPLAIN, InteractionMode.TEACH),
        ("Quiz me on photosynthesis", Intent.EXPLAIN, InteractionMode.QUIZ),
        ("Compare mitosis vs meiosis", Intent.GENERAL, InteractionMode.COMPARE),
        ("What is the latest NASA moon mission news?", Intent.GENERAL, InteractionMode.SEARCH),
        ("continue", Intent.EXPLAIN, InteractionMode.CONTINUE),
    ],
)
def test_contract_preserves_user_interaction_shape(text, intent, mode):
    contract = resolve_interaction_contract(
        user_text=text,
        router_intent=intent,
    )
    assert contract.mode is mode


def test_attachment_analysis_is_direct_and_source_oriented():
    contract = resolve_interaction_contract(
        user_text="analyze this",
        router_intent=Intent.EXPLAIN,
        has_media=True,
        has_current_media=True,
    )

    assert contract.mode is InteractionMode.ANALYZE
    assert contract.fast_lane is True
    assert contract.representation is ResponseRepresentation.DOCUMENT
    assert contract.suggested_actions == [
        "Explain deeper",
        "Teach this in Classroom",
        "Quiz me on this",
        "Use this for Test Prep",
    ]


def test_attachment_quiz_keeps_explicit_quiz_workflow():
    contract = resolve_interaction_contract(
        user_text="Quiz me on this PDF",
        router_intent=Intent.EXPLAIN,
        has_media=True,
        has_current_media=True,
    )

    assert contract.mode is InteractionMode.QUIZ
    assert contract.workflow_intent is Intent.QUIZ
    assert effective_intent(contract, Intent.EXPLAIN) is Intent.QUIZ
    assert contract.fast_lane is False


def test_classroom_transition_becomes_course_workflow():
    contract = resolve_interaction_contract(
        user_text="Teach this in Classroom",
        router_intent=Intent.EXPLAIN,
        has_media=True,
    )

    assert contract.mode is InteractionMode.CREATE
    assert contract.workflow_intent is Intent.COURSE
    assert effective_intent(contract, Intent.EXPLAIN) is Intent.COURSE


def test_test_prep_transition_becomes_test_prep_workflow():
    contract = resolve_interaction_contract(
        user_text="Use this for Test Prep",
        router_intent=Intent.EXPLAIN,
        has_media=True,
    )

    assert contract.workflow_intent is Intent.TEST_PREP
    assert effective_intent(contract, Intent.EXPLAIN) is Intent.TEST_PREP


def test_response_depth_obeys_explicit_control_then_state_preference():
    deep = resolve_interaction_contract(
        user_text="Go deeper on this",
        router_intent=Intent.EXPLAIN,
        state_summary={"chat_preferences": {"response_depth": "concise"}},
    )
    concise = resolve_interaction_contract(
        user_text="Explain this",
        router_intent=Intent.EXPLAIN,
        state_summary={"chat_preferences": {"response_depth": "concise"}},
    )

    assert deep.depth is ResponseDepth.DEEP
    assert concise.depth is ResponseDepth.CONCISE


def test_compare_prefers_table_and_skips_planner():
    contract = resolve_interaction_contract(
        user_text="Compare Python and JavaScript",
        router_intent=Intent.GENERAL,
    )

    assert contract.representation is ResponseRepresentation.TABLE
    assert contract.fast_lane is True


def test_current_info_uses_search_step_before_generation():
    contract = resolve_interaction_contract(
        user_text="What is the latest on the James Webb telescope?",
        router_intent=Intent.GENERAL,
    )
    plan = fast_lane_plan(contract, "What is the latest on the James Webb telescope?")

    assert contract.requires_search is True
    assert [step.action_type.value for step in plan.steps] == ["SEARCH_WEB", "GENERATE_TEXT"]


def test_personal_memory_is_selective_not_default():
    ordinary = resolve_interaction_contract(
        user_text="Explain gravity",
        router_intent=Intent.EXPLAIN,
    )
    remembered = resolve_interaction_contract(
        user_text="Remember what worked for me last time?",
        router_intent=Intent.GENERAL,
    )

    assert MemoryScope.PERSONAL not in ordinary.memory_scopes
    assert MemoryScope.PERSONAL in remembered.memory_scopes


def test_learner_memory_is_used_for_teaching_and_progress():
    teaching = resolve_interaction_contract(
        user_text="Teach me fractions",
        router_intent=Intent.EXPLAIN,
    )
    progress = resolve_interaction_contract(
        user_text="How am I doing in fractions?",
        router_intent=Intent.REFLECT,
    )

    assert MemoryScope.LEARNER in teaching.memory_scopes
    assert MemoryScope.LEARNER in progress.memory_scopes



@pytest.mark.asyncio
async def test_explicit_explain_contract_prevents_first_contact_probe():
    from lyo_app.teaching_runtime.models import TeachingAction
    from lyo_app.teaching_runtime.service import decide_for_chat

    contract = resolve_interaction_contract(
        user_text="Explain photosynthesis",
        router_intent=Intent.EXPLAIN,
    )
    decision = await decide_for_chat(
        db=None,
        user_id=None,
        user_text="Explain photosynthesis",
        intent="EXPLAIN",
        concept_id="photosynthesis",
        interaction_contract={
            **contract.model_dump(mode="json"),
            "directives": contract.prompt_directives(),
        },
    )

    assert decision.action is TeachingAction.EXPLAIN
    assert decision.interaction_required is False
    assert decision.reason_code == "interaction_contract_explain"


def test_source_manifest_keeps_document_pages_and_web_urls():
    from lyo_app.ai.executor import _source_manifest

    sources = _source_manifest(
        [
            {
                "name": "notes.pdf",
                "mime_type": "application/pdf",
                "source_pages": [
                    {"page": 1, "has_text": True},
                    {"page": 2, "has_text": True},
                ],
            }
        ],
        [
            {
                "title": "Example source",
                "url": "https://example.com/reference",
                "snippet": "Current fact",
            }
        ],
    )

    assert sources[0]["name"] == "notes.pdf"
    assert sources[0]["pages"] == [1, 2]
    assert sources[1]["kind"] == "web"
    assert sources[1]["url"] == "https://example.com/reference"



def test_server_depth_preference_merges_but_current_client_wins():
    from lyo_app.chat.experience import merged_chat_state

    stored = {"chat_preferences": {"response_depth": "deep"}, "server": "kept"}
    inherited = merged_chat_state({}, stored)
    overridden = merged_chat_state(
        {"chat_preferences": {"response_depth": "concise"}},
        stored,
    )

    assert inherited["chat_preferences"]["response_depth"] == "deep"
    assert overridden["chat_preferences"]["response_depth"] == "concise"
    assert overridden["server"] == "kept"


def test_depth_preference_update_reassigns_nested_json():
    from lyo_app.chat.experience import ResponseDepth, context_with_response_depth

    original = {"chat_preferences": {"response_depth": "standard"}, "other": 1}
    updated = context_with_response_depth(original, ResponseDepth.DEEP)

    assert updated is not original
    assert original["chat_preferences"]["response_depth"] == "standard"
    assert updated["chat_preferences"]["response_depth"] == "deep"
    assert updated["other"] == 1


def test_required_search_without_sources_forbids_claiming_current_verification():
    from lyo_app.ai.executor import _experience_prompt

    prompt = _experience_prompt(
        {
            "mode": "search",
            "depth": "standard",
            "representation": "prose",
            "requires_search": True,
        },
        {},
        [],
    )

    assert "No live-search sources were returned" in prompt
    assert "Do not present time-sensitive claims as verified or current" in prompt



@pytest.mark.parametrize(
    "text",
    [
        "What does this document say?",
        "Explain this PDF",
        "Summarize the attachment",
        "What is on page 2?",
        "Teach this in Classroom",
        "Use this for Test Prep",
        "Quiz me on this",
    ],
)
def test_explicit_attachment_followups_reuse_prior_media(text):
    from lyo_app.chat.experience import should_reuse_historical_media

    assert should_reuse_historical_media(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Teach me fractions",
        "What is the capital of Peru?",
        "Explain photosynthesis",
        "Compare Python and JavaScript",
    ],
)
def test_unrelated_turns_do_not_reuse_stale_media(text):
    from lyo_app.chat.experience import should_reuse_historical_media

    assert should_reuse_historical_media(text) is False



def test_study_plan_today_stays_a_study_plan_not_web_search():
    contract = resolve_interaction_contract(
        user_text="Create a study plan for today",
        router_intent=Intent.STUDY_PLAN,
    )

    assert contract.mode is InteractionMode.CREATE
    assert contract.workflow_intent is Intent.STUDY_PLAN
    assert contract.requires_search is False
    assert contract.fast_lane is False


def test_recent_progress_stays_learner_state_not_web_search():
    contract = resolve_interaction_contract(
        user_text="Show my recent progress in algebra",
        router_intent=Intent.REFLECT,
    )

    assert contract.mode is InteractionMode.ANSWER
    assert contract.requires_search is False
    assert MemoryScope.LEARNER in contract.memory_scopes


def test_required_search_with_only_document_source_still_warns_unverified():
    from lyo_app.ai.executor import _experience_prompt

    prompt = _experience_prompt(
        {
            "mode": "search",
            "depth": "standard",
            "representation": "document",
            "requires_search": True,
        },
        {},
        [{"kind": "document", "name": "notes.pdf", "pages": [1]}],
    )

    assert "No live-search sources were returned" in prompt
    assert "Non-web attachments or references do not satisfy live verification" in prompt
