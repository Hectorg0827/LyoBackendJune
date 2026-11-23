#!/usr/bin/env python3
"""No-provider authenticated staging WebSocket cross-user same-ID probe.

Two disposable learner JWTs open /ws/connect on the SAME random session ID,
strictly with resume=1 and continuous_teaching=0. Missing saved scene must
return resume_unavailable, not generate a new teacher scene. Any event carrying
the other user's ID or lesson material fails. This tests connection/auth
identity and safe recovery; in-process room broadcast tests cover delivery.
No paid AI provider, external learner, or production access.
"""
import asyncio
import json
import secrets
import sys
from urllib.parse import urlencode

import websockets

from classroom_session_owner_live_http import API, request, student, create_student


async def verify_socket(token, user_id, session_id):
    params = {
        "session_id": session_id,
        "token": token,
        "topic": "synthetic-no-scene",
        "resume": "1",
        "continuous_teaching": "0",
        "client_contract_version": "2",
        "duration_minutes": "1",
        "language": "en-US",
    }
    url = API.replace("https://", "wss://") + "/api/v1/classroom/ws/connect?" + urlencode(params)
    own_state = False
    no_scene_recovered = False
    messages = 0
    async with websockets.connect(
        url, open_timeout=20, close_timeout=5, ping_interval=20,
        ping_timeout=30, max_size=100000,
    ) as socket:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 20
        while loop.time() < deadline:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=min(5, max(0.1, deadline-loop.time())))
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                break
            if len(raw) > 100000:
                raise RuntimeError("Unexpectedly large Classroom WS event")
            try:
                event = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(event, dict):
                continue
            messages += 1
            recipient = event.get("user_id")
            if recipient is not None and str(recipient) != str(user_id):
                raise RuntimeError("Cross-user WebSocket event received")
            kind = str(event.get("event_type") or event.get("type") or "").upper()
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            if kind in ("SCENE_START", "SCENE_STREAM", "COMPONENT_RENDER", "SCENE_COMPLETE"):
                raise RuntimeError("Unexpected provider/teaching scene during no-provider resume")
            if kind in ("SYSTEM_STATE", "SYSTEM_STATE_UPDATE", "SYSTEMSTATE"):
                own_state = True
            if str(data.get("error", "")).lower() == "resume_unavailable":
                no_scene_recovered = True
            if own_state and no_scene_recovered:
                # Keep both authenticated sockets connected for a bounded
                # overlap; any later misrouted events still fail the check.
                pass
    if not own_state or not no_scene_recovered:
        raise RuntimeError("Missing identity-scoped socket state or explicit resume denial")
    return messages


async def main():
    accounts = {}
    deleted = set()
    valid = False
    try:
        for label in ("A", "B"):
            person = student("Socket" + label)
            accounts[label] = {"person": person, "token": None}
            accounts[label]["token"] = create_student(person)
            code, me = request("GET", "/api/v1/auth/me", token=accounts[label]["token"])
            if code != 200 or not me.get("id"):
                raise RuntimeError("Invalid synthetic user identity")
            accounts[label]["id"] = str(me["id"])
        if accounts["A"]["id"] == accounts["B"]["id"]:
            raise RuntimeError("Distinct synthetic users received same identity")
        session_id = "lyo-ws-qa-" + secrets.token_hex(12)
        counts = await asyncio.gather(*[
            verify_socket(accounts[label]["token"], accounts[label]["id"], session_id)
            for label in ("A", "B")
        ])
        assert all(count > 0 for count in counts)
        print("PASS: two distinct JWT users connected to same session ID in staging")
        print("PASS: only own identity events; missing scene reported without AI generation")
        valid = True
    except Exception as exc:
        # Never print WebSocket URLs, bearer tokens or credentials.
        print("FAIL: "+type(exc).__name__ + " (details suppressed)", file=sys.stderr)
    finally:
        for label, item in accounts.items():
            if not item.get("token"):
                valid = False
                print("CLEANUP BLOCKED for "+label, file=sys.stderr)
                continue
            status, result = request("DELETE", "/auth/me", token=item["token"])
            if status != 200 or result.get("deleted") is not True:
                code, login = request("POST", "/api/v1/auth/login", {
                    "email": item["person"]["email"], "password": item["person"]["password"]
                })
                if code == 200 and login.get("access_token"):
                    status, result = request("DELETE", "/auth/me", token=login["access_token"])
            if status == 200 and result.get("deleted") is True:
                deleted.add(label)
            else:
                valid = False
                print("CLEANUP FAILED for "+label, file=sys.stderr)
        if len(deleted) == 2:
            print("PASS: both synthetic JWT learners permanently deleted")
    return 0 if valid and deleted == {"A", "B"} else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
