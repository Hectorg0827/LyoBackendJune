"""Classroom speech performance metrics never contain student material."""

from prometheus_client import generate_latest

from lyo_app.tts.routes import (
    classroom_tts_full_synthesis_seconds,
    classroom_tts_stream_first_byte_seconds,
)


def test_full_tts_timing_has_no_private_or_unbounded_labels():
    metric = classroom_tts_full_synthesis_seconds
    assert tuple(metric._labelnames) == ("outcome",)
    before = metric.labels("success")._sum.get()
    metric.labels("success").observe(1.75)
    assert metric.labels("success")._sum.get() == before + 1.75
    rendered = generate_latest(metric)
    for secret_label in (b"text=", b"learner=", b"user_id=", b"voice=", b"session="):
        assert secret_label not in rendered


def test_stream_first_byte_metric_tracks_success_separately():
    metric = classroom_tts_stream_first_byte_seconds
    assert tuple(metric._labelnames) == ("outcome",)
    before = metric.labels("success")._sum.get()
    metric.labels("success").observe(0.25)
    assert metric.labels("success")._sum.get() == before + 0.25
    assert b'outcome="success"' in generate_latest(metric)
