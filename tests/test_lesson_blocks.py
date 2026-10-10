import pytest
"""Lesson -> SmartBlock rendering, and the emit/grade round trip.

The round-trip test is the important one: it proves the blocks the stream
emits are the same shape the grading endpoint can read back, so the two sides
cannot drift into "the check renders but nothing can grade it".
"""

from lyo_app.ai.lesson_composer import ChatLesson
from lyo_app.api.v1.stream_lyo2 import (
    _check_evidence_contract,
    _find_check_block,
    _grade_check_block,
    _lesson_to_smart_blocks,
    _lesson_mode_for_teaching_action,
)
from lyo_app.teaching_runtime import TeachingAction


class _FakeMessage:
    def __init__(self, blocks):
        self.blocks = blocks


def _lesson():
    return ChatLesson(
        topic="square roots",
        skill_id="square_roots",
        is_probe=True,
        sections=[
            {"kind": "hook", "text": "What number times itself gives you this?"},
            {"kind": "core", "text": "A square root undoes squaring."},
            {"kind": "representation", "text": "A square of area 16 has side 4.",
             "latex": "\\sqrt{16}=4"},
            {"kind": "trap", "text": "sqrt(a+b) is not sqrt(a)+sqrt(b)."},
            {"kind": "reference", "text": "Perfect squares",
             "table_markdown": "| n | root |\n|---|---|\n| 49 | 7 |"},
        ],
        check={
            "question": "What is the square root of 49?",
            "options": [
                {"text": "7"},
                {"text": "9", "reveals": "confusing the root with a nearby square"},
                {"text": "Not sure — just explain it"},
            ],
            "correct_index": 0,
            "explanation": "7 x 7 = 49.",
            "bailout_index": 2,
        },
        next_directions=["estimate irrational roots", "why negatives have no real root"],
    )


def _by_subtype(blocks, subtype):
    return [b for b in blocks if b.get("subtype") == subtype]


def test_each_lesson_beat_becomes_its_own_block():
    blocks = _lesson_to_smart_blocks(_lesson())
    # Distinct blocks are what make a lesson scannable rather than a wall.
    assert _by_subtype(blocks, "hook")
    assert _by_subtype(blocks, "core")
    assert _by_subtype(blocks, "representation")


def test_trap_section_becomes_a_styled_callout():
    blocks = _lesson_to_smart_blocks(_lesson())
    callouts = _by_subtype(blocks, "callout")
    assert len(callouts) == 1
    assert callouts[0]["type"] == "text"
    assert callouts[0]["content"]["style"] == "trap"
    assert "sqrt(a+b)" in callouts[0]["content"]["text"]


def test_reference_section_becomes_a_table_block():
    blocks = _lesson_to_smart_blocks(_lesson())
    tables = _by_subtype(blocks, "table")
    assert len(tables) == 1
    assert tables[0]["content"]["format"] == "table"
    assert "| 49 | 7 |" in tables[0]["content"]["source"]


def test_latex_becomes_a_math_block_not_inline_text():
    blocks = _lesson_to_smart_blocks(_lesson())
    math = [b for b in blocks if b["content"].get("format") == "math"]
    assert len(math) == 1
    assert math[0]["content"]["source"] == "\\sqrt{16}=4"
    # The prose beside it must not carry raw delimiters.
    rep = _by_subtype(blocks, "representation")[0]
    assert "$" not in rep["content"]["text"]


def test_check_block_carries_skill_and_probe_metadata():
    blocks = _lesson_to_smart_blocks(_lesson())
    check = [b for b in blocks if b["type"] == "quiz"][0]
    assert check["metadata"]["skill_id"] == "square_roots"
    assert check["metadata"]["is_probe"] is True


def test_probe_check_has_server_owned_recognition_contract():
    blocks = _lesson_to_smart_blocks(_lesson(), target_evidence_type="transfer")
    check = [b for b in blocks if b["type"] == "quiz"][0]
    contract = check["metadata"]["evidence_contract"]
    assert contract["target_evidence_type"] == "recognition"
    assert contract["grading"] == "server"
    assert contract["award_condition"] == "correct"


def test_teach_check_can_target_transfer_but_caps_confidence():
    lesson = _lesson()
    lesson.is_probe = False
    lesson.check.bailout_index = None
    blocks = _lesson_to_smart_blocks(lesson, target_evidence_type="transfer")
    check = [b for b in blocks if b["type"] == "quiz"][0]
    contract = _check_evidence_contract(check)
    assert contract.target_evidence_type == "transfer"
    assert contract.confidence_cap == 0.8


def test_unsupported_quiz_contract_fails_safe_to_recognition():
    lesson = _lesson()
    lesson.is_probe = False
    lesson.check.bailout_index = None
    blocks = _lesson_to_smart_blocks(lesson, target_evidence_type="retention")
    check = [b for b in blocks if b["type"] == "quiz"][0]
    contract = _check_evidence_contract(check)
    assert contract.target_evidence_type == "application"


def test_check_block_carries_bounded_teaching_intervention():
    intervention = {
        "action": "guide",
        "reason_code": "developing_mastery",
        "target_evidence_type": "application",
        "preferred_instrument": "guided_attempt",
        "model_tier": "teaching",
        "policy_version": "learning-os-v1",
    }
    blocks = _lesson_to_smart_blocks(
        _lesson(),
        target_evidence_type="recognition",
        teaching_intervention=intervention,
    )
    check = [b for b in blocks if b["type"] == "quiz"][0]
    assert check["metadata"]["teaching_intervention"] == intervention


def test_check_block_preserves_distractor_reveals_and_bailout():
    blocks = _lesson_to_smart_blocks(_lesson())
    content = [b for b in blocks if b["type"] == "quiz"][0]["content"]
    assert content["correct_index"] == 0
    assert content["bailout_index"] == 2
    assert content["options"][1]["reveals"] == "confusing the root with a nearby square"
    assert content["options"][0]["reveals"] is None


def test_teach_lesson_without_a_bailout_emits_none():
    lesson = _lesson()
    lesson.is_probe = False
    lesson.check.bailout_index = None
    blocks = _lesson_to_smart_blocks(lesson)
    content = [b for b in blocks if b["type"] == "quiz"][0]["content"]
    assert content["bailout_index"] is None


def test_lesson_with_no_check_emits_no_quiz_block():
    lesson = _lesson()
    lesson.check = None
    blocks = _lesson_to_smart_blocks(lesson)
    assert not [b for b in blocks if b["type"] == "quiz"]


# --- the round trip ---------------------------------------------------------

def test_emitted_check_can_be_found_and_graded_by_the_endpoint():
    """What the stream emits must be exactly what the grader can read back."""
    blocks = _lesson_to_smart_blocks(_lesson())
    quiz = [b for b in blocks if b["type"] == "quiz"][0]

    # Exactly as the endpoint sees it: persisted on a message, looked up by id.
    found, skill_id = _find_check_block([_FakeMessage(blocks)], quiz["id"])
    assert found is not None
    assert skill_id == "square_roots"

    # The production bug, end to end: answering 9 must not be "correct".
    correct, bailed, misconception, correct_index, explanation = _grade_check_block(found, 1)
    assert correct is False
    assert bailed is False
    assert misconception == "confusing the root with a nearby square"
    assert correct_index == 0
    assert explanation == "7 x 7 = 49."

    # And the right answer still grades right.
    assert _grade_check_block(found, 0)[0] is True
    # And the opt-out is recognised as an opt-out.
    assert _grade_check_block(found, 2)[1] is True



def test_only_diagnose_can_fall_back_to_probe_mode():
    assert _lesson_mode_for_teaching_action(TeachingAction.DIAGNOSE) == "probe"
    for action in (
        TeachingAction.CHECK_RECALL,
        TeachingAction.CHECK_APPLICATION,
        TeachingAction.CHECK_TRANSFER,
        TeachingAction.REVIEW,
        TeachingAction.ADVANCE,
    ):
        assert _lesson_mode_for_teaching_action(action) == "teach"


def test_non_teaching_actions_do_not_start_structured_lesson_composition():
    assert _lesson_mode_for_teaching_action(TeachingAction.ANSWER) is None
    assert _lesson_mode_for_teaching_action(TeachingAction.PAUSE) is None


# --- visual teaching blocks --------------------------------------------------

def test_structural_representation_is_sent_as_renderable_mermaid():
    lesson = _lesson()
    lesson.is_probe = False
    diagram = "flowchart LR\n  A[Water evaporates] --> B[Clouds form]\n  B --> C[Rain]"
    lesson.sections[2].mermaid = diagram
    blocks = _lesson_to_smart_blocks(lesson)
    visuals = [b for b in blocks if b["type"] == "dataViz" and b["content"]["format"] == "mermaid"]
    assert len(visuals) == 1
    assert visuals[0]["content"]["source"] == diagram
    assert _by_subtype(blocks, "representation")[0]["content"]["text"]


def test_non_structural_or_injected_diagram_is_rejected_without_losing_prose():
    from lyo_app.api.v1.stream_lyo2 import _valid_teaching_mermaid
    assert _valid_teaching_mermaid("flowchart TD\n  A[Start] --> B[Finish]")
    assert not _valid_teaching_mermaid("\n\t  ")
    assert not _valid_teaching_mermaid("A[Start] --> B[Finish]")
    assert not _valid_teaching_mermaid('flowchart TD\nclick A "javascript:alert(1)"')
    assert not _valid_teaching_mermaid("%%{init:{}}%%\nflowchart TD\nA-->B")
    assert not _valid_teaching_mermaid("flowchart TD\n%%{init:{'securityLevel':'loose'}}%%\nA-->B")
    lesson = _lesson()
    lesson.sections[2].mermaid = "flowchart LR\n  A[<img src=x>]"
    blocks = _lesson_to_smart_blocks(lesson)
    assert not [b for b in blocks if b["content"].get("format") == "mermaid"]
    assert _by_subtype(blocks, "representation")


def test_verified_media_has_caption_and_is_supplementary_to_prose():
    lesson = _lesson()
    lesson.sections[2].image_query = "historical water cycle illustration"
    lesson.sections[2].image_url = "https://upload.wikimedia.org/example.jpg"
    lesson.sections[2].image_source_url = "https://commons.wikimedia.org/wiki/File:example.jpg"
    lesson.sections[2].image_attribution = "Wikimedia Commons / CC BY"
    blocks = _lesson_to_smart_blocks(lesson)
    photos = [b for b in blocks if b["type"] == "media"]
    assert len(photos) == 1
    assert photos[0]["subtype"] == "image"
    assert photos[0]["content"]["caption"] == "Wikimedia Commons / CC BY"
    assert photos[0]["metadata"]["source_url"].startswith("https://commons.wikimedia.org/")
    assert _by_subtype(blocks, "representation")
    lesson.sections[2].image_url = "https://arbitrary.example/unsourced.png"
    assert not [b for b in _lesson_to_smart_blocks(lesson) if b["type"] == "media"]
    lesson.sections[2].image_url = "https://images.pexels.com/photos/123/leaf.jpeg"
    lesson.sections[2].image_source_url = "https://www.pexels.com/photo/green-leaf-123/"
    lesson.sections[2].image_attribution = "Photo by Jane Artist on Pexels · Pexels License"
    approved = [b for b in _lesson_to_smart_blocks(lesson) if b["type"] == "media"]
    assert len(approved) == 1
    assert approved[0]["metadata"]["source_url"] == "https://www.pexels.com/photo/green-leaf-123/"
    lesson.sections[2].image_source_url = "https://untrusted.example/bad"
    assert not [b for b in _lesson_to_smart_blocks(lesson) if b["type"] == "media"]


# --- regression: real production text-only visual response (2026-10-08) ---

def test_optional_check_explanation_does_not_discard_structured_lesson():
    from lyo_app.ai.lesson_composer import CheckItem
    check = CheckItem.model_validate({
        "question": "What absorbs the sunlight in a leaf?",
        "options": [
            {"text": "Chlorophyll"}, {"text": "Nitrogen"},
            {"text": "Carbon dioxide"}, {"text": "I am not sure"},
        ],
        "correct_index": 0,
        "bailout_index": 3,
        # Omitted by the live provider; used to fail the entire ChatLesson.
    })
    assert check.explanation == "Correct answer: Chlorophyll"
    assert check.grade(1) is False
    assert check.grade(0) is True


def test_invalid_check_answer_key_still_rejected():
    from pydantic import ValidationError
    from lyo_app.ai.lesson_composer import CheckItem
    import pytest
    with pytest.raises(ValidationError):
        CheckItem.model_validate({
            "question": "Question?",
            "options": [{"text": "A"}, {"text": "B"}],
            "correct_index": 7,
        })


def test_explicit_visual_teaching_request_identified_and_topic_cleaned():
    from lyo_app.api.v1.stream_lyo2 import (
        _requested_teaching_visuals, _visual_lesson_topic,
    )
    text = "Teach me photosynthesis using a process-flow diagram and a real supporting image"
    assert _requested_teaching_visuals(text) == (True, True)
    assert _visual_lesson_topic(text) == "photosynthesis"
    assert _requested_teaching_visuals("Teach me photosynthesis without images") == (False, False)
    assert _requested_teaching_visuals("Teach me photosynthesis") == (False, False)
    assert _requested_teaching_visuals("Explain osmosis with a diagram") == (True, False)


def test_requested_diagram_is_grounded_in_actual_numbered_lesson_steps():
    from lyo_app.ai.lesson_composer import LessonSection
    from lyo_app.api.v1.stream_lyo2 import _complete_requested_lesson_visuals
    lesson = _lesson()
    lesson.topic = "photosynthesis"
    lesson.sections.append(LessonSection(
        kind="method",
        text=(
            "1. Chlorophyll captures sunlight\n"
            "2. Water splits, releasing oxygen\n"
            "3. Carbon is fixed into sugar\n"
        ),
    ))
    _complete_requested_lesson_visuals(lesson, diagram=True, image=True)
    blocks = _lesson_to_smart_blocks(lesson)
    diagrams = [block for block in blocks
                if block.get("type") == "dataViz" and
                block.get("content", {}).get("format") == "mermaid"]
    assert len(diagrams) == 1
    assert "Chlorophyll captures sunlight" in diagrams[0]["content"]["source"]
    assert "Carbon is fixed into sugar" in diagrams[0]["content"]["source"]
    assert lesson.sections[2].image_query == "photosynthesis"
    assert not [block for block in blocks if block["type"] == "media"]


def test_requested_visual_does_not_invent_unstated_process_steps():
    from lyo_app.api.v1.stream_lyo2 import _complete_requested_lesson_visuals
    lesson = _lesson()
    lesson.sections[2].mermaid = None
    _complete_requested_lesson_visuals(lesson, diagram=True, image=False)
    assert lesson.sections[2].mermaid is None


@pytest.mark.asyncio
async def test_visual_teaching_request_composer_receives_structured_visual_requirements(monkeypatch):
    from lyo_app.ai import lesson_composer
    prompts = []

    async def fake_generate(prompt):
        prompts.append(prompt)
        return {
            "sections": [
                {"kind": "core", "text": "Photosynthesis turns light into chemical energy."},
                {"kind": "representation", "text": "Light and water support sugar production."},
            ],
            "check": {
                "question": "What is captured by chlorophyll?",
                "options": [{"text": "Light"}, {"text": "Heat only"}],
                "correct_index": 0,
                # Production provider omits explanatory copy.
            },
        }

    monkeypatch.setattr(lesson_composer, "_generate_json", fake_generate)
    lesson = await lesson_composer.compose(
        "photosynthesis",
        mode="teach",
        requested_diagram=True,
        requested_image=True,
    )
    assert lesson is not None
    assert lesson.check.explanation == "Correct answer: Light"
    assert "VISUAL OUTPUT IS EXPLICITLY REQUESTED" in prompts[0]
    assert "image_query" in prompts[0]
    assert "mermaid" in prompts[0]


@pytest.mark.parametrize("user_text,expected", [
    ("Explain photosynthesis with diagrams and images", (True, True)),
    ("Explain photosynthesis with a diagram but don't use an image", (True, False)),
    ("Show me diagrams and photographs of the water cycle", (True, True)),
    ("Explain photosynthesis without using any pictures", (False, False)),
    ("Explain photosynthesis with a diagram, but do not show an image", (True, False)),
    ("Show me an image of photosynthesis without a flowchart", (False, True)),
    ("Explain photosynthesis without photos", (False, False)),
])
def test_visual_request_plurals_and_opt_outs(user_text, expected):
    from lyo_app.api.v1.stream_lyo2 import _requested_teaching_visuals
    assert _requested_teaching_visuals(user_text) == expected


@pytest.mark.parametrize("user_text,expected", [
    ("Show me a diagram of photosynthesis", "photosynthesis"),
    ("Draw a diagram of photosynthesis", "photosynthesis"),
    ("Can you explain photosynthesis using diagrams and images?", "photosynthesis"),
    ("Please visualize the water cycle with a flowchart", "the water cycle"),
    ("Could you draw a picture of a leaf?", "a leaf"),
    ("Explain osmosis with diagrams", "osmosis"),
])
def test_visual_lesson_topic_excludes_format_instructions(user_text, expected):
    from lyo_app.api.v1.stream_lyo2 import _visual_lesson_topic
    assert _visual_lesson_topic(user_text) == expected


def test_provider_null_explanation_recovers_without_losing_gradeable_lesson():
    from lyo_app.ai.lesson_composer import ChatLesson
    result = ChatLesson.model_validate({
        "topic": "photosynthesis", "skill_id": "photosynthesis",
        "sections": [{"kind": "representation", "text": "Light supports sugar formation."}],
        "check": {"question": "Which pigment absorbs light?",
                  "options": [{"text": "Chlorophyll"}, {"text": "Melanin"}],
                  "correct_index": 0, "explanation": None},
    })
    assert result.check.explanation == "Correct answer: Chlorophyll"
    assert result.check.grade(1) is False
