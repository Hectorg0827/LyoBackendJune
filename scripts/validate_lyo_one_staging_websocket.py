#!/usr/bin/env python3
"""Safe first-frame Classroom WebSocket auth smoke against isolated staging only."""
import asyncio
import json
import os
from urllib.parse import urlparse

import websockets

from validate_lyo_one_live_classroom import (
    STAGING_API, create_synthetic_access_token, verify_candidate,
)


async def main() -> None:
    if os.getenv("LYO_ONE_STAGING_WS_AUTH_SMOKE") != "1":
        raise RuntimeError("Explicit isolated Classroom WS security opt-in required")
    if urlparse(STAGING_API).hostname != "lyojourneystagingbackend-staging.up.railway.app":
        raise RuntimeError("Refusing non-isolated staging target")
    verify_candidate()  # Full SHA + environment + configured-provider identity
    token = create_synthetic_access_token()
    url = STAGING_API.replace("https://", "wss://") + (
        "/api/v1/classroom/ws/connect"
        "?session_id=ws-security-smoke&topic=Fractions&mode=solo"
    )
    assert "token=" not in url and "api_key=" not in url
    # An ordinary learner action cannot be used as an authentication message.
    async with websockets.connect(url, open_timeout=15, close_timeout=5) as ws:
        await ws.send(json.dumps({"action_intent": "continue", "token": token}))
        try:
            await asyncio.wait_for(ws.recv(), timeout=15)
        except websockets.exceptions.ConnectionClosed as exc:
            if exc.code != 4001:
                raise AssertionError(f"Unauthenticated socket closed with {exc.code}") from exc
        else:
            raise AssertionError("Unauthenticated user action was accepted")
    # Dedicated first frame authenticates before any learner/session data is sent.
    async with websockets.connect(url, open_timeout=15, close_timeout=5) as ws:
        await ws.send(json.dumps({"type": "classroom_auth", "token": token}))
        payload = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        if payload.get("event_type", "").lower() != "system_state":
            raise AssertionError("Authenticated socket did not receive its system state")
    verify_candidate()
    print("PASS secure Classroom WebSocket auth, no JWT in URL")


if __name__ == "__main__":
    asyncio.run(main())
