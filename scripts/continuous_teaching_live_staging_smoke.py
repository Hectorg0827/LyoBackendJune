"""Bounded external transport smoke for the isolated LYO Continuous Teaching staging host.

Runs from GitHub-hosted CI, never from production or against other hosts.
Creates two clearly labelled synthetic learners; these persist in staging.
Does not claim database durability, grading accuracy, or physical audio acceptance.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import time
import uuid
from urllib.parse import urlencode, urlsplit

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

HOST = "lyo-continuousteaching-preview-backend-staging.up.railway.app"
BASE = f"https://{HOST}"
WS_ENDPOINT = f"wss://{HOST}/api/v1/classroom/ws/connect"


def verify_target() -> None:
    configured = os.getenv("LYO_STAGING_SMOKE_URL", BASE).rstrip("/")
    parsed = urlsplit(configured)
    if configured != BASE or parsed.hostname != HOST or parsed.scheme != "https":
        raise RuntimeError("Refusing any target other than the pinned isolated staging host")
    if os.getenv("LYO_ALLOW_PRODUCTION_TEST", ""):
        raise RuntimeError("Production override must not be set for this workflow")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def report(name: str, **properties) -> None:
    safe = {key: value for key, value in properties.items() if key not in {"token", "password", "email"}}
    print("STAGING_LIVE " + json.dumps({"check": name, **safe}, sort_keys=True), flush=True)


async def create_synthetic(client: httpx.AsyncClient, marker: str) -> tuple[str, str]:
    identity = uuid.uuid4().hex
    email = f"lyo-ct-stage-{marker}-{identity[:12]}@example.com"
    password = "Aa1!" + secrets.token_urlsafe(24)
    body = {
        "email": email,
        "username": f"ct{marker}{identity[:12]}",
        "password": password,
        "confirm_password": password,
        "first_name": "Staging",
        "last_name": "Test",
    }
    response = await client.post("/auth/register", json=body)
    require(response.status_code == 201,
            f"synthetic account registration {marker} returned {response.status_code}")
    payload = response.json()
    token = payload.get("access_token")
    user_id = str((payload.get("user") or {}).get("id") or "")
    require(bool(token and user_id), "account creation did not return token and user ID")
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    require(me.status_code == 200, f"authenticated /auth/me {marker}: {me.status_code}")
    require(str(me.json().get("id")) == user_id, "authenticated account identity mismatch")
    report("synthetic_auth", user=marker, status="passed")
    return token, user_id


async def recv_until(ws, predicate, *, limit: float, name: str) -> dict:
    deadline = time.monotonic() + limit
    while True:
        timeout = deadline - time.monotonic()
        require(timeout > 0, f"timed out waiting for {name}")
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        try:
            message = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if isinstance(message, dict) and predicate(message):
            return message


def socket_url(token: str, session_id: str, *, topic: str, resume: bool) -> str:
    params = {
        "token": token,
        "session_id": session_id,
        "topic": topic,
        "language": "en-US",
        "continuous_teaching": "0",
        "resume": "1" if resume else "0",
    }
    return WS_ENDPOINT + "?" + urlencode(params)


def is_scene(msg: dict) -> bool:
    return msg.get("event_type") in {"scene_start", "scene_update"}


def scene_id(msg: dict) -> str:
    scene = msg.get("scene") or (msg.get("data") or {}).get("scene") or {}
    return str(scene.get("scene_id", ""))


async def check_no_token() -> None:
    url = WS_ENDPOINT + "?" + urlencode({"session_id": "ct-unauth-" + uuid.uuid4().hex[:10]})
    try:
        async with websockets.connect(url, open_timeout=15) as ws:
            try:
                await asyncio.wait_for(ws.recv(), timeout=10)
            except ConnectionClosed as exc:
                require(exc.code == 4001, f"unexpected unauthenticated close code: {exc.code}")
                report("websocket_auth_reject", status="passed", close_code=exc.code)
                return
            raise RuntimeError("unauthenticated WebSocket was allowed to receive data")
    except InvalidStatus as exc:
        require(exc.response.status in (401, 403), f"unexpected auth HTTP status: {exc.response.status}")
        report("websocket_auth_reject", status="passed", http_status=exc.response.status)


async def exercise_socket(token: str, user_id: str, session_id: str) -> tuple[str, int]:
    url = socket_url(token, session_id, topic="Compare one half to one third", resume=False)
    async with websockets.connect(url, open_timeout=20, max_size=5_000_000) as ws:
        system = await recv_until(ws, lambda x: x.get("event_type") == "system_state",
                                  limit=20, name="authenticated system state")
        require(str(system.get("user_id")) == user_id, "socket returned a different learner identity")
        require(system.get("session_id") == session_id, "socket returned a different session")
        report("websocket_authenticated", status="passed")

        forged = {
            "event_type": "user_action",
            "action_intent": "continue",
            "session_id": "other-learner-session",
            "user_id": user_id,
        }
        await ws.send(json.dumps(forged))
        error = await recv_until(
            ws,
            lambda x: x.get("event_type") == "error"
                and (x.get("data") or {}).get("error") == "session_mismatch",
            limit=15, name="forged session isolation error",
        )
        require(str(error.get("user_id")) == user_id, "forged action routed to wrong user")
        report("forged_session_denied", status="passed")

        scene = await recv_until(ws, is_scene, limit=110, name="first authoritative lesson scene")
        sid = scene_id(scene)
        require(sid and not sid.startswith(("db_error_", "error_welcome_", "welcome_")),
                "received only a fallback scene instead of an authoritative teacher scene")
        report("authoritative_scene", status="passed", scene_seen=True)
        return sid, 1


async def reconnect(token: str, user_id: str, session_id: str) -> None:
    url = socket_url(token, session_id, topic="Compare one half to one third", resume=True)
    async with websockets.connect(url, open_timeout=20, max_size=5_000_000) as ws:
        system = await recv_until(ws, lambda x: x.get("event_type") == "system_state",
                                  limit=20, name="resumed authenticated system state")
        require(str(system.get("user_id")) == user_id and system.get("session_id") == session_id,
                "reconnect returned a different learner or session")
        report("authenticated_reconnect", status="passed", note="transport identity; not database durability")


async def run() -> None:
    verify_target()
    async with httpx.AsyncClient(base_url=BASE, timeout=25, follow_redirects=False) as client:
        health = await client.get("/health")
        require(health.status_code == 200, f"staging health returned {health.status_code}")
        payload = health.json()
        require(payload.get("status") in ("healthy", "ok"),
                "staging health payload did not indicate a healthy service")
        require(str(payload.get("environment", "")).lower() != "production",
                "health payload indicates a production service")
        report("pinned_staging_health", status="passed")

        await check_no_token()
        a_token, a_id = await create_synthetic(client, "a")
        b_token, b_id = await create_synthetic(client, "b")
        require(a_id != b_id, "synthetic account IDs collide")

        session_id = "ct-stage-" + uuid.uuid4().hex
        await exercise_socket(a_token, a_id, session_id)
        await reconnect(a_token, a_id, session_id)
        # Second account has its own independent token; no shared credentials.
        b_me = await client.get("/auth/me", headers={"Authorization": f"Bearer {b_token}"})
        require(b_me.status_code == 200 and str(b_me.json().get("id")) == b_id,
                "second learner session is not isolated")
        report("second_authenticated_identity", status="passed")
        report("result", status="passed", limitations=[
            "persistent database checkpoint not directly queried",
            "no graded answer or replay deduplication checked",
            "no physical Android speech verified",
        ])


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as exc:
        # Never print private token, email, or password; HTTP/WS error messages
        # above carry bounded status only.
        report("result", status="failed", reason=type(exc).__name__, detail=str(exc)[:250])
        sys.exit(1)
