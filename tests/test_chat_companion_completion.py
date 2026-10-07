from types import SimpleNamespace

import pytest

from lyo_app.chat.document_grounding import (
    document_navigator_content,
    normalize_attachment_citations,
    source_descriptors,
)
from lyo_app.chat.representation import promote_answer_representations
from lyo_app.chat.response_depth import (
    apply_learned_depth,
    explicit_depth_preference,
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
    )

    assert result.checked is True
    assert result.revised is True
    assert result.text == "The verified value is 42."
