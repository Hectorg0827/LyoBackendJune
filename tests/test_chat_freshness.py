from datetime import datetime, timezone

import pytest

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
        "trending news in dominixan republic",
        "Give me the news",
        "últimas noticias de República Dominicana",
        "pronóstico de hoy en Nueva York",
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


def test_current_lookup_follow_up_inherits_user_topic():
    history = [
        {"role": "user", "content": "Today's weather in New York"},
        {"role": "assistant", "content": "July 10: 85 degrees"},
    ]
    assert decide_freshness("What about Boston?", history).mode is FreshnessMode.REQUIRE
    assert decide_freshness("Try again", history).mode is FreshnessMode.REQUIRE
    assert decide_freshness("Write a poem", history).mode is FreshnessMode.NONE


def test_lookup_context_does_not_cross_subject_changes():
    history = [
        {"role": "user", "content": "Today's weather in New York"},
        {"role": "user", "content": "Explain fractions"},
    ]
    assert decide_freshness("What about Boston?", history).mode is FreshnessMode.ALLOW


def test_weather_city_reply_keeps_lookup_context():
    history = [
        {"role": "user", "content": "What is the weather today?"},
        {"role": "assistant", "content": "Which city or location should I check the weather for?"},
    ]
    assert decide_freshness("New York", history).mode is FreshnessMode.REQUIRE


def test_capability_and_definition_questions_do_not_trigger_a_forecast():
    for text in ("Bit how can you generare weather update", "What is weather?", "How do weather forecasts work?"):
        assert decide_freshness(text).mode is FreshnessMode.NONE
    assert decide_freshness("What is the weather today?").mode is FreshnessMode.REQUIRE


@pytest.mark.parametrize("query", [
    "Summarize the news article I attached",
    "Translate the weather forecast below",
    "Rewrite my news article",
    "Resume el artículo de noticias adjunto",
    "What does this uploaded document say about current regulations?",
])
def test_supplied_content_and_transformations_do_not_trigger_web_lookup(query):
    assert decide_freshness(query).mode is FreshnessMode.NONE


@pytest.mark.parametrize("query", [
    "Summarize the latest news in Dominican Republic",
    "Verify this attached article against current web sources",
    "What is the latest FastAPI version?",
    "Current iPhone pricing",
    "New research on batteries",
    "What are the visa requirements for Spain?",
])
def test_changing_information_requires_search_across_topics(query):
    assert decide_freshness(query).mode is FreshnessMode.REQUIRE


@pytest.mark.parametrize("query", [
    "Tell me about retrieval augmented generation",
    "Who invented the transistor?",
    "Compare Python and JavaScript",
])
def test_general_informational_questions_have_web_access(query):
    assert decide_freshness(query).mode is FreshnessMode.ALLOW


def test_general_information_follow_up_keeps_the_requested_topic():
    history = [{"role": "user", "content": "Tell me about retrieval augmented generation"}]
    assert decide_freshness("What about embeddings?", history).mode is FreshnessMode.ALLOW


def test_arithmetic_and_conversation_memory_do_not_search():
    assert decide_freshness("What is 2+2?").mode is FreshnessMode.NONE
    assert decide_freshness("What did I tell you about my preferences?").mode is FreshnessMode.NONE
    assert decide_freshness("How are you?").mode is FreshnessMode.NONE
