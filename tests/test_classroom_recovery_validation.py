"""The staging probe must reject fallback success and retain real evidence."""

import json

import pytest
from jsonschema import Draft202012Validator

from scripts.validate_classroom_recovery import contract_examples, recovery_probe
from lyo_app.ai_classroom.adaptive_teaching import GuidedState, LearningPlan, LearningUnit
from lyo_app.ai_classroom.strict_schema import strict_json_schema
from tests.adaptive_fixtures import ScriptedTeacher, context


def test_probe_examples_satisfy_the_real_models_and_converted_schemas():
    for schema, example in contract_examples().items():
        payload = example.model_dump(mode="json")
        Draft202012Validator(strict_json_schema(schema.model_json_schema())).validate(payload)
        assert schema.model_validate(payload) == example


@pytest.mark.asyncio
@pytest.mark.parametrize("two_failures", [False, True])
async def test_recovery_probe_drives_real_persistence_and_retry_code(monkeypatch, two_failures):
    teacher = ScriptedTeacher()

    async def simulated_completion(**kwargs):
        payload = json.loads(kwargs["messages"][-1]["content"])
        state = GuidedState(owner="42", plan=LearningPlan(units=[LearningUnit.model_validate(payload["unit"])]))
        turn = teacher._turn(context(), state, payload["move"])
        return {"content": turn.model_dump_json(), "model_used": "gemini-2.5-pro"}

    monkeypatch.setenv("CLASSROOM_STRICT_SCHEMA", "0")
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", simulated_completion)
    result = await recovery_probe(two_failures)
    assert result["passed"] and result["database_reload"] and result["evidence_preserved"]
    assert result["recovered_move"] == ("reteach" if two_failures else "explain")


@pytest.mark.asyncio
async def test_a_fallback_is_never_reported_as_actual_pro_acceptance(monkeypatch):
    async def fallback(**kwargs):
        return {"is_fallback": True, "content": "", "model_used": "fallback"}

    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", fallback)
    with pytest.raises(RuntimeError):
        await recovery_probe()
