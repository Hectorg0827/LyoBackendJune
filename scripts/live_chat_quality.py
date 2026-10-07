#!/usr/bin/env python3
"""Production-facing quality matrix for canonical Lyo Chat.

The harness records public SSE events only. It does not inspect private prompts,
model reasoning, or internal databases. Use a dedicated test learner token when
available; guest mode still validates most interaction-contract behavior.
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
from typing import Any, Dict, List, Optional

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
        "Who is the current president of France? Use current information.",
        "search",
        r"France",
        require_sources=True,
    ),
    Scenario(
        "spanish",
        "Explícame brevemente qué es la gravedad.",
        "explain",
        r"gravedad|atracci",
    ),
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
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    started = time.monotonic()
    response = await client.post(
        f"{base_url.rstrip('/')}/api/v1/lyo2/chat/stream",
        json=payload,
        headers=headers,
        timeout=75.0,
    )
    response.raise_for_status()
    return _decode_sse(response.text), int((time.monotonic() - started) * 1000)


def _observe(scenario: Scenario, events: List[Dict[str, Any]], wall_ms: int) -> Observation:
    mode = None
    answer = ""
    sources = 0
    structured = 0
    reported_latency = None

    for event in events:
        event_type = event.get("type")
        if event_type == "interaction_contract":
            mode = event.get("mode")
        elif event_type == "answer":
            block = event.get("block") or {}
            content = block.get("content") or {}
            if isinstance(content.get("text"), str):
                answer = content["text"]
        elif event_type == "sources":
            values = event.get("sources") or []
            sources = max(sources, len(values) if isinstance(values, list) else 0)
        elif event_type == "smart_blocks":
            blocks = event.get("blocks") or []
            if isinstance(blocks, list):
                structured += sum(
                    1
                    for block in blocks
                    if isinstance(block, dict)
                    and (
                        block.get("type") in {"dataViz", "interactive"}
                        or block.get("subtype") in {"comparison", "stepByStep", "sourceNavigator"}
                    )
                )
        elif event_type == "latency":
            metrics = event.get("metrics") or {}
            value = metrics.get("total_ms")
            if isinstance(value, int):
                reported_latency = value

    failures: List[str] = []
    if mode != scenario.expected_mode:
        failures.append(f"mode={mode!r}, expected {scenario.expected_mode!r}")
    if not answer.strip():
        failures.append("no canonical final answer")
    if scenario.expected_text and not re.search(scenario.expected_text, answer, re.IGNORECASE):
        failures.append("expected answer evidence missing")
    if scenario.require_sources and sources < 1:
        failures.append("current-information turn had no exposed sources")
    if scenario.require_structured_representation and structured < 1:
        failures.append("structured representation missing")
    if scenario.forbid_leading_question and answer.lstrip().startswith("?"):
        failures.append("answer gated behind a question")
    latency = reported_latency if reported_latency is not None else wall_ms
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
    )


async def run(base_url: str, token: str) -> Dict[str, Any]:
    observations: List[Observation] = []
    async with httpx.AsyncClient() as client:
        for scenario in SCENARIOS:
            events, wall_ms = await _turn(client, base_url, scenario.prompt, token=token)
            observations.append(_observe(scenario, events, wall_ms))

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
            history=[
                {"role": "user", "content": "For this conversation, my study codeword is ORBIT-42."},
                {"role": "assistant", "content": "Got it."},
            ],
        )
        continuity = _observe(
            Scenario("working_memory", "", "answer", r"ORBIT-42"),
            follow_events,
            wall_ms,
        )
        observations.append(continuity)

    passed = sum(1 for item in observations if item.passed)
    total = len(observations)
    return {
        "base_url": base_url,
        "authenticated": bool(token),
        "passed": passed,
        "total": total,
        "pass_rate": passed / total if total else 0.0,
        "observations": [asdict(item) for item in observations],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("LYO_BASE_URL", "https://api.lyoai.app"))
    parser.add_argument("--output", default="artifacts/chat-quality/live-chat-quality.json")
    args = parser.parse_args()

    token = os.getenv("LYO_CHAT_QUALITY_TOKEN") or os.getenv("LYO_TEACHER_QUALITY_TOKEN") or ""
    report = asyncio.run(run(args.base_url, token))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"chat quality: {report['passed']}/{report['total']} passed")
    print(f"report: {path}")
    return 0 if report["pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
