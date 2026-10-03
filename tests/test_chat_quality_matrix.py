"""Contract-level Chat quality matrix.

These scenarios are intentionally model-independent.  They guard the product
behaviours that should never depend on prompt luck: user-intent obedience,
planner/tool choice, response depth, representation choice, attachment
continuity, and memory-scope isolation.
"""

import pytest

from lyo_app.ai.schemas.lyo2 import Intent
from lyo_app.chat.experience import (
    InteractionMode,
    MemoryScope,
    ResponseDepth,
    ResponseRepresentation,
    resolve_interaction_contract,
)


SCENARIOS = [
    # text, router intent, expected mode, depth, representation, search
    ("What is a mitochondrion?", Intent.GENERAL, InteractionMode.ANSWER, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, False),
    ("Give me a brief definition of mitosis", Intent.GENERAL, InteractionMode.ANSWER, ResponseDepth.CONCISE, ResponseRepresentation.BULLETS, False),
    ("Explain gravity", Intent.EXPLAIN, InteractionMode.EXPLAIN, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, False),
    ("Go deeper on gravity", Intent.EXPLAIN, InteractionMode.EXPLAIN, ResponseDepth.DEEP, ResponseRepresentation.PROSE, False),
    ("Teach me fractions", Intent.EXPLAIN, InteractionMode.TEACH, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, False),
    ("Quiz me on fractions", Intent.EXPLAIN, InteractionMode.QUIZ, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, False),
    ("Compare mitosis vs meiosis", Intent.GENERAL, InteractionMode.COMPARE, ResponseDepth.STANDARD, ResponseRepresentation.TABLE, False),
    ("Show me a diagram of the water cycle", Intent.EXPLAIN, InteractionMode.EXPLAIN, ResponseDepth.STANDARD, ResponseRepresentation.DIAGRAM, False),
    ("Solve x + 4 = 9", Intent.GENERAL, InteractionMode.ANSWER, ResponseDepth.STANDARD, ResponseRepresentation.WORKED_EXAMPLE, False),
    ("Give me a timeline of the French Revolution", Intent.EXPLAIN, InteractionMode.EXPLAIN, ResponseDepth.STANDARD, ResponseRepresentation.TIMELINE, False),
    ("What is the latest NASA Artemis news?", Intent.GENERAL, InteractionMode.SEARCH, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, True),
    ("Search the web for current Python release", Intent.GENERAL, InteractionMode.SEARCH, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, True),
    ("continue", Intent.EXPLAIN, InteractionMode.CONTINUE, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, False),
    ("Create a course on geometry", Intent.GENERAL, InteractionMode.CREATE, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, False),
    ("Teach this in Classroom", Intent.EXPLAIN, InteractionMode.CREATE, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, False),
    ("Use this for Test Prep", Intent.EXPLAIN, InteractionMode.CREATE, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, False),
    ("Make flashcards about cells", Intent.GENERAL, InteractionMode.CREATE, ResponseDepth.STANDARD, ResponseRepresentation.PROSE, False),
]


@pytest.mark.parametrize(
    ("text", "intent", "mode", "depth", "representation", "requires_search"),
    SCENARIOS,
)
def test_chat_quality_matrix(
    text,
    intent,
    mode,
    depth,
    representation,
    requires_search,
):
    contract = resolve_interaction_contract(
        user_text=text,
        router_intent=intent,
        has_media="this" in text.lower(),
        has_current_media="this" in text.lower(),
    )

    assert contract.mode is mode
    assert contract.depth is depth
    assert contract.representation is representation
    assert contract.requires_search is requires_search


def test_unrelated_turn_does_not_pull_personal_memory():
    contract = resolve_interaction_contract(
        user_text="What is the capital of Peru?",
        router_intent=Intent.GENERAL,
    )
    assert contract.memory_scopes == [MemoryScope.WORKING]


def test_progress_request_can_use_measured_learner_memory():
    contract = resolve_interaction_contract(
        user_text="How am I doing in algebra?",
        router_intent=Intent.REFLECT,
    )
    assert MemoryScope.LEARNER in contract.memory_scopes
    assert MemoryScope.PERSONAL not in contract.memory_scopes


def test_explicit_prior_context_request_can_use_personal_memory():
    contract = resolve_interaction_contract(
        user_text="Remember what worked for me last time?",
        router_intent=Intent.GENERAL,
    )
    assert MemoryScope.PERSONAL in contract.memory_scopes


def test_new_attachment_analysis_is_not_a_quiz():
    contract = resolve_interaction_contract(
        user_text="what is this?",
        router_intent=Intent.EXPLAIN,
        has_media=True,
        has_current_media=True,
    )
    assert contract.mode is InteractionMode.ANALYZE
    assert contract.fast_lane is True
    assert "Quiz me on this" in contract.suggested_actions



def test_current_progress_is_learner_state_not_web_search():
    contract = resolve_interaction_contract(
        user_text="What is my current progress in algebra?",
        router_intent=Intent.REFLECT,
    )
    assert contract.requires_search is False
    assert contract.mode is InteractionMode.ANSWER
    assert MemoryScope.LEARNER in contract.memory_scopes
