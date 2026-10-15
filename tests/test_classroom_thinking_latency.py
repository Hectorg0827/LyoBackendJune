"""Keep immediate authoring inside its deadline without weakening assessment."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_teaching import model_json
from lyo_app.core.ai_resilience import AIModelConfig, AIResilienceManager
from scripts.validate_classroom_recovery import contract_examples


EXAMPLES = list(contract_examples().items())


@pytest.mark.asyncio
@pytest.mark.parametrize("schema,example", EXAMPLES, ids=[schema.__name__ for schema, _ in EXAMPLES])
async def test_real_contracts_keep_validation_and_assessment_reasoning(monkeypatch, schema, example):
    completion = AsyncMock(return_value={
        "model_used": "gemini-3.8-flash", "content": example.model_dump_json(),
    })
    monkeypatch.setenv("CLASSROOM_STRICT_SCHEMA", "0")
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    result = await model_json("Author the requested lesson move.", {"move": "test"}, schema)
    assert result == example
    options = completion.await_args.kwargs
    if schema.__name__ in {"Evaluation", "DiagnosticTurn", "UnitPackage"}:
        assert "thinking_level" not in options
    else:
        assert options["thinking_level"] == "low"
    assert options["response_format"] == {"type": "json_object"}
    assert options["use_cache"] is False
    assert options["max_tokens"] == (16000 if schema.__name__ == "UnitPackage" else
                                      2000 if schema.__name__ == "Evaluation" else 4500)


class TransparentBreaker:
    is_closed = True

    async def call(self, action):
        return await action()


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["gemini-3.8-flash", "gemini-2.5-flash"])
async def test_thinking_level_reaches_actual_http_payload_without_extending_deadline(monkeypatch, model_name):
    observed = []

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"units": []}'}]}}]}

    def post(endpoint, **options):
        observed.append(options)
        return Response()

    manager = AIResilienceManager()
    manager._initialized = True
    manager.models = {model_name: AIModelConfig(name=model_name, endpoint="https://provider.invalid",
                                               api_key="fixture-not-an-api-key")}
    manager.circuit_breakers = {model_name: TransparentBreaker()}
    manager.session = SimpleNamespace(post=post)
    monkeypatch.setattr("lyo_app.teaching_runtime.model_usage.capture_model_usage", AsyncMock())
    for level in ("low", None):
        response = await manager.chat_completion(
            messages=[{"role": "user", "content": "Author the next teaching move."}],
            provider_order=[model_name], max_tokens=4500, thinking_level=level,
            response_format={"type": "json_object"}, use_cache=False,
        )
        assert response["content"] == '{"units": []}'
        config = observed[-1]["json"]["generationConfig"]
        assert config["maxOutputTokens"] == 4500
        assert config["responseMimeType"] == "application/json"
        assert observed[-1]["timeout"].total == 25
        if level and model_name == "gemini-3.8-flash":
            assert config["thinkingConfig"] == {"thinkingLevel": "low"}
        else:
            assert "thinkingConfig" not in config


@pytest.mark.asyncio
async def test_unsupported_thinking_level_is_rejected_before_provider_initialization():
    manager = AIResilienceManager()
    manager.initialize = AsyncMock()
    with pytest.raises(ValueError, match="thinking level"):
        await manager.chat_completion(messages=[], thinking_level="minimal")
    manager.initialize.assert_not_awaited()
