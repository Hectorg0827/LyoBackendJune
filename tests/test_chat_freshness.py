from datetime import datetime, timezone

from lyo_app.chat.freshness import (
    FreshnessMode,
    current_time_context,
    decide_freshness,
)


def test_current_requests_require_search():
    for text in (
        "What happened with Nvidia today?",
        "Who is the current president of France?",
        "What's the score right now?",
        "Look this up on the web",
    ):
        assert decide_freshness(text).mode is FreshnessMode.REQUIRE


def test_factual_questions_allow_model_search_without_forcing_it():
    assert decide_freshness("Who invented the transistor?").mode is FreshnessMode.ALLOW
    assert decide_freshness("Is Pluto a planet?").mode is FreshnessMode.ALLOW


def test_creative_and_workflow_requests_do_not_pay_search_cost():
    assert decide_freshness("Write me a poem about Saturn").mode is FreshnessMode.NONE
    assert decide_freshness("Create a course on marketing").mode is FreshnessMode.NONE


def test_current_time_context_uses_client_timezone():
    now = datetime(2026, 10, 4, 19, 12, tzinfo=timezone.utc)
    value = current_time_context("America/New_York", now=now)
    assert "2026-10-04T15:12:00-04:00" in value
    assert "America/New_York" in value
