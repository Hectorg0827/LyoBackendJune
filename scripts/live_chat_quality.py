#!/usr/bin/env python3
"""Production-facing quality matrix for canonical Lyo Chat.

The harness records public SSE events only. It does not inspect private prompts,
model reasoning, or internal databases. An accepted dedicated test learner
token is required to verify the authenticated production endpoint and history.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class Scenario:
    name: str
    prompt: str
    expected_mode: str
    expected_text: Optional[str] = None
    require_sources: bool = False
    require_structured_representation: bool = False
    forbid_leading_question: bool = True
    require_streaming: bool = True
    source_pattern: Optional[str] = None
    source_day: Optional[str] = None
    max_first_token_ms: int = 2000


SCENARIOS = [
    Scenario("direct_answer", "Just answer: what is 2 + 2?", "answer", r"\b4\b"),
    Scenario("explain", "Briefly explain photosynthesis.", "explain", r"light|energy|glucose"),
    Scenario(
        "compare",
        "Compare mitosis and meiosis.",
        "compare",
        r"mitosis|meiosis",
        require_structured_representation=True,
    ),
    Scenario(
        "current_grounded",
        "Who is the current president of France? Verify with the official Elysée website.",
        "search",
        r"Emmanuel\s+Macron",
        require_sources=True,
        source_pattern=r"macron",
    ),
    Scenario(
        "spanish",
        "Explícame brevemente qué es la gravedad.",
        "explain",
        r"gravedad|atracci",
    ),
    Scenario("news_today", "What happened in AI news today? Include current sources.",
             "search", r"AI|artificial intelligence", require_sources=True,
             source_pattern=r"AI|artificial intelligence", source_day="today"),
    Scenario("weather_today", "What's today's weather in New York City? Include current sources.",
             "search", r"New York", require_sources=True,
             source_pattern=r"New York", source_day="today"),
    Scenario("weather_tomorrow", "What's tomorrow's weather in New York City? Include the forecast date.",
             "search", r"New York", require_sources=True,
             source_pattern=r"New York", source_day="tomorrow"),
    Scenario("latest_software", "What is the latest stable Python version? Check python.org.",
             "search", r"Python|\d+\.\d+", require_sources=True, source_pattern=r"Python"),
]


@dataclass
class Observation:
    scenario: str
    passed: bool
    failures: List[str] = field(default_factory=list)
    answer: str = ""
    mode: Optional[str] = None
    sources: int = 0
    structured_blocks: int = 0
    latency_ms: Optional[int] = None
    first_token_ms: Optional[int] = None
    text_deltas: int = 0


def _decode_sse(raw: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for chunk in raw.split("\n\n"):
        data_lines = [
            line[5:].strip()
            for line in chunk.splitlines()
            if line.startswith("data:")
        ]
        if not data_lines:
            continue
        data = "\n".join(data_lines)
        if data == "[DONE]":
            events.append({"type": "validation_done"})
            continue
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


async def _turn(
    client: httpx.AsyncClient,
    base_url: str,
    prompt: str,
    *,
    token: str = "",
    conversation_id: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> tuple[List[Dict[str, Any]], int]:
    headers = {"Accept": "text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload: Dict[str, Any] = {
        "text": prompt,
        "client_message_id": str(uuid.uuid4()),
        "state_summary": {"stream_capabilities": {"text_delta": True}},
        "conversation_history": history or [],
        "timezone": "America/New_York",
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    started = time.monotonic()
    events = []
    buffer = []
    try:
        async with client.stream(
            "POST", f"{base_url.rstrip('/')}/api/v1/lyo2/chat/stream",
            json=payload, headers=headers, timeout=75.0,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    buffer.append(line)
                    continue
                decoded = _decode_sse("\n".join(buffer))
                buffer = []
                for event in decoded:
                    event["_received_ms"] = int((time.monotonic() - started) * 1000)
                    events.append(event)
        if buffer:
            for event in _decode_sse("\n".join(buffer)):
                event["_received_ms"] = int((time.monotonic() - started) * 1000)
                events.append(event)
    except Exception as exc:
        # Never serialize response bodies, request headers, or URLs containing secrets.
        response = getattr(exc, "response", None)
        events.append({"type": "validation_error", "error": type(exc).__name__,
                       "http_status": getattr(response, "status_code", None)})
    return events, int((time.monotonic() - started) * 1000)


def _observe(scenario: Scenario, events: List[Dict[str, Any]], wall_ms: int) -> Observation:
    mode = None
    answer = ""
    sources = 0
    structured = 0
    first_token_ms = None
    text_deltas = 0
    completed = False
    invalid_completion = False
    source_values = []
    done = False

    for event in events:
        event_type = event.get("type")
        if event_type == "interaction_contract":
            mode = event.get("mode")
        elif event_type == "answer":
            completed = event.get("generation_status") == "completed"
            invalid_completion |= event.get("generation_status") == "incomplete"
            block = event.get("block") or {}
            content = block.get("content") or {}
            if isinstance(content.get("text"), str):
                answer = content["text"]
        elif event_type == "sources":
            values = event.get("sources") or []
            sources = max(sources, len(values) if isinstance(values, list) else 0)
            if isinstance(values, list):
                source_values = [source for source in values if isinstance(source, dict)]
        elif event_type == "smart_blocks":
            blocks = event.get("blocks") or []
            if isinstance(blocks, list):
                structured += sum(
                    1
                    for block in blocks
                    if isinstance(block, dict)
                    and (
                        (block.get("type") == "dataViz" and (block.get("content") or {}).get("source"))
                        or (block.get("subtype") in {"comparison", "stepByStep", "timeline"}
                            and any(item.get("detail") for item in (block.get("content") or {}).get("items", [])
                                    if isinstance(item, dict)))
                    )
                )
        elif event_type == "text_delta" and event.get("content"):
            text_deltas += 1
            if first_token_ms is None:
                first_token_ms = event.get("_received_ms")
        elif event_type in {"error", "voice_incomplete", "validation_error"}:
            invalid_completion = True
        elif event_type == "validation_done":
            done = True

    failures: List[str] = []
    if mode != scenario.expected_mode:
        failures.append(f"mode={mode!r}, expected {scenario.expected_mode!r}")
    if not answer.strip():
        failures.append("no canonical final answer")
    if scenario.expected_text and not re.search(scenario.expected_text, answer, re.IGNORECASE):
        failures.append("expected answer evidence missing")
    if scenario.require_sources and sources < 1:
        failures.append("current-information turn had no exposed sources")
    if scenario.require_sources:
        usable_sources = []
        for source in source_values:
            url = str(source.get("url") or "")
            try:
                parsed = urlparse(url)
                valid_url = parsed.scheme in {"https", "http"} and bool(parsed.hostname)
            except ValueError:
                valid_url = False
            evidence = str(source.get("snippet") or source.get("content") or "")
            if valid_url and evidence.strip() and source.get("retrieved_at"):
                if not scenario.source_pattern or re.search(scenario.source_pattern, evidence, re.I):
                    if scenario.source_day:
                        expected_day = datetime.now(ZoneInfo("America/New_York")).date()
                        if scenario.source_day == "tomorrow":
                            expected_day += timedelta(days=1)
                        actual_day = source.get("forecast_date") or source.get("published_at")
                        try:
                            if len(str(actual_day)) == 10:
                                source_date = datetime.fromisoformat(actual_day).date()
                            else:
                                source_date = datetime.fromisoformat(str(actual_day).replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).date()
                        except (ValueError, TypeError):
                            continue
                        if source_date != expected_day:
                            continue
                    usable_sources.append(source)
        if not usable_sources:
            failures.append("no relevant dated source evidence for the expected claim")
    if scenario.require_structured_representation and structured < 1:
        failures.append("structured representation missing")
    if scenario.forbid_leading_question and re.match(
        r"^\s*(?:[?¿]|(?:could|can|would) you\b|before (?:i|we)\b|first,? (?:tell|let)\b)", answer, re.I
    ):
        failures.append("answer gated behind a question")
    if not completed or invalid_completion or not done:
        failures.append("stream did not complete successfully")
    if scenario.require_streaming and (not text_deltas or first_token_ms is None):
        failures.append("no measured incremental text delivery")
    elif first_token_ms is not None and first_token_ms > scenario.max_first_token_ms:
        failures.append(f"first visible text exceeded {scenario.max_first_token_ms}ms: {first_token_ms}ms")
    # Server metrics cannot override the clock measured at the receiving client.
    latency = wall_ms
    if latency > 15_000:
        failures.append(f"latency too high: {latency}ms")

    return Observation(
        scenario=scenario.name,
        passed=not failures,
        failures=failures,
        answer=answer[:1000],
        mode=mode,
        sources=sources,
        structured_blocks=structured,
        latency_ms=latency,
        first_token_ms=first_token_ms,
        text_deltas=text_deltas,
    )


async def run(base_url: str, token: str) -> Dict[str, Any]:
    observations: List[Observation] = []
    async with httpx.AsyncClient() as client:
        try:
            preflight = await client.get(f"{base_url.rstrip('/')}/healthz", timeout=15.0)
            preflight.raise_for_status()
            health = preflight.json()
        except Exception as exc:
            return {"base_url": base_url, "authenticated": bool(token), "passed": 0,
                    "total": len(SCENARIOS) + 1, "pass_rate": 0.0,
                    "preflight_error": type(exc).__name__, "observations": []}
        expected_sha = os.getenv("LYO_EXPECTED_DEPLOYED_SHA")
        deployed_sha = health.get("commit_sha")
        if expected_sha and deployed_sha != expected_sha:
            return {"base_url": base_url, "authenticated": bool(token), "passed": 0,
                    "total": len(SCENARIOS) + 1, "pass_rate": 0.0,
                    "preflight_error": "deployed revision does not match candidate",
                    "expected_sha": expected_sha, "deployed_sha": deployed_sha, "observations": []}
        for scenario in SCENARIOS:
            events, wall_ms = await _turn(client, base_url, scenario.prompt, token=token)
            observations.append(_observe(scenario, events, wall_ms))
            if any(event.get("http_status") in {401, 403} for event in events):
                return {"base_url": base_url, "authenticated": bool(token), "passed": 0,
                        "total": len(SCENARIOS) + 1, "pass_rate": 0.0,
                        "preflight_error": "accepted test learner authentication is required",
                        "deployed_sha": deployed_sha,
                        "observations": [asdict(item) for item in observations]}

        # Explicit working-memory continuity: same canonical conversation.
        seed_events, _ = await _turn(
            client,
            base_url,
            "For this conversation, my study codeword is ORBIT-42.",
            token=token,
        )
        conversation_id = next(
            (
                str(event.get("conversation_id"))
                for event in seed_events
                if event.get("type") == "conversation" and event.get("conversation_id")
            ),
            None,
        )
        follow_events, wall_ms = await _turn(
            client,
            base_url,
            "What study codeword did I just give you? Just answer.",
            token=token,
            conversation_id=conversation_id,
        )
        continuity = _observe(
            Scenario("working_memory", "", "answer", r"ORBIT-42"),
            follow_events,
            wall_ms,
        )
        observations.append(continuity)
        if not token or not conversation_id:
            continuity.passed = False
            continuity.failures.append("durable continuity requires authentication and server conversation identity")

    passed = sum(1 for item in observations if item.passed)
    total = len(observations)
    return {
        "base_url": base_url,
        "authenticated": bool(token),
        "passed": passed,
        "total": total,
        "pass_rate": passed / total if total else 0.0,
        "observations": [asdict(item) for item in observations],
        "deployed_sha": deployed_sha,
        "scope": "API interaction, evidence exposure, streaming arrival, and server history; device rendering and factual accuracy require client/source validation",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("LYO_BASE_URL", "https://api.lyoai.app"))
    parser.add_argument("--output", default="artifacts/chat-quality/live-chat-quality.json")
    args = parser.parse_args()

    token = os.getenv("LYO_CHAT_QUALITY_TOKEN") or os.getenv("LYO_TEACHER_QUALITY_TOKEN") or ""
    try:
        report = asyncio.run(run(args.base_url, token))
    except Exception as exc:
        report = {"base_url": args.base_url, "passed": 0, "total": len(SCENARIOS) + 1,
                  "pass_rate": 0.0, "preflight_error": type(exc).__name__, "observations": []}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"chat quality: {report['passed']}/{report['total']} passed")
    for item in report.get("observations", []):
        print(f"{item['scenario']}: passed={item['passed']} first_text_ms={item.get('first_token_ms')} "
              f"wall_ms={item.get('latency_ms')} failures={item.get('failures', [])}")
    if report.get("preflight_error"):
        print(f"preflight: {report['preflight_error']}")
    print(f"report: {path}")
    if "authentication" in str(report.get("preflight_error", "")):
        return 2
    return 0 if report["pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
