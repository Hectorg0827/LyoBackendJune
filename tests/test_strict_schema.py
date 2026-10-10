"""The schema a provider is given must be enforceable, and must not lie.

These run entirely offline. They cannot show that OpenAI or Gemini accepts the
result — nothing here can, short of calling them — but they do show that the
conversion keeps the contract honest: nothing a real model would reject gets
through, and nothing the real Pydantic model would reject becomes legal.
"""

import json

import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    DiagnosticTurn, Evaluation, ExplanationPracticeTurn, ExplanationTurn,
    FocusedModelledTurn, LearningPlan, ModelledTurn, PracticeTurn,
    ReteachingTurn, TransferPracticeTurn, UnitPackage,
)
from lyo_app.ai_classroom.strict_schema import SchemaNotStrictable, strict_json_schema

CONTRACTS = [PracticeTurn, ModelledTurn, FocusedModelledTurn, ReteachingTurn,
             ExplanationTurn, ExplanationPracticeTurn, TransferPracticeTurn,
             DiagnosticTurn, Evaluation, LearningPlan, UnitPackage]


def objects(node):
    """Every object schema in the tree, including the root."""
    if isinstance(node, list):
        for item in node:
            yield from objects(item)
    elif isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            yield node
        for value in node.values():
            yield from objects(value)


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.__name__)
def test_every_teaching_contract_converts(contract):
    strict = strict_json_schema(contract.model_json_schema())
    text = json.dumps(strict)
    # References are inlined: provider support for them differs by provider
    # and by version, and these contracts are small enough not to need them.
    assert "$ref" not in text and "$defs" not in text
    # Nothing a strict dialect refuses is left behind.
    for rejected in ("minLength", "maxLength", "minimum", "maximum", "default", "pattern"):
        assert rejected not in text, f"{rejected} survived conversion"


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.__name__)
def test_every_object_is_closed_and_fully_required(contract):
    strict = strict_json_schema(contract.model_json_schema())
    found = list(objects(strict))
    assert found, "conversion produced no object schemas at all"
    for obj in found:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.__name__)
def test_requiring_a_field_never_makes_null_legal_where_it_was_not(contract):
    """The one way this conversion could be dangerous, closed off.

    Strict mode has no optional property, so every field is required. That is
    safe only because it does not touch the *types*: a field Pydantic allows
    to be null still carries `{"type": "null"}`, and a field it does not still
    does not. If this ever started adding null to make a field optional, the
    provider would be allowed to send something the model then rejects — a
    rejected turn, which is the failure this whole change exists to reduce.
    """
    loose = contract.model_json_schema()
    strict = strict_json_schema(loose)

    def nullable(node):
        """Whether *this* property may itself be null.

        Deliberately not a walk of the whole subtree: a nested field being
        nullable says nothing about its parent, and a comparison that
        conflated the two would pass or fail for the wrong reason — the
        strict side is fully inlined and so has every nested type in view
        where the loose side still hides them behind a reference.
        """
        if not isinstance(node, dict):
            return False
        if node.get("type") == "null":
            return True
        for branch in ("anyOf", "oneOf"):
            if any(isinstance(m, dict) and m.get("type") == "null"
                   for m in node.get(branch, [])):
                return True
        return False

    for name, loose_property in loose.get("properties", {}).items():
        assert nullable(strict["properties"][name]) == nullable(loose_property), name


def test_descriptions_written_on_a_field_survive_being_inlined():
    """A `$ref` with a sibling `description` is how Pydantic annotates a
    nested field. Inlining must keep the wording — it is teaching instruction
    for the model, and dropping it quietly makes every authored turn worse."""
    strict = strict_json_schema({
        "type": "object",
        "properties": {"task": {"$ref": "#/$defs/Task", "description": "the one question"}},
        "required": ["task"],
        "$defs": {"Task": {"type": "object", "properties": {"q": {"type": "string"}},
                           "required": ["q"], "additionalProperties": False}},
    })
    assert strict["properties"]["task"]["description"] == "the one question"
    assert strict["properties"]["task"]["properties"]["q"] == {"type": "string"}


def test_a_recursive_contract_is_refused_rather_than_mangled():
    """Refused, so the caller falls back to the loose mode it always used.

    An inlined recursive schema is either infinite or silently truncated, and
    a truncated contract is one the provider would enforce *wrongly*.
    """
    with pytest.raises(SchemaNotStrictable):
        strict_json_schema({
            "type": "object",
            "properties": {"child": {"$ref": "#/$defs/Node"}},
            "$defs": {"Node": {"type": "object", "properties": {"child": {"$ref": "#/$defs/Node"}}}},
        })


def test_a_reference_with_no_definition_is_refused():
    with pytest.raises(SchemaNotStrictable):
        strict_json_schema({"type": "object", "properties": {"a": {"$ref": "#/$defs/Missing"}}})


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.__name__)
def test_nested_field_names_and_types_survive_conversion(contract):
    original = contract.model_json_schema()
    definitions = original.get("$defs", {})

    def compare(loose, strict):
        if not isinstance(loose, dict):
            return
        if "$ref" in loose:
            loose = {**definitions[loose["$ref"].removeprefix("#/$defs/")],
                     **{key: value for key, value in loose.items() if key != "$ref"}}
        if "type" in loose:
            assert strict["type"] == loose["type"]
        if "enum" in loose:
            assert strict["enum"] == loose["enum"]
        if "const" in loose:
            assert strict["enum"] == [loose["const"]]
        if "properties" in loose:
            assert set(strict["properties"]) == set(loose["properties"])
            for name, field in loose["properties"].items():
                compare(field, strict["properties"][name])
        if "items" in loose:
            compare(loose["items"], strict["items"])
        for branch in ("anyOf", "oneOf", "allOf"):
            if branch in loose:
                assert len(loose[branch]) == len(strict[branch])
                for before, after in zip(loose[branch], strict[branch]):
                    compare(before, after)

    compare(original, strict_json_schema(original))


@pytest.mark.parametrize("name", ["title", "default", "pattern", "format", "const", "$ref"])
def test_field_names_are_not_treated_as_schema_keywords(name):
    strict = strict_json_schema({"type": "object", "properties": {
        name: {"type": "string", "title": "Metadata", "default": "example"},
    }})
    assert strict["properties"] == {name: {"type": "string"}}
    assert strict["required"] == [name]


def test_required_learning_unit_title_can_satisfy_both_contracts():
    from jsonschema import Draft202012Validator

    plan = LearningPlan.model_validate({"units": [{
        "title": "Compare equal fraction parts",
        "objective": "Compare two shares using equal-sized parts.",
        "material": "Split each whole into four equal parts, then count the shaded parts to compare shares.",
        "practice_targets": ["Compare shares with the same denominator"],
        "takeaway": "Compare equal parts by counting them.",
        "prerequisite_titles": [],
    }]})
    payload = plan.model_dump(mode="json")
    strict = strict_json_schema(LearningPlan.model_json_schema())
    Draft202012Validator.check_schema(strict)
    Draft202012Validator(strict).validate(payload)
    assert LearningPlan.model_validate(payload) == plan


def test_literals_are_enforced_as_single_value_enums():
    strict = strict_json_schema({"type": "object", "properties": {
        "version": {"type": "integer", "const": 2},
    }})
    assert strict["properties"]["version"] == {"type": "integer", "enum": [2]}
