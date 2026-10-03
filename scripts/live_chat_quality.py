#!/usr/bin/env python3
"""Black-box Chat quality validation against a deployed Lyo backend.

The harness validates the product contracts that should never depend on prompt
luck: interaction-mode obedience, direct-answer behavior, planner-free response
availability, and live-source grounding.  It uses only the public Chat SSE
contract and a dedicated test learner token.

Reports are bounded and never include the bearer token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


DEFAULT_BASE_URL = "https://api.lyoai.app"
REPORT_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_https(value: str, allow_http: bool = False) -> str:
    base = value.rstrip("/")
    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("LYO_BASE_URL must be an absolute URL")
    if parsed.scheme != "https" and not allow_http:
        raise ValueError("Refusing non-HTTPS target")
    return base


def parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            events.append({"type": "invalid_json"})
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def answer_text(events: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for event in events:
        if event.get("type") not in {"answer", "text"}:
            continue
        block = event.get("block")
        if isinstance(block, dict):
            content = block.get("content")
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
                continue
        if isinstance(event.get("content"), str):
            parts.append(event["content"])
    return "".join(parts).strip()


def contract_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (event for event in events if event.get("type") == "interaction_contract"),
        None,
    )


def source_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((event for event in events if event.get("type") == "sources"), None)


def has_clarification(events: list[dict[str, Any]]) -> bool:
    return any(event.get("type") == "clarification" for event in events)


async def run_turn(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    text: str,
) -> list[dict[str, Any]]:
    response = await client.post(
        f"{base_url}/api/v1/lyo2/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": text,
            "device_id": f"chat-quality-{uuid.uuid4()}",
            "client_message_id": str(uuid.uuid4()),
            "conversation_history": [],
            "state_summary": {},
        },
        timeout=90.0,
    )
    response.raise_for_status()
    return parse_sse(response.text)


async def validate(base_url: str, token: str) -> dict[str, Any]:
    scenarios = [
        {
            "name": "direct_concise",
            "text": "What is the capital of France? Keep it concise.",
            "mode": "answer",
            "depth": "concise",
            "sources": False,
        },
        {
            "name": "explicit_explain",
            "text": "Explain photosynthesis.",
            "mode": "explain",
            "depth": "standard",
            "sources": False,
        },
        {
            "name": "comparison",
            "text": "Compare mitosis vs meiosis.",
            "mode": "compare",
            "depth": "standard",
            "sources": False,
        },
        {
            "name": "live_search",
            "text": "Search the web for the current stable Python release.",
            "mode": "search",
            "depth": "standard",
            "sources": True,
        },
    ]

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for scenario in scenarios:
            events = await run_turn(client, base_url, token, scenario["text"])
            contract = contract_event(events) or {}
            sources = source_event(events) or {}
            answer = answer_text(events)
            checks = {
                "contract_present": bool(contract),
                "mode_matches": contract.get("mode") == scenario["mode"],
                "depth_matches": contract.get("depth") == scenario["depth"],
                "no_unrequested_clarification": not has_clarification(events),
                "answer_present": bool(answer),
            }
            if scenario["sources"]:
                checks["live_sources_present"] = bool(sources.get("sources"))

            results.append(
                {
                    "name": scenario["name"],
                    "checks": checks,
                    "passed": all(checks.values()),
                    "contract": {
                        key: contract.get(key)
                        for key in (
                            "mode",
                            "depth",
                            "representation",
                            "fast_lane",
                            "requires_search",
                            "reason_code",
                        )
                    },
                    "source_count": len(sources.get("sources") or []),
                    "answer_preview": answer[:500],
                }
            )

    return {
        "report_version": REPORT_VERSION,
        "generated_at": utc_now(),
        "base_url": base_url,
        "passed": all(item["passed"] for item in results),
        "scenarios": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("LYO_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--output")
    parser.add_argument("--allow-http", action="store_true")
    args = parser.parse_args()

    token = os.getenv("LYO_ACCESS_TOKEN", "").strip()
    if not token:
        print("LYO_ACCESS_TOKEN is required", file=sys.stderr)
        return 2

    try:
        base_url = require_https(args.base_url, args.allow_http)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    import asyncio

    report = asyncio.run(validate(base_url, token))
    output = args.output or f"artifacts/chat-quality/live-{uuid.uuid4()}.json"
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
