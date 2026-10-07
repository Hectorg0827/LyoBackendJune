import pytest
from unittest.mock import AsyncMock, MagicMock

from lyo_app.chat.document_grounding import (
    document_navigator_content,
    normalize_attachment_citations,
    source_descriptors,
)
from lyo_app.chat.representation import promote_answer_representations
from lyo_app.chat.response_depth import (
    apply_learned_depth,
    explicit_depth_preference,
    learned_depth_for_user,
    record_explicit_depth_preference,
)
from lyo_app.chat.verification import (
    selectively_verify_answer,
    should_verify_answer,
)
from lyo_app.teaching_runtime.interaction_contract import (
    InteractionMode,
    ResponseDepth,
    interaction_contract_for_request,
)


def _pdf():
    return {
        "name": "lease.pdf",
        "mime_type": "application/pdf",
        "page_count": 4,
        "uri": "/api/v1/media/file/chat/lease.pdf",
        "source_pages": [
            {"page": 1, "text": "Rent is due on the first."},
            {"page": 3, "text": "Late fee is $50."},
        ],
    }


def test_spanish_explain_request_keeps_explain_mode_and_concise_depth():
    contract = interaction_contract_for_request(
        text="Explícame brevemente qué es la gravedad."
    )
    assert contract.mode is InteractionMode.EXPLAIN
    assert contract.depth is ResponseDepth.CONCISE


def test_current_information_is_an_explicit_search_contract():
    contract = interaction_contract_for_request(
        text="Who is the current president of France?"
    )
    assert contract.mode is InteractionMode.SEARCH
    assert contract.fast_lane is False


def test_document_grounding_preserves_only_real_page_citations():
    text = "Rent is due monthly 【lease.pdf p. 1】 and fee is listed 【lease.pdf p. 2】."
    normalized = normalize_attachment_citations(text, [_pdf()])

    assert "【lease.pdf p. 1】" in normalized
    assert "【lease.pdf p. 2】" not in normalized
    assert "【lease.pdf】" in normalized


def test_document_navigator_exposes_pages_and_four_document_actions_without_text():
    descriptor = source_descriptors([_pdf()])[0]
    navigator = document_navigator_content([_pdf()])

    assert descriptor["available_pages"] == [1, 3]
    assert "Rent is due" not in str(descriptor)
    assert navigator["title"] == "Document navigator"
    assert navigator["quick_actions"] == [
        "Summarize this document",
        "Show key dates",
        "Show key numbers",
        "Ask about a page",
    ]
    assert navigator["items"][0]["available_pages"] == [1, 3]


def test_learned_depth_applies_only_when_user_did_not_override_it():
    neutral = interaction_contract_for_request(text="Explain gravity")
    # Explain is explicit interaction mode, but has standard depth unless the
    # learner states a depth preference.
    adapted = apply_learned_depth(
        neutral,
        user_text="Explain gravity",
        learned=ResponseDepth.DEEP,
    )
    assert adapted.mode is InteractionMode.EXPLAIN
    assert adapted.depth is ResponseDepth.DEEP

    explicit = interaction_contract_for_request(text="Briefly explain gravity")
    preserved = apply_learned_depth(
        explicit,
        user_text="Briefly explain gravity",
        learned=ResponseDepth.DEEP,
    )
    assert explicit_depth_preference("Briefly explain gravity") is ResponseDepth.CONCISE
    assert preserved.depth is ResponseDepth.CONCISE


@pytest.mark.asyncio
async def test_explicit_depth_requires_repetition_before_becoming_durable():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    no_durable = MagicMock()
    no_durable.scalar_one_or_none.return_value = None
    no_signals = MagicMock()
    no_signals.scalars.return_value.all.return_value = []
    db.execute.side_effect = [no_durable, no_signals]

    saved = await record_explicit_depth_preference(
        db,
        7,
        "Please be concise.",
        source_session_id="turn-1",
    )
    assert saved is ResponseDepth.CONCISE
    added_categories = [call.args[0].category for call in db.add.call_args_list]
    assert added_categories == ["response_depth_signal"]
    db.commit.assert_awaited_once()

    db.execute.reset_mock()
    db.add.reset_mock()
    db.commit.reset_mock()

    prior_signal = MagicMock()
    prior_signal.insight_text = "Requested response depth: concise"
    prior_signals = MagicMock()
    prior_signals.scalars.return_value.all.return_value = [prior_signal]
    db.execute.side_effect = [no_durable, prior_signals]

    await record_explicit_depth_preference(
        db,
        7,
        "Keep it concise.",
        source_session_id="turn-2",
    )
    added = [call.args[0] for call in db.add.call_args_list]
    assert [row.category for row in added] == [
        "response_depth_signal",
        "response_depth",
    ]
    assert added[-1].insight_text == "Preferred response depth: concise"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_learned_depth_reads_only_durable_preference():
    db = MagicMock()
    db.execute = AsyncMock()
    row = MagicMock()
    row.insight_text = "Preferred response depth: deep"
    found = MagicMock()
    found.scalar_one_or_none.return_value = row
    db.execute.return_value = found

    assert await learned_depth_for_user(db, 7) is ResponseDepth.DEEP


def test_representation_promotion_turns_table_and_mermaid_into_workspace_blocks():
    answer = """The comparison is:

| A | B |
| --- | --- |
| Fast | Slow |

```mermaid
flowchart LR
A --> B
```
"""
    prose, blocks = promote_answer_representations(answer, interaction_mode="compare")

    assert "| A | B |" not in prose
    assert "flowchart LR" not in prose
    assert [block["type"] for block in blocks] == ["dataViz", "dataViz"]
    assert blocks[0]["content"]["format"] == "mermaid"
    assert blocks[1]["content"]["format"] == "table"


def test_representation_promotion_creates_timeline_and_math_blocks():
    answer = """2024 - Foundation launched
2025 - Pilot expanded

The relationship is:

$E = mc^2$
"""
    prose, blocks = promote_answer_representations(answer, interaction_mode="explain")

    assert "2024 - Foundation launched" not in prose
    assert "$E = mc^2$" not in prose
    assert any(block.get("subtype") == "timeline" for block in blocks)
    assert any(
        block.get("type") == "dataViz"
        and block.get("content", {}).get("format") == "math"
        for block in blocks
    )


def test_compare_always_has_a_structured_representation_even_if_model_used_prose():
    prose, blocks = promote_answer_representations(
        "Mitosis produces two similar cells. Meiosis produces four genetically varied cells.",
        interaction_mode="compare",
    )

    assert prose == ""
    assert any(block.get("subtype") == "comparison" for block in blocks)


def test_verification_gate_skips_simple_turns_and_selects_risky_factual_turns():
    assert not should_verify_answer(
        question="Define inertia.",
        answer="Inertia is an object's resistance to changes in its motion.",
        interaction_mode="answer",
    )
    assert should_verify_answer(
        question="What is the current version and price today?",
        answer="The current version is 12.4 and the current price is $499 according to today's listing.",
        interaction_mode="search",
        search_required=True,
    )


@pytest.mark.asyncio
async def test_selective_critic_can_replace_a_materially_wrong_answer(monkeypatch):
    from lyo_app.core.ai_resilience import ai_resilience_manager

    async def fake_chat_completion(**kwargs):
        return {"content": "REVISED:\nThe verified value is 42."}

    monkeypatch.setattr(ai_resilience_manager, "chat_completion", fake_chat_completion)

    result = await selectively_verify_answer(
        question="What is the current value today?",
        answer="The current value is 41, according to today's source listing and supporting technical analysis.",
        interaction_mode="search",
        search_required=True,
        sources=[
            {
                "title": "Fresh source",
                "url": "https://example.test/current",
                "snippet": "The current verified value is 42.",
            }
        ],
    )

    assert result.checked is True
    assert result.revised is True
    assert result.text == "The verified value is 42."
