from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher,
    GuidedState,
    LearningPlan,
    LearningUnit,
    TeachingBeat,
)
from lyo_app.ai_classroom.teaching_visuals import TeachingVisual, VisualItem


def base_fields(kind: str):
    return dict(
        kind=kind,
        title="Visual teaching example",
        caption="Look at the relationship before answering the next question.",
        description="A text equivalent describing the important visual relationship.",
    )


def test_richer_visual_contract_accepts_diagrams_timelines_number_lines_and_real_images():
    process = TeachingVisual(
        **base_fields("process_flow"),
        entries=[
            VisualItem(label="Input", detail="Raw material enters the system."),
            VisualItem(label="Transform", detail="The system changes the material."),
            VisualItem(label="Output", detail="A new result leaves the system."),
        ],
        value=1,
    )
    timeline = TeachingVisual(
        **base_fields("timeline"),
        entries=[
            VisualItem(label="1900", detail="The starting event."),
            VisualItem(label="1950", detail="The transition event."),
            VisualItem(label="2000", detail="The later event."),
        ],
    )
    number_line = TeachingVisual(
        **base_fields("number_line"),
        x_min=-10,
        x_max=10,
        entries=[
            VisualItem(label="-5", detail="Five units below zero.", position=-5),
            VisualItem(label="0", detail="The origin.", position=0),
            VisualItem(label="7", detail="Seven units above zero.", position=7),
        ],
        value=1,
    )
    image = TeachingVisual(
        **base_fields("annotated_image"),
        image_query="human heart anatomy",
        image_url="https://upload.wikimedia.org/example/heart.jpg",
        source_url="https://commons.wikimedia.org/wiki/File:Heart.jpg",
        attribution="File:Heart.jpg",
        entries=[
            VisualItem(label="Ventricle", detail="Lower pumping chamber.", x=0.55, y=0.72),
        ],
    )

    assert process.kind == "process_flow"
    assert timeline.kind == "timeline"
    assert number_line.entries[2].position == 7
    assert image.image_url.startswith("https://upload.wikimedia.org/")
    assert len({process.visual_id, timeline.visual_id, number_line.visual_id, image.visual_id}) == 4


def test_visual_contract_has_no_video_or_youtube_kind():
    policy = AdaptiveTeacher.visual_policy_for("orient", "worked_example")
    assert policy["mode"] == "preferred"
    assert "video" not in policy["allowed"]
    assert "youtube" not in policy["allowed"]

    with pytest.raises(ValidationError):
        TeachingVisual(**base_fields("video"))


def test_annotated_images_reject_model_invented_media_hosts():
    with pytest.raises(ValidationError):
        TeachingVisual(
            **base_fields("annotated_image"),
            image_query="human heart anatomy",
            image_url="https://example.com/invented.jpg",
        )


def test_visual_board_memory_reemits_the_latest_prior_visual():
    plan = LearningPlan(units=[
        LearningUnit(
            title="Understand a simple system",
            objective="Explain how an input changes as it moves through a simple system.",
            material="A system receives an input, transforms it through a process, and produces an output.",
        ),
    ])
    state = GuidedState(owner="learner", plan=plan)
    visual = TeachingVisual(
        **base_fields("process_flow"),
        entries=[
            VisualItem(label="Input", detail="Material enters."),
            VisualItem(label="Process", detail="Material changes."),
            VisualItem(label="Output", detail="Result leaves."),
        ],
    )
    prior = TeachingBeat(
        speech="Follow this system from the input through the change to the output.",
        board_title="System flow",
        board_content="Input → process → output",
        visual=visual,
    )
    current = TeachingBeat(
        speech="Now use that same flow to think about a different system.",
        board_title="New example",
        board_content="Apply the same three-part structure to a new case.",
    )
    AdaptiveSession.remember_beat(state, prior)
    AdaptiveSession.remember_beat(state, current)

    context = SimpleNamespace(
        language_code="en-US",
        source_attributions=[],
    )
    components = AdaptiveSession(None).surface(
        context,
        state,
        current.speech,
        current.board_title,
        current.board_content,
        current.visual,
        "current",
    )
    memory_visuals = [
        component for component in components
        if getattr(component, "block_type", None) == "teaching_visual"
        and component.component_id.startswith("memory-visual:")
    ]
    assert len(memory_visuals) == 1
    assert memory_visuals[0].block["visual_id"] == visual.visual_id
    assert memory_visuals[0].block["kind"] == "process_flow"
