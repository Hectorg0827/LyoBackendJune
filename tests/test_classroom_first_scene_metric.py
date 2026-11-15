"""Measure authoritative Classroom startup separately from instant local practice.

No learner identifiers, topics, answers, request bodies or audio are labels.
"""

from prometheus_client import generate_latest

from lyo_app.ai_classroom.websocket_routes import classroom_first_scene_seconds


def test_first_scene_latency_metric_has_only_fixed_outcome_label():
    assert tuple(classroom_first_scene_seconds._labelnames) == ("outcome",)
    metric = classroom_first_scene_seconds.labels("success")
    before = metric._sum.get()
    metric.observe(2.5)
    assert metric._sum.get() == before + 2.5

    exported = generate_latest(classroom_first_scene_seconds)
    assert b'outcome="success"' in exported
    assert b"learner_id" not in exported
    assert b"session_id" not in exported
    assert b"topic" not in exported
