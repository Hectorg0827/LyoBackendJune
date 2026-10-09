"""Turn a Pydantic contract into a schema a provider will actually enforce.

The classroom asks for JSON by putting `schema.model_json_schema()` into the
*prompt* and setting the provider's loose JSON mode — OpenAI's
`{"type": "json_object"}`, Gemini's `responseMimeType`. Both of those mean
only "reply with some JSON". The schema is a request, and a model that ignores
it produces output that fails `model_validate_json`, which is a rejected turn,
which is a retry, which is how a learner ends up on a paused board.

Both providers can be given the schema itself, as something they must satisfy
rather than something they are asked to respect. They want it in a narrower
dialect than Pydantic emits, which is what this module produces:

* `$ref`/`$defs` inlined — support for references differs between providers
  and between versions of each, and the contracts here are small enough that
  inlining costs nothing.
* Validation-only keywords dropped. `maximum`, `minLength` and friends are not
  reliably accepted, and nothing is lost by removing them: the response is
  still parsed by the real Pydantic model afterwards, which enforces every one
  of them properly. The full annotated contract also still goes into the
  prompt, so the model keeps the guidance even where the enforced schema is
  coarser.
* Every object closed (`additionalProperties: false`) and every property
  required.

That last rule deserves its reason. Strict mode has no notion of an optional
property, so each one must be listed. A field Pydantic marks optional because
it has a default (`demonstration: list[Beat] = []`) becomes a field the model
must write explicitly — an empty list, not an absent key — and that is safe
because whatever it sends is validated by the model afterwards anyway. A field
that is genuinely nullable (`visual: Visual | None`) already carries
`{"type": "null"}` in the schema Pydantic emits, so requiring it changes
nothing: null stays legal. Requiring a non-nullable field cannot make null
legal, which is what would have been dangerous.
"""

from __future__ import annotations

from typing import Any

#: Keywords no provider's structured-output dialect accepts consistently.
#: Every one of them is re-checked by the Pydantic model after parsing, so
#: dropping them here narrows what the provider enforces, never what we do.
_DROPPED_KEYWORDS = frozenset({
    "default", "title", "examples", "example", "format", "pattern",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties", "discriminator", "deprecated",
    "readOnly", "writeOnly", "$schema", "$id", "const",
})

#: How deep inlining may go before a schema is assumed to be recursive.
#: A recursive contract cannot be inlined at all, and the caller is expected
#: to fall back to the loose mode rather than send something malformed.
_MAX_DEPTH = 24


#: Phrases that identify a provider refusing the *request* because of the
#: schema it carried, as opposed to the provider being down, rate limited,
#: unreachable or behind an open circuit.
#:
#: Deliberately narrow. A provider that cannot be reached has not told us
#: anything about our schema, and treating silence as a schema rejection is
#: what would make an ordinary outage cost two full attempts instead of one.
_SCHEMA_REJECTION_MARKERS = (
    "response_format",
    "json_schema",
    "responseschema",
    "response schema",
    "invalid schema",
    "invalid_schema",
    "unsupported schema",
    "schema is invalid",
    "schema is not supported",
)


def looks_like_schema_rejection(error: object) -> bool:
    """Did the provider refuse the enforced schema, or just fail?

    `chat_completion` reports both the same way — every provider exhausted,
    `is_fallback` set — so the only thing separating "this dialect is not
    accepted here" from "nothing is working right now" is what the last
    exception said.

    The difference matters because the two want opposite responses. A schema
    rejection is permanent for this call and worth one immediate retry in the
    loose mode. An outage is neither: retrying sends the identical request
    through the identical unhealthy providers, doubles a 45-second classroom
    call to 90 (or a package call from 100 to 200), and adds load at exactly
    the moment there is least to spare.
    """
    text = str(error or "").lower()
    return any(marker in text for marker in _SCHEMA_REJECTION_MARKERS)


class SchemaNotStrictable(ValueError):
    """This contract cannot be expressed in a provider's strict dialect.

    Raised rather than returned so a caller cannot use the result by accident.
    Recursion is the real case: a schema that refers to itself has no finite
    inlining, and no amount of retrying changes that.
    """


def strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The provider-enforceable form of a Pydantic JSON schema.

    Raises `SchemaNotStrictable` for a contract that cannot be expressed —
    callers fall back to the loose JSON mode, which is what every call did
    before this existed.
    """
    definitions = schema.get("$defs") or {}
    return _convert(schema, definitions, depth=0)


def _convert(node: Any, definitions: dict[str, Any], depth: int) -> Any:
    if depth > _MAX_DEPTH:
        raise SchemaNotStrictable("Schema is recursive or deeper than strict mode allows")
    if isinstance(node, list):
        return [_convert(item, definitions, depth + 1) for item in node]
    if not isinstance(node, dict):
        return node

    reference = node.get("$ref")
    if isinstance(reference, str):
        resolved = _resolve(reference, definitions)
        # Anything beside a `$ref` in the same object (Pydantic puts a
        # `description` there) is kept, with the reference's own body
        # underneath it, so wording written on the field is not lost.
        merged = {key: value for key, value in node.items() if key != "$ref"}
        return {**_convert(resolved, definitions, depth + 1),
                **_convert(merged, definitions, depth + 1)}

    converted: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROPPED_KEYWORDS or key == "$defs":
            continue
        converted[key] = _convert(value, definitions, depth + 1)

    properties = converted.get("properties")
    if isinstance(properties, dict):
        # Closed and fully required. See this module's docstring for why
        # requiring an optional-with-default property is safe.
        converted["additionalProperties"] = False
        converted["required"] = list(properties)
        converted.setdefault("type", "object")
    return converted


def _resolve(reference: str, definitions: dict[str, Any]) -> dict[str, Any]:
    prefix = "#/$defs/"
    if not reference.startswith(prefix):
        raise SchemaNotStrictable(f"Unsupported schema reference: {reference}")
    name = reference[len(prefix):]
    if name not in definitions:
        raise SchemaNotStrictable(f"Schema reference has no definition: {reference}")
    return definitions[name]
