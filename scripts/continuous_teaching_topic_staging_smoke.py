"""Verify that a real staging lesson keeps its launch topic across WebSocket actions.

Live readout is correlated with Railway's server-side ContextAssembler logs by
a synthetic session ID. This is not a production or physical-device test.
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid

import httpx
import websockets

from continuous_teaching_live_staging_smoke import (
    BASE, create_synthetic, report, require, socket_url, verify_target,
)
from continuous_teaching_grading_replay_staging_smoke import (
    scene_cycle, submission, action, task_from, continue_from,
)

EXPECTED = "b77ff24a6b3fe4017571a0da28e979a9e45511a7"
TOPIC = "Compare one half with one third using equal-sized pieces"


async def main() -> None:
    verify_target()
    async with httpx.AsyncClient(base_url=BASE, timeout=25, follow_redirects=False) as client:
        health = await client.get("/health")
        require(health.status_code == 200, "staging health endpoint not OK")
        metadata = health.json()
        require(metadata.get("commit_sha") == EXPECTED, "unexpected staging revision")
        require(str(metadata.get("environment", "")).lower() != "production",
                "refusing to test production")
        token, user_id = await create_synthetic(client, "topic")
        session = "ct-topic-" + uuid.uuid4().hex
        report("topic_probe_session", status="created", session_id=session,
               expected_topic=TOPIC)
        async with websockets.connect(
            socket_url(token, session, topic=TOPIC, resume=False),
            open_timeout=25, max_size=5_000_000,
        ) as ws:
            first, _ = await scene_cycle(ws, name="topic launch")
            require(bool(first.get("scene_id")), "no initial authoritative scene")
            item = task_from(first)
            if item:
                await ws.send(json.dumps(submission(session, item)))
                after, feedback = await scene_cycle(ws, name="first learner action")
                require(after.get("scene_id") != first.get("scene_id"),
                        "first learner action did not produce new lesson scene")
                report("topic_after_learner_action", status="passed",
                       session_id=session, scene_transition=True,
                       feedback_events=len(feedback))
            else:
                button = continue_from(first)
                require(button is not None, "no diagnostic or continue action")
                await ws.send(json.dumps(action(
                    session, "continue", button["component_id"],
                )))
                after, _ = await scene_cycle(ws, name="first learner Continue")
                require(after.get("scene_id") != first.get("scene_id"),
                        "first Continue did not produce new lesson scene")
                report("topic_after_learner_action", status="passed",
                       session_id=session, scene_transition=True)
        # Server-side logs are the authoritative way to check the topic sent
        # to the provider. Do not claim proof from this transport check alone.
        report("result", status="passed", limitation=(
            "requires correlation of session ID against Railway context logs "
            "for both first and subsequent learner turns"
        ))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        report("result", status="failed", reason=type(exc).__name__)
        sys.exit(1)
