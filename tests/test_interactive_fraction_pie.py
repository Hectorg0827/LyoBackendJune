"""Shared exploration in Chat, Classroom and Test Prep, independent of grading."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from lyo_app.ai.lesson_composer import ChatLesson, _drop_unusable_explorables
from lyo_app.ai.schemas.smart_block import SmartBlock
from lyo_app.ai_classroom.teaching_visuals import (
    TeachingVisual, complete_fraction_visuals, fraction_pie_from_text,
)
from lyo_app.api.v1 import stream_lyo2 as stream
from lyo_app.chat.representation import promote_answer_representations
from lyo_app.chat.visuals import update_visual_blocks


def pie(**changes):
    return TeachingVisual(**{
        "kind": "fraction_pie", "title": "Explore the fraction",
        "caption": "Tap slices or change the numerator and denominator.",
        "description": "One whole has four equal slices, with three shaded.",
        "parts": 4, "value": 3, **changes,
    })


@pytest.mark.parametrize("parts,value", [(1, 0), (1, 1), (20, 20), (4, 0)])
def test_pie_round_trips_zero_and_one_whole(parts, value):
    visual = pie(parts=parts, value=value)
    assert TeachingVisual.model_validate_json(visual.model_dump_json()) == visual


@pytest.mark.parametrize("parts,value", [(0, 0), (21, 0), (4, 5), (4, -1)])
def test_pie_rejects_impossible_state(parts, value):
    with pytest.raises(ValidationError):
        pie(parts=parts, value=value)


def test_denominator_and_numerator_save_atomically_with_a_text_equivalent():
    visual = pie()
    assert visual.update({"parts": 8, "value": 3})
    assert (visual.parts, visual.value, visual.whole) == (8, 3, 1)
    assert "3/8" in visual.description
    assert visual.update({"parts": 2, "value": 2})
    assert (visual.parts, visual.value) == (2, 2)


@pytest.mark.parametrize("values", [
    {}, [], {"parts": 2}, {"parts": 0, "value": 0}, {"parts": 21},
    {"parts": True}, {"value": False}, {"value": 1.5}, {"value": "2"},
    {"value": 5}, {"value": -1}, {"value": 2, "correct": True},
])
def test_invalid_or_grading_values_leave_both_controls_unchanged(values):
    visual = pie()
    before = visual.model_dump()
    assert not visual.update(values)
    assert visual.model_dump() == before


@pytest.mark.parametrize("text,expected", [
    ("The fraction 3/4 has three shaded slices.", (3, 4)),
    ("The fraction is 3/4.", (3, 4)),
    ("The fraction denominator is not a decimal: 3/4.5.", None),
    (r"The fraction \frac{2}{4} is one half.", (2, 4)),
    ("The fraction ¾ has three shaded slices.", (3, 4)),
    ("The fraction 0/5 has no shaded slices.", (0, 5)),
    ("The fraction 1/1 represents one whole.", (1, 1)),
    ("The fraction 5/4 is larger than one whole.", None),
    ("The mixed fraction 1 1/2 needs more than one pie.", None),
    ("The mixed fraction 1½ needs more than one pie.", None),
    (r"The mixed fraction 1 \frac{1}{2} needs two wholes.", None),
    ("The fraction − 1/2 is negative.", None),
    ("Fractions will be covered on 10/09/2026.", None),
    ("The meeting is on 3/4.", None),
])
def test_fallback_uses_only_a_supported_fraction_from_the_teaching_text(text, expected):
    visual = fraction_pie_from_text("", text)
    assert ((visual.value, visual.parts) if visual else None) == expected


def test_spanish_text_and_saved_description_keep_the_same_language():
    visual = fraction_pie_from_text("Fracciones", "La fracción 3/4 tiene tres partes sombreadas.")
    assert "numerador" in visual.caption
    assert visual.update({"parts": 8, "value": 3})
    assert visual.caption in visual.description
    assert "3/8" in visual.description


def test_updated_text_equivalent_preserves_authored_language_and_quantity():
    visual = pie(
        title="Les fractions de pommes",
        caption="Touchez les parts pour changer la fraction de pommes.",
        description="Trois quarts de douze pommes représentent neuf pommes.",
        whole=12, unit="pommes",
    )
    assert visual.update({"parts": 8, "value": 2})
    assert visual.caption in visual.description
    assert "2/8" in visual.description
    assert "12 pommes" in visual.description
    assert "3 pommes" in visual.description
    assert "shaded" not in visual.description
    assert "neuf" not in visual.description  # The old amount must not remain.
    assert TeachingVisual.model_validate(visual.model_dump()) == visual


def test_every_supported_pie_update_keeps_a_valid_bounded_text_equivalent():
    visual = pie(title="t" * 100, caption="c" * 350, unit="u" * 40, whole=1000000)
    for parts in range(1, 21):
        for value in range(parts + 1):
            assert visual.update({"parts": parts, "value": value})
            assert TeachingVisual.model_validate(visual.model_dump()) == visual
            assert f"{value}/{parts}" in visual.description


@pytest.mark.parametrize("content", [None, "Legacy plain text", ["legacy"], {"visual": None}])
def test_malformed_saved_visual_is_rejected_without_mutating_other_blocks(content):
    block = SmartBlock.teaching_visual(pie()).model_dump(mode="json")
    block["content"] = content
    before = deepcopy(block)
    with pytest.raises(ValueError):
        update_visual_blocks([block], block["id"], {"value": 1})
    assert block == before


def test_authored_classroom_visuals_are_preserved_and_missing_beats_get_a_pie():
    authored = pie(parts=8, value=2)
    turn = SimpleNamespace(visual=authored, board_content="Fraction 1/4", demonstration=[
        SimpleNamespace(visual=None, board_content="The fraction 2/4 is one half."),
    ])
    assert complete_fraction_visuals(turn, "Fractions") is turn
    assert turn.visual is authored
    assert turn.demonstration[0].visual.value == 2
    assert turn.demonstration[0].visual.parts == 4


def test_general_chat_gets_the_same_visual_without_replacing_its_explanation():
    answer = "The fraction 3/4 means three out of four equal parts."
    prose, blocks = promote_answer_representations(answer, interaction_mode="explain")
    assert prose == answer
    assert blocks[0]["subtype"] == "teaching_visual"
    assert blocks[0]["content"]["visual"]["kind"] == "fraction_pie"
    assert "evidence_contract" not in blocks[0]["metadata"]
    _, diagnostic = promote_answer_representations(answer, interaction_mode="diagnose")
    assert not any(b.get("subtype") == "teaching_visual" for b in diagnostic)


@pytest.mark.parametrize("surface", ["chat", "test_prep"])
def test_chat_and_test_prep_lessons_share_the_pie_and_keep_their_check(surface):
    lesson = ChatLesson(
        topic="Fractions", skill_id="fractions", is_probe=False,
        sections=[{"kind": "representation", "text": "The fraction 3/4 has three shaded slices."}],
        check={"question": "Which fraction means half?", "options": [{"text": "2/4"}, {"text": "3/4"}],
               "correct_index": 0, "explanation": "Two of four equal parts make half."},
        next_directions=["equivalent fractions", "compare fractions"],
    )
    blocks = stream._lesson_to_smart_blocks(lesson, source_surface=surface)
    visual = next(b for b in blocks if b.get("subtype") == "teaching_visual")
    assert visual["metadata"]["source_surface"] == surface
    assert (visual["content"]["visual"]["value"], visual["content"]["visual"]["parts"]) == (3, 4)
    assert any(b["type"] == "quiz" for b in blocks)
    lesson.is_probe = True
    assert not any(b.get("subtype") == "teaching_visual" for b in stream._lesson_to_smart_blocks(lesson))


def test_optional_invalid_visual_does_not_discard_a_usable_lesson():
    raw = {"sections": [{"kind": "representation", "text": "The fraction 3/4.",
                         "visual": {"kind": "fraction_pie", "parts": 0}}]}
    _drop_unusable_explorables(raw)
    assert raw == {"sections": [{"kind": "representation", "text": "The fraction 3/4."}]}


def test_saved_visual_update_preserves_quiz_results_and_rejects_answer_injection():
    visual = SmartBlock.teaching_visual(pie()).model_dump(mode="json")
    quiz = {"id": "quiz-1", "type": "quiz", "content": {"correct_index": 0},
            "metadata": {"result": {"correct": False, "selected_index": 1}}}
    original = [visual, quiz]
    before = deepcopy(original)
    updated, block = update_visual_blocks(original, visual["id"], {"parts": 8, "value": 3})
    assert original == before
    assert updated[1] == quiz
    assert block["content"]["visual"]["parts"] == 8
    assert "3/8" in block["content"]["items"][0]["detail"]
    with pytest.raises(ValueError):
        update_visual_blocks(original, visual["id"], {"value": 2, "correct_index": 1})
    with pytest.raises(LookupError):
        update_visual_blocks(original, "quiz-1", {"value": 2})


@pytest.mark.asyncio
async def test_visual_endpoint_enforces_owner_and_validates_updates_before_saving(monkeypatch):
    block = SmartBlock.teaching_visual(pie()).model_dump(mode="json")
    message = SimpleNamespace(role="assistant", blocks=[block])
    db = SimpleNamespace(commit=AsyncMock())
    owner = AsyncMock(return_value=SimpleNamespace(id="conversation-1"))
    monkeypatch.setattr(stream.conversation_store, "get_owned_conversation", owner)
    monkeypatch.setattr(stream.conversation_store, "get_messages", AsyncMock(return_value=[message]))
    app = FastAPI()
    app.include_router(stream.router, prefix="/api/v1/lyo2")
    app.dependency_overrides[stream.get_db] = lambda: db
    app.dependency_overrides[stream.get_current_user_or_guest] = lambda: SimpleNamespace(id=42)
    body = {"conversation_id": "conversation-1", "block_id": block["id"], "values": {"parts": 8, "value": 3}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/lyo2/chat/visual", json=body)
        assert response.status_code == 200
        assert response.json()["block"]["content"]["visual"]["parts"] == 8
        owner.assert_awaited_with(db, "conversation-1", "42")
        db.commit.assert_awaited_once()
        before = deepcopy(message.blocks)
        invalid = await client.post("/api/v1/lyo2/chat/visual", json={**body, "values": {"value": 9}})
        assert invalid.status_code == 422 and message.blocks == before
        db.commit.assert_awaited_once()
        owner.return_value = None
        other = await client.post("/api/v1/lyo2/chat/visual", json=body)
        assert other.status_code == 404
        app.dependency_overrides[stream.get_current_user_or_guest] = lambda: SimpleNamespace(id=0)
        guest = await client.post("/api/v1/lyo2/chat/visual", json=body)
        assert guest.status_code == 401
