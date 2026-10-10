"""Asking a provider to honour the schema, and never betting the lesson on it.

The classroom used to put its contract in the prompt and set the provider's
loose JSON mode, which means "reply with some JSON". A model that ignored the
contract produced output `model_validate_json` rejected, which is a rejected
turn, which is a retry, which is how a learner reaches a paused board.

Enforcing the schema closes that off — but only if the provider accepts the
dialect, and nothing in this repository can establish that. These tests cover
what is knowable offline: that the feature is off unless switched on, that a
rejection costs the old behaviour rather than the lesson, and that each
provider is handed the shape it actually understands.
"""

import pytest

from lyo_app.ai_classroom import adaptive_teaching
from lyo_app.ai_classroom.adaptive_teaching import (
    LOOSE_JSON, PracticeTurn, TeachingUnavailable, strict_response_format,
)


#: A task that satisfies the real contract, so these tests exercise the code
#: path under test rather than Pydantic rejecting a half-built fixture.
TASK = {
    "kind": "apply",
    "target_index": 0,
    "scenario": "Two friends split a pizza into four equal pieces and take one each.",
    "question": "How much of the pizza is left, and how do you know?",
    "response_hint": "Say the fraction and the reason in one sentence.",
    "criteria": ["names the fraction left", "explains how the equal pieces give it"],
    "example_answer": "Half, because they took two of the four equal pieces between them.",
}


@pytest.fixture
def contract():
    return PracticeTurn.model_json_schema()


def test_the_schema_is_only_enforced_once_someone_switches_it_on(monkeypatch, contract):
    """Off by default: a dialect no test here can verify must not ship enabled."""
    monkeypatch.delenv("CLASSROOM_STRICT_SCHEMA", raising=False)
    assert strict_response_format(PracticeTurn, contract) is None
    monkeypatch.setenv("CLASSROOM_STRICT_SCHEMA", "0")
    assert strict_response_format(PracticeTurn, contract) is None


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes", "on"])
def test_the_switch_reads_the_spellings_a_deploy_config_actually_uses(monkeypatch, contract, flag):
    monkeypatch.setenv("CLASSROOM_STRICT_SCHEMA", flag)
    enforced = strict_response_format(PracticeTurn, contract)
    assert enforced["type"] == "json_schema"
    assert enforced["json_schema"]["strict"] is True
    assert enforced["json_schema"]["name"] == "PracticeTurn"
    assert enforced["json_schema"]["schema"]["additionalProperties"] is False


def test_a_contract_that_cannot_be_enforced_asks_the_old_way(monkeypatch):
    """Not an error. A schema this cannot express is a schema the provider
    should be asked about loosely, exactly as it always was."""
    monkeypatch.setenv("CLASSROOM_STRICT_SCHEMA", "1")
    recursive = {"type": "object", "properties": {"child": {"$ref": "#/$defs/Node"}},
                 "$defs": {"Node": {"type": "object",
                                    "properties": {"child": {"$ref": "#/$defs/Node"}}}}}
    assert strict_response_format(PracticeTurn, recursive) is None


def test_only_an_actual_schema_rejection_is_read_as_one():
    """`is_fallback` means every provider was exhausted, for any reason.

    Only the last exception says whether the schema was refused or the
    providers were simply unreachable, and the two want opposite responses.
    """
    from lyo_app.ai_classroom.strict_schema import looks_like_schema_rejection

    for rejection in [
        "Error code: 400 - Invalid parameter: 'response_format' of type 'json_schema' is not supported",
        "Invalid schema for response_format 'PracticeTurn'",
        "GenerateContentRequest.generation_config.responseSchema: invalid schema",
        "GenerateContentRequest.generation_config.responseJsonSchema: invalid schema",
    ]:
        assert looks_like_schema_rejection(rejection), rejection

    for outage in [
        "Error code: 429 - Rate limit reached for gpt-4o-mini",
        "Error code: 401 - Incorrect API key provided",
        "Cannot connect to host generativelanguage.googleapis.com",
        "Circuit breaker is OPEN",
        "",
        None,
    ]:
        assert not looks_like_schema_rejection(outage), outage


@pytest.mark.asyncio
async def test_an_outage_is_not_retried_loosely(monkeypatch):
    """The cost of getting this wrong is paid by a learner who is waiting.

    Retrying an outage sends the identical request through the identical
    unhealthy providers: a 45-second classroom call becomes 90, and the extra
    load lands exactly when there is least to spare.
    """
    monkeypatch.setenv("CLASSROOM_STRICT_SCHEMA", "1")
    seen = []

    async def chat_completion(**kwargs):
        seen.append(kwargs["response_format"]["type"])
        return {"is_fallback": True, "content": "",
                "error": "Error code: 429 - Rate limit reached for gpt-4o-mini"}

    import lyo_app.core.ai_resilience as resilience
    monkeypatch.setattr(resilience.ai_resilience_manager, "chat_completion", chat_completion)

    with pytest.raises(TeachingUnavailable):
        await adaptive_teaching.model_json("system", {"a": 1}, PracticeTurn)
    assert seen == ["json_schema"], "an outage must cost one attempt, not two"


@pytest.mark.asyncio
async def test_a_provider_that_refuses_the_schema_costs_the_old_behaviour_not_the_lesson(monkeypatch):
    """The safety property the whole change rests on.

    A provider that rejects the dialect rejects every request carrying it, so
    retrying under the enforced contract retries the same rejection. One
    fallback to the loose mode bounds the worst case at how the classroom
    behaved before any of this, instead of at a teacher who cannot speak.
    """
    monkeypatch.setenv("CLASSROOM_STRICT_SCHEMA", "1")
    seen = []
    turn = PracticeTurn(
        speech="Let's try one together with the same method.",
        board_title="Your turn to apply it",
        board_content="Work out which of the two shares is larger, and say why.",
        task=TASK,
    )

    async def chat_completion(**kwargs):
        seen.append(kwargs["response_format"])
        if kwargs["response_format"]["type"] == "json_schema":
            return {"is_fallback": True, "content": "",
                    "error": "Error code: 400 - Invalid parameter: 'response_format' of type "
                             "'json_schema' is not supported with this model"}
        return {"content": turn.model_dump_json(), "model_used": "gpt-4o-mini", "tokens_used": 10}

    monkeypatch.setattr(adaptive_teaching, "ai_resilience_manager", None, raising=False)
    import lyo_app.core.ai_resilience as resilience
    monkeypatch.setattr(resilience.ai_resilience_manager, "chat_completion", chat_completion)

    result = await adaptive_teaching.model_json("system", {"a": 1}, PracticeTurn)

    assert [fmt["type"] for fmt in seen] == ["json_schema", "json_object"]
    assert result.board_title == "Your turn to apply it"


@pytest.mark.asyncio
async def test_a_working_schema_is_not_asked_for_twice(monkeypatch):
    monkeypatch.setenv("CLASSROOM_STRICT_SCHEMA", "1")
    seen = []
    turn = PracticeTurn(
        speech="Let's try one together with the same method.",
        board_title="Your turn to apply it",
        board_content="Work out which of the two shares is larger, and say why.",
        task=TASK,
    )

    async def chat_completion(**kwargs):
        seen.append(kwargs["response_format"])
        return {"content": turn.model_dump_json(), "model_used": "gpt-4o-mini", "tokens_used": 10}

    import lyo_app.core.ai_resilience as resilience
    monkeypatch.setattr(resilience.ai_resilience_manager, "chat_completion", chat_completion)

    await adaptive_teaching.model_json("system", {"a": 1}, PracticeTurn)
    assert [fmt["type"] for fmt in seen] == ["json_schema"]


def test_gemini_is_handed_the_schema_under_the_key_it_understands():
    """OpenAI's wrapper is what callers build; Gemini wants the bare schema
    under `responseJsonSchema`. Unwrapping it here is what keeps callers from
    having to know two dialects."""
    from lyo_app.core.ai_resilience import AIResilienceManager

    enforced = {"type": "object", "properties": {"a": {"type": "string"}},
                "required": ["a"], "additionalProperties": False}
    config = AIResilienceManager.apply_structured_output(
        {"maxOutputTokens": 100},
        {"type": "json_schema", "json_schema": {"name": "T", "schema": enforced, "strict": True}},
    )
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == enforced
    assert "responseSchema" not in config


def test_gemini_still_understands_a_plain_json_request():
    from lyo_app.core.ai_resilience import AIResilienceManager

    config = AIResilienceManager.apply_structured_output({"maxOutputTokens": 100}, LOOSE_JSON)
    assert config["responseMimeType"] == "application/json"
    assert "responseSchema" not in config
    assert "responseJsonSchema" not in config


def test_a_call_that_asked_for_no_particular_shape_is_left_alone():
    from lyo_app.core.ai_resilience import AIResilienceManager

    assert AIResilienceManager.apply_structured_output({"maxOutputTokens": 100}, None) == {
        "maxOutputTokens": 100
    }
