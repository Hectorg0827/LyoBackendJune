"""One-shot isolated staging checkpoint proof across a real backend redeployment.

The operator redeploys ONLY the designated preview backend after
STAGING_RESTART_READY is printed. The CI worker retains credentials privately.
This does not grade answers or validate physical audio.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid

import httpx
import websockets

from continuous_teaching_live_staging_smoke import (
    BASE, verify_target, require, report, create_synthetic,
    exercise_socket, socket_url, recv_until, is_scene, scene_id,
)

PAUSE_SECONDS = 170


async def main() -> None:
    verify_target()
    async with httpx.AsyncClient(base_url=BASE, timeout=25, follow_redirects=False) as http:
        health = await http.get("/health")
        require(health.status_code == 200, "staging backend health not 200")
        require(str(health.json().get("environment", "")).lower() != "production",
                "refusing to test production environment")
        token, user_id = await create_synthetic(http, "restart")
        session_id = "ct-restart-" + uuid.uuid4().hex

        initial_scene, _ = await exercise_socket(token, user_id, session_id)
        require(bool(initial_scene), "first scene was not delivered")
        report("STAGING_RESTART_READY", status="awaiting_preview_redeploy",
               pause_seconds=PAUSE_SECONDS, checkpoint_created=True)
        await asyncio.sleep(PAUSE_SECONDS)

        health_after = await http.get("/health")
        require(health_after.status_code == 200, "staging backend did not recover after redeploy")
        async with websockets.connect(
            socket_url(token, session_id, topic="Compare one half to one third", resume=True),
            open_timeout=25, max_size=5_000_000,
        ) as ws:
            state = await recv_until(
                ws, lambda msg: msg.get("event_type") == "system_state",
                limit=25, name="post-restart auth",
            )
            require(str(state.get("user_id")) == user_id, "post-restart account owner mismatch")
            require(state.get("session_id") == session_id, "post-restart session mismatch")
            restored = await recv_until(ws, is_scene, limit=85, name="post-restart scene")
            actual = scene_id(restored)
            require(bool(actual), "post-restart scene was blank")
            require(actual == initial_scene,
                    "saved checkpoint was not restored with same scene identity")
            report("restart_checkpoint_restored", status="passed", same_scene=True)
        report("result", status="passed",
               limitation="requires separate Railway deployment observation to prove process recycled")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        # Never log a token, URL query, credential or platform exception detail.
        report("result", status="failed", reason=type(exc).__name__)
        sys.exit(1)
