"""Display contracts: authored information survives, across subjects and rollout order."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from lyo_app.ai_classroom.board_presentation import BoardBlock, BoardDocument, board_document
from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import GuidedState, LearningPlan, LearningUnit
from lyo_app.ai_classroom.sdui_models import ExampleBlock, InputField, Scene, SceneType
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


def test_scene_focus_prioritizes_recovery_then_practice():
    task = InputField(question="Explain the result in your own words.", placeholder="Your explanation")
    scene = Scene(scene_type=SceneType.INSTRUCTION, components=[task])
    assert scene.metadata.presentation_focus == "practice"
    scene = Scene(scene_type=SceneType.INSTRUCTION, components=[task, ExampleBlock(
        component_id="classroom-recovery/notice", title="Paused", content="Retry this step to carry on.", presentation_role="recovery")])
    assert scene.metadata.presentation_focus == "recovery"
