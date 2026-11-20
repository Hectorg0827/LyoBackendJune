"""Staging-only live Continuous Teaching bridge start-vs-authoritative-scene probe.

Verifies that the early prompt is immediate, ungraded and separate from the
authoritative lesson. Does NOT claim to play or evaluate Android phone audio.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from urllib.parse import urlencode

import httpx
import websockets

from continuous_teaching_live_staging_smoke import (
    BASE, WS_ENDPOINT, create_synthetic, report, require, verify_target,
)

EXPECTED_REVISION = "16b44150da69457e2ab738175aafc10361f349e6"


async def main() -> None:
    verify_target()
    async with httpx.AsyncClient(base_url=BASE, timeout=25, follow_redirects=False) as client:
        health_response = await client.get("/health")
        require(health_response.status_code == 200, "staging health not 200")
        health = health_response.json()
        require(health.get("commit_sha") == EXPECTED_REVISION,
                "refusing unexpected backend revision")
        require(str(health.get("environment", "")).lower() != "production",
                "refusing production environment")
        token, user_id = await create_synthetic(client, "bridge")
        session_id = "ct-bridge-" + uuid.uuid4().hex
        params = {
            "token": token, "session_id": session_id,
            "topic": "Fractions and equal pieces", "language": "en-US",
            "continuous_teaching": "1", "resume": "0",
        }
        url = WS_ENDPOINT + "?" + urlencode(params)
        opened = time.monotonic()
        bridge = None
        authoritative_scene = None
        events_before_scene = []
        async with websockets.connect(url, open_timeout=20, max_size=5_000_000) as ws:
            deadline = time.monotonic() + 145
            while time.monotonic() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
                try:
                    event = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("event_type")
                if kind == "error":
                    raise RuntimeError("classroom websocket reported an error")
                if kind == "bridge_message" and bridge is None:
                    bridge = event
                    latency_ms = round((time.monotonic() - opened) * 1000)
                    data = bridge.get("data") or {}
                    require(bridge.get("session_id") == session_id
                            and str(bridge.get("user_id")) == user_id,
                            "bridge message routed to another learner")
                    require(data.get("ungraded") is True, "early bridge is not ungraded")
                    require(data.get("ai_generated") is False,
                            "startup bridge claimed AI-written content")
                    require(data.get("prompt") is True, "early bridge did not ask learner a prompt")
                    require(bool(data.get("text")), "empty startup bridge prompt")
                    require(latency_ms < 5000,
                            "startup text bridge exceeded five seconds")
                    report("ungraded_startup_bridge", status="passed",
                           latency_ms=latency_ms, user_scoped=True)
                if authoritative_scene is None:
                    events_before_scene.append(kind)
                if kind == "scene_start" and event.get("scene"):
                    authoritative_scene = event["scene"]
                    scene_latency_ms = round((time.monotonic() - opened) * 1000)
                    require(bridge is not None, "authoritative scene started before early bridge")
                    require(authoritative_scene.get("scene_id"), "authoritative scene lacks ID")
                    require(scene_latency_ms >= latency_ms,
                            "lesson scene preceded bridge prompt")
                    report("authoritative_scene_handoff", status="passed",
                           elapsed_ms=scene_latency_ms, bridge_before_scene=True,
                           early_feedback_events=events_before_scene.count("answer_feedback"))
                    break
            require(bridge is not None and authoritative_scene is not None,
                    "missing early bridge or authoritative scene")
            require(events_before_scene.count("answer_feedback") == 0,
                    "bridge emitted grading feedback without any assessment")
        report("result", status="passed", limitations=[
            "no Android TTS audio or microphone transport was tested",
            "scene timing includes real provider and network latency",
            "only one bounded startup session measured",
        ])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        report("result", status="failed", reason=type(exc).__name__)
        sys.exit(1)
