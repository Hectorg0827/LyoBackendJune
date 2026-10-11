"""Display contracts: authored information survives, across subjects and rollout order."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from lyo_app.ai_classroom.board_presentation import BoardBlock, BoardDocument, board_document
from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import GuidedState, LearningPlan, LearningUnit
from lyo_app.ai_classroom.sdui_models import (
    ActionIntent, CTAButton, ExampleBlock, InputField, LessonBlock, Scene,
    SceneMetadata, SceneType, TeacherMessage,
)
from lyo_app.ai_classroom.teaching_visuals import TeachingVisual, VisualItem


@pytest.mark.parametrize("source,kind", [
    ("1. Subtract 5 from both sides.\n2. Divide both sides by 3.\n3. x = 4", "steps"),
    ("- Claim: cities expanded.\n- Evidence: census records.\n- Explain the link.", "bullets"),
    ("| Term | Meaning |\n| --- | --- |\n| Bonjour | Hello |\n| Merci | Thank you |", "table"),
    ("```sql\nSELECT name FROM employees;\n```", "code"),
    ("```python\n    return total\n```", "code"),
    ("$E = mc^2$ relates mass and energy.", "text"),
    ("葉は光を吸収する。", "text"),
])
def test_subject_independent_authored_structure(source, kind):
    document = board_document(source)
    assert document.blocks[0].kind == kind
    assert BoardDocument.model_validate(document.model_dump()) == document
    if kind == "code":
        assert document.blocks[0].text == source.splitlines()[1]


@pytest.mark.parametrize("source", [
    "```python\n    incomplete()",
    "| Column | Value |\n| --- | --- |\n| Missing cell |",
    "| Column | Value |\n| --- | --- |\n| | empty |",
    "4. A continued step\n5. Another step",
    "1. First step\n3. Missing second step",
])
def test_malformed_structure_remains_literal_source(source):
    document = board_document(source)
    assert document.blocks == [BoardBlock(kind="text", text=source)]


def test_mixed_teaching_tools_preserve_order_and_fragmented_source():
    source = "Observe the specimen.\n- Shape\n- Texture\n\n1. Compare\n2. Explain\n\n```text\nA → B\n```"
    assert [b.kind for b in board_document(source).blocks] == ["text", "bullets", "steps", "code"]
    fragmented = "\n".join(f"Heading {i}\n- Anchor {i}" for i in range(12))
    assert board_document(fragmented).blocks == [BoardBlock(kind="text", text=fragmented)]
    assert board_document(" ") is None
    assert board_document("x" * 1501) is None


def test_invalid_documents_cannot_request_arbitrary_executables_or_ragged_tables():
    with pytest.raises(ValidationError):
        BoardDocument(blocks=[{"kind": "script", "text": "execute()"}])
    with pytest.raises(ValidationError):
        BoardBlock(kind="table", headers=["A", "B"], rows=[["only A"]])
    with pytest.raises(ValidationError):
        BoardBlock(kind="steps", items=[" "])


def test_fenced_code_preserves_every_line_without_executing_it():
    authored = "    raise RuntimeError('display only')\n\n        return total  "
    source = "Before the example.\n```python\n" + authored + "\n```\nAfter the example."
    document = board_document(source)
    assert [block.kind for block in document.blocks] == ["text", "code", "text"]
    assert document.blocks[1].text == authored
    assert document.blocks[1].language == "python"


@pytest.mark.parametrize("columns,rows,kind", [
    (8, 1, "table"), (9, 1, "text"), (2, 20, "table"), (2, 21, "text"),
])
def test_table_limits_preserve_all_authored_cells(columns, rows, kind):
    headers = [f"H{index}" for index in range(columns)]
    values = [[f"{row}:{column}" for column in range(columns)] for row in range(rows)]
    source = "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * columns) + " |",
        *("| " + " | ".join(row) + " |" for row in values),
    ])
    document = board_document(source)
    assert document.blocks[0].kind == kind
    if kind == "table":
        assert document.blocks[0].headers == headers
        assert document.blocks[0].rows == values
    else:
        assert document.blocks == [BoardBlock(kind="text", text=source)]


@pytest.mark.parametrize("numbered", [False, True], ids=["bullets", "steps"])
@pytest.mark.parametrize("count", [20, 21])
def test_list_limit_keeps_the_final_item_and_authored_step_number(numbered, count):
    lines = [f"{index}. Item {index}" if numbered else f"- Item {index}"
             for index in range(1, count + 1)]
    document = board_document("\n".join(lines))
    assert document.blocks[0].items == [f"Item {index}" for index in range(1, 21)]
    if count == 21 and numbered:
        assert document.blocks[1] == BoardBlock(kind="text", text=lines[-1])
    elif count == 21:
        assert document.blocks[1].items == ["Item 21"]
    else:
        assert len(document.blocks) == 1


@pytest.mark.parametrize("payload", [
    {"version": 2, "blocks": [{"kind": "text", "text": "Future format"}]},
    {"blocks": []},
    {"blocks": [{"kind": "text", "text": "Anchor"}] * 21},
    {"blocks": [{"kind": "text", "text": "x" * 1501}]},
    {"blocks": [{"kind": "code", "text": "display()", "execute": True}]},
])
def test_invalid_wire_documents_are_rejected_by_the_production_contract(payload):
    with pytest.raises(ValidationError):
        BoardDocument.model_validate(payload)


def teaching_state():
    return GuidedState(owner="learner", plan=LearningPlan(units=[LearningUnit(
        title="Observe a system", objective="Explain the relationship between the input and output.",
        material="An input is changed by a process, producing an output.",
    )]))


def test_workspace_document_has_complete_legacy_and_accessibility_fallback():
    state = teaching_state()
    before = state.model_dump()
    context = SimpleNamespace(language_code="en-US", source_attributions=[])
    visual = TeachingVisual(kind="process_flow", title="The system", caption="Follow the change.",
        description="An input passes through a process to produce an output.",
        entries=[VisualItem(label="Input", detail="The raw material."), VisualItem(label="Output", detail="The result.")])
    content = "1. Identify the input.\n2. Describe the change."
    components = AdaptiveSession(None).surface(context, state, "Follow what changes as the input passes through.",
        "Observe the change", content, visual, "step-1")
    board = next(c for c in components if isinstance(c, ExampleBlock))
    assert board.presentation_role == "board"
    assert board.board_document.blocks[0].kind == "steps"
    assert board.content == content + "\n\n" + visual.description
    assert components[1].presentation_role == "narration"
    assert components[-1].presentation_role == "board"
    assert state.model_dump() == before  # display alone never grades or advances
    restored = ExampleBlock.model_validate(board.model_dump(mode="json"))
    assert restored.board_document == board.board_document
    old = ExampleBlock(title="Legacy board", content="Complete previous-version teaching content.")
    assert old.board_document is None


@pytest.mark.parametrize("language", ["en-US", "es-ES"])
@pytest.mark.parametrize("split_description", [False, True])
def test_full_scene_round_trip_keeps_narration_documents_visuals_and_legacy_content(
    language, split_description,
):
    state = teaching_state()
    prior = TeachingVisual(kind="fraction_bar", visual_id="prior-fraction",
        title="One third", caption="One of three equal pieces is shaded.",
        description="Three equal parts form the whole, and one part is shaded.", parts=3, value=1)
    state.board_memory = [{"title": "Earlier fraction", "content": "1/3 of the same whole",
                           "visual": prior.model_dump(mode="json")}]
    before = state.model_dump()
    context = SimpleNamespace(language_code=language, source_attributions=[])
    description = "Four equal parts form the whole; one part is shaded."
    if split_description:
        description = " ".join([description] * 10)
    visual = TeachingVisual(kind="fraction_bar", visual_id="current-fraction",
        title="One fourth", caption="Shade one of the four equal pieces.",
        description=description, parts=4, value=1)
    content = ("1. " + "First step. " * 45 + "\n2. " + "Next step. " * 45
               if split_description else "1. Divide the whole into four equal parts.\n2. Shade one part.")
    speech = "Compare these equal pieces of the same whole."
    components = AdaptiveSession(None).surface(
        context, state, speech, "Compare the parts", content, visual, "current-step",
    )
    scene = Scene(scene_type=SceneType.INSTRUCTION, components=components)
    restored = Scene.model_validate_json(scene.model_dump_json())
    assert restored == scene
    assert restored.metadata.presentation_focus == "board"
    by_id = {component.component_id: component for component in restored.components}
    board = by_id["board:current-step"]
    assert isinstance(board, ExampleBlock)
    assert board.board_document == board_document(content)
    assert board.presentation_role == "board" and board.language_code == language
    assert next(c.text for c in restored.components if isinstance(c, TeacherMessage)) == speech
    current_visual = by_id["visual:current-step"]
    assert isinstance(current_visual, LessonBlock)
    assert current_visual.presentation_role == "board"
    assert current_visual.block == visual.model_dump(mode="json")
    assert by_id["classroom-board-memory"].presentation_role == "reference"
    assert by_id["memory-visual:prior-fraction"].presentation_role == "reference"
    assert by_id["memory-visual:prior-fraction"].block == prior.model_dump(mode="json")
    if split_description:
        assert board.content == content
        assert next(c.content for c in restored.components if c.presentation_role == "details") == description
    else:
        assert board.content == content + "\n\n" + description
    assert state.model_dump() == before

    # A saved scene from before this contract still has every authored word.
    legacy = scene.model_dump(mode="json")
    legacy["metadata"].pop("presentation_focus")
    for component in legacy["components"]:
        component.pop("presentation_role")
        component.pop("board_document", None)
    old_scene = Scene.model_validate(legacy)
    assert old_scene.metadata.presentation_focus == "board"
    assert [c.content for c in old_scene.components if isinstance(c, ExampleBlock)] == [
        c.content for c in restored.components if isinstance(c, ExampleBlock)
    ]
    assert all(c.board_document is None for c in old_scene.components if isinstance(c, ExampleBlock))
    assert next(c for c in old_scene.components if c.component_id == "memory-visual:prior-fraction").presentation_role == "reference"


@pytest.mark.parametrize("language", ["en-US", "es-ES"])
def test_recovery_scene_round_trip_keeps_the_document_and_retry_action(language):
    state = teaching_state()
    context = SimpleNamespace(language_code=language, source_attributions=[], lesson_content="")
    components = AdaptiveSession(None).surface(context, state,
        "Keep this worked example in view.", "The example", "1. Compare.\n2. Explain.")
    state.scene = Scene(scene_type=SceneType.INSTRUCTION, components=components).model_dump(mode="json")
    before = state.model_dump()
    failed = AdaptiveSession(None).unavailable(context, state)
    restored = Scene.model_validate_json(failed.model_dump_json())
    assert restored.metadata.presentation_focus == "recovery"
    retained = next(c for c in restored.components if c.component_id == "board:" + state.step_id)
    assert retained.board_document == board_document("1. Compare.\n2. Explain.")
    assert retained.content == "1. Compare.\n2. Explain."
    notice = next(c for c in restored.components if c.component_id == "classroom-recovery/notice")
    assert notice.presentation_role == "recovery" and notice.content
    assert next(c for c in restored.components if isinstance(c, CTAButton)).action_intent == ActionIntent.RETRY
    assert state.model_dump() == before


def test_explicit_scene_focus_survives_serialization_with_a_practice_component():
    task = InputField(question="Explain the relationship.", placeholder="Your explanation")
    scene = Scene(scene_type=SceneType.INSTRUCTION, components=[task],
                  metadata=SceneMetadata(presentation_focus="conversation"))
    assert Scene.model_validate_json(scene.model_dump_json()).metadata.presentation_focus == "conversation"


def test_scene_focus_prioritizes_recovery_then_practice():
    task = InputField(question="Explain the result in your own words.", placeholder="Your explanation")
    scene = Scene(scene_type=SceneType.INSTRUCTION, components=[task])
    assert scene.metadata.presentation_focus == "practice"
    scene = Scene(scene_type=SceneType.INSTRUCTION, components=[task, ExampleBlock(
        component_id="classroom-recovery/notice", title="Paused", content="Retry this step to carry on.", presentation_role="recovery")])
    assert scene.metadata.presentation_focus == "recovery"
