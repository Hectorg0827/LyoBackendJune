"""The model a failed step reaches for must exist, and must be worth reaching.

`model_json` escalates by putting `ESCALATION_PROVIDER` at the front of the
provider order. That order is filtered against `ai_resilience`'s registry
downstream, so a name the registry does not carry is dropped silently: the
escalation becomes a no-op, the retry re-runs on exactly the models that just
failed, and the symptom is indistinguishable from the bug the escalation
exists to fix. Nothing else in the suite would notice.
"""

import ast
import pathlib

import pytest

from lyo_app.ai_classroom import adaptive_teaching
from lyo_app.ai_classroom.adaptive_teaching import ESCALATION_PROVIDER, PracticeTurn


def registry() -> set[str]:
    """The model names `ai_resilience` configures.

    Read out of the source rather than by constructing the manager: its
    `initialize()` reaches for API keys, cloud secrets and an aiohttp session,
    none of which a unit test should need in order to answer "is this name
    one of the four?".
    """
    source = pathlib.Path("lyo_app/core/ai_resilience.py").read_text()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        target = node.targets[0]
        if (isinstance(target, ast.Attribute) and target.attr == "models"
                and isinstance(target.value, ast.Name) and target.value.id == "self"):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError("could not find the model registry in ai_resilience.py")


def test_the_registry_is_readable_at_all():
    """If this fails the other assertions here are vacuous, not passing."""
    assert len(registry()) >= 2


def test_the_escalation_target_is_a_model_the_registry_actually_carries():
    assert ESCALATION_PROVIDER in registry(), (
        f"{ESCALATION_PROVIDER} is not configured in ai_resilience, so escalating to it "
        "would silently re-run the models that just failed"
    )


def test_the_escalation_target_is_not_one_of_the_models_that_just_failed():
    """Escalating to a model already in the ordinary order buys nothing.

    The ordinary teaching order is the small, fast pair. A step reaches the
    escalation only after every attempt under that pair has failed, so the
    target has to be something those attempts did not already use.
    """
    ordinary = {"gpt-4o-mini", "gemini-2.5-flash"}
    assert ESCALATION_PROVIDER not in ordinary


@pytest.mark.asyncio
async def test_a_failed_step_is_retried_on_the_escalated_model_first(monkeypatch):
    monkeypatch.delenv("CLASSROOM_STRICT_SCHEMA", raising=False)
    orders = []
    turn = PracticeTurn(
        speech="Let's try one together with the same method.",
        board_title="Your turn to apply it",
        board_content="Work out how much of the pizza is left, and say why.",
        task={
            "kind": "apply", "target_index": 0,
            "scenario": "Two friends split a pizza into four equal pieces and take one each.",
            "question": "How much of the pizza is left, and how do you know?",
            "response_hint": "Say the fraction and the reason in one sentence.",
            "criteria": ["names the fraction left", "explains how the equal pieces give it"],
            "example_answer": "Half, because they took two of the four equal pieces.",
        },
    )

    async def chat_completion(**kwargs):
        orders.append(list(kwargs["provider_order"]))
        return {"content": turn.model_dump_json(), "model_used": "gemini-2.5-pro", "tokens_used": 10}

    import lyo_app.core.ai_resilience as resilience
    monkeypatch.setattr(resilience.ai_resilience_manager, "chat_completion", chat_completion)

    await adaptive_teaching.model_json("system", {"a": 1}, PracticeTurn)
    assert orders[-1][0] != ESCALATION_PROVIDER, "an ordinary step must not pay for the big model"

    await adaptive_teaching.model_json("system", {"a": 1, "_escalate": True}, PracticeTurn)
    assert orders[-1][0] == ESCALATION_PROVIDER
    # The models that just failed stay available behind it, rather than being
    # dropped: the escalation is a reorder, never a narrowing.
    assert set(orders[-1]) >= set(orders[-2])


@pytest.mark.asyncio
async def test_nothing_internal_reaches_the_model(monkeypatch):
    """`_escalate` is routing, like `_rejected_provider`. A learner's teaching
    context must never carry this server's own retry bookkeeping into a prompt."""
    monkeypatch.delenv("CLASSROOM_STRICT_SCHEMA", raising=False)
    sent = []
    turn = PracticeTurn(
        speech="Let's try one together with the same method.",
        board_title="Your turn to apply it",
        board_content="Work out how much of the pizza is left, and say why.",
        task={
            "kind": "apply", "target_index": 0,
            "scenario": "Two friends split a pizza into four equal pieces and take one each.",
            "question": "How much of the pizza is left, and how do you know?",
            "response_hint": "Say the fraction and the reason in one sentence.",
            "criteria": ["names the fraction left", "explains how the equal pieces give it"],
            "example_answer": "Half, because they took two of the four equal pieces.",
        },
    )

    async def chat_completion(**kwargs):
        sent.append(kwargs["messages"][-1]["content"])
        return {"content": turn.model_dump_json(), "model_used": "gemini-2.5-pro", "tokens_used": 10}

    import lyo_app.core.ai_resilience as resilience
    monkeypatch.setattr(resilience.ai_resilience_manager, "chat_completion", chat_completion)

    await adaptive_teaching.model_json(
        "system", {"unit": "fractions", "_escalate": True, "_rejected_provider": "gpt-4o-mini"},
        PracticeTurn,
    )
    assert "_escalate" not in sent[-1] and "_rejected_provider" not in sent[-1]
    assert "fractions" in sent[-1]
