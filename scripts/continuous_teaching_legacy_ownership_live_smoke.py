"""Staging-only, real HTTP authorization/ownership smoke for legacy Classroom routes.

Creates 2 clearly marked, synthetic learners and one isolated ConversationSession.
No production, real-person accounts, grading, TTS, provider calls, or cross-tenant
data inspection. Creates only synthetic records in the dedicated preview backend.
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from continuous_teaching_live_staging_smoke import (
    BASE,
    create_synthetic,
    report,
    require,
    verify_target,
)

ROUTES = (
    ("get", "/api/v1/classroom/session/{session}"),
    ("get", "/api/v1/classroom/session/{session}/history"),
    ("post", "/api/v1/classroom/session/{session}/continue"),
    ("delete", "/api/v1/classroom/session/{session}"),
)


async def request_with(client: httpx.AsyncClient, method: str, url: str, token: str | None):
    # Never place bearer credentials or emails in logs or query parameters.
    headers = {"Authorization": "Bearer " + token} if token else {}
    return await client.request(method.upper(), url, headers=headers)


async def main() -> None:
    verify_target()
    async with httpx.AsyncClient(base_url=BASE, timeout=25, follow_redirects=False) as client:
        health = await client.get("/health")
        require(health.status_code == 200, "pinned staging health failed")
        payload = health.json()
        require(str(payload.get("environment", "")).lower() != "production",
                "refusing a production service")
        expected = "16b44150da69457e2ab738175aafc10361f349e6"
        observed = payload.get("commit_sha")
        if observed:
            require(str(observed) == expected, "staging security patch commit not active")
        report("staging_revision", status="passed", sha_confirmed=bool(observed))

        owner_token, owner_id = await create_synthetic(client, "owner")
        other_token, other_id = await create_synthetic(client, "other")
        require(owner_id != other_id, "synthetic identities must differ")

        create = await client.post(
            "/api/v1/classroom/session",
            json={"preferences": {"source": "isolated-staging-ownership-smoke"}},
            headers={"Authorization": "Bearer " + owner_token},
        )
        require(create.status_code == 200,
                "authenticated synthetic session creation failed")
        session_id = create.json().get("session_id")
        require(bool(session_id), "no synthetic session id returned")
        report("owner_session_created", status="passed")

        for method, template in ROUTES:
            url = template.format(session=session_id)
            no_auth = await request_with(client, method, url, None)
            require(no_auth.status_code in (401, 403),
                    f"anonymous {method} Classroom session route not rejected")
            report("anonymous_denied", method=method, route=template,
                   status="passed", http_status=no_auth.status_code)

        for method, template in ROUTES:
            url = template.format(session=session_id)
            other = await request_with(client, method, url, other_token)
            require(other.status_code == 404,
                    f"second learner {method} not isolated (HTTP {other.status_code})")
            report("cross_user_denied", method=method, route=template,
                   status="passed", http_status=404)

        owner_read = await request_with(client, "get", ROUTES[0][1].format(session=session_id), owner_token)
        require(owner_read.status_code == 200, "owner cannot retrieve own session")
        require(owner_read.json().get("session_id") == session_id, "incorrect owner session")
        report("owner_read", status="passed")

        owner_history = await request_with(
            client, "get", ROUTES[1][1].format(session=session_id), owner_token,
        )
        require(owner_history.status_code == 200, "owner cannot retrieve own history")
        require(owner_history.json().get("session_id") == session_id,
                "wrong owner conversation history")
        report("owner_history", status="passed")

        deleted = await request_with(
            client, "delete", ROUTES[3][1].format(session=session_id), owner_token,
        )
        require(deleted.status_code == 200, "owner cannot delete own synthetic session")
        gone = await request_with(
            client, "get", ROUTES[0][1].format(session=session_id), owner_token,
        )
        require(gone.status_code == 404, "deleted owner session remained accessible")
        report("owner_delete_and_absence", status="passed")

        report("result", status="passed", scope=(
            "anonymous and cross-user denial on 4 legacy routes; "
            "owner GET/history/delete; no actual grading/phone audio"
        ))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        # Never log bearer tokens, passwords, emails, or raw exception details.
        report("result", status="failed", reason=type(exc).__name__)
        sys.exit(1)
