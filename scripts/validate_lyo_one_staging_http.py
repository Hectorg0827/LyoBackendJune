#!/usr/bin/env python3
"""Authenticated external HTTP smoke of Lyo One, on a dedicated staging host.

Only synthetic learners, goals and navigation records. This script NEVER
targets the public Lyo production API, any user accounts, or any real exams.
No external model credentials are needed for the journey API.
"""
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

STAGING_HOST = "lyojourneystagingbackend-staging.up.railway.app"
BASE = "https://" + STAGING_HOST
STAGING_WEB = "https://lyoonestagingweb-staging.up.railway.app"
GOALS = "/api/v1/me/coach/goals"
JOURNEYS = "/api/v1/me/coach/journeys"


def require_staging():
    if os.environ.get("LYO_ONE_STAGING_SMOKE") != "1":
        raise RuntimeError("LYO_ONE_STAGING_SMOKE=1 is required")
    if urllib.parse.urlparse(BASE).hostname != STAGING_HOST:
        raise RuntimeError("Refusing to test any non-isolated domain")
    for name in ("LYO_ONE_EXPECTED_BACKEND_SHA", "LYO_ONE_EXPECTED_CLIENT_SHA"):
        value = os.environ.get(name)
        if value is not None and not re.fullmatch(r"[0-9a-f]{40}", value):
            raise RuntimeError(f"{name} must be a full commit SHA")


def verify_deployed_revisions():
    expected_backend = os.environ.get("LYO_ONE_EXPECTED_BACKEND_SHA")
    expected_client = os.environ.get("LYO_ONE_EXPECTED_CLIENT_SHA")
    code, health = http("/health")
    if code != 200 or not isinstance(health, dict):
        raise AssertionError("Staging backend health is unavailable")
    if expected_backend and health.get("commit_sha") != expected_backend:
        raise AssertionError(f"Backend revision mismatch: expected {expected_backend}, received {health.get('commit_sha')}")
    if expected_client:
        req = urllib.request.Request(STAGING_WEB + "/api/health", headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=35) as response:
            client_health = json.load(response)
        if client_health.get("commit") != expected_client:
            raise AssertionError(f"Client revision mismatch: expected {expected_client}, received {client_health.get('commit')}")
    return health


def http(path, method="GET", body=None, token=None, timeout=35):
    headers = {"Accept": "application/json", "Cache-Control": "no-cache", "User-Agent": "LyoOne-isolated-staging-gate/1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(320000)
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = raw.decode("utf-8", errors="replace")
            return response.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read(2500)
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw.decode("utf-8", errors="replace")[:800]
        return exc.code, payload


def expect(name, method, path, status, body=None, token=None):
    code, data = http(path, method=method, body=body, token=token)
    if code != status:
        # Never print credentials, bearer tokens, profile data, or email.
        detail = data.get("detail", None) if isinstance(data, dict) else str(data)[:200]
        raise AssertionError(f"{name}: expected HTTP {status}, received {code}; detail={str(detail)[:250]}")
    print(f"PASS {name}: HTTP {code}")
    return data


def new_actor(label):
    suffix = uuid.uuid4().hex[:16]
    pwd = "Lyo1!" + secrets.token_urlsafe(18)
    body = {
        "username": f"smoke{label}{suffix}"[:40],
        "email": f"lyo-one-staging-{label}-{suffix}@example.com",
        "password": pwd,
        "confirm_password": pwd,
        "first_name": "Synthetic",
        "last_name": "Staging",
    }
    code, registration = http("/api/v1/auth/register", method="POST", body={
        "email": body["email"], "password": pwd, "full_name": "Synthetic Staging",
    })
    if code != 200 or not isinstance(registration, dict) or not registration.get("user_id"):
        keys = sorted(registration.keys()) if isinstance(registration, dict) else ["non-json"]
        raise AssertionError(f"Registration returned HTTP {code} with fields={keys}")
    print(f"PASS register synthetic learner {label}: HTTP {code}")
    login = expect(
        f"authenticate synthetic learner {label}", "POST",
        "/api/v1/auth/login", 200,
        {"email": body["email"], "password": pwd},
    )
    if not isinstance(login, dict) or not isinstance(login.get("access_token"), str):
        raise AssertionError("Authenticated login did not return an access token")
    return login["access_token"]


def main():
    require_staging()
    # Give Railway deployment/hostname a bounded window to become available.
    for attempt in range(24):
        try:
            verify_deployed_revisions()
            break
        except (OSError, TimeoutError, AssertionError):
            pass
        time.sleep(7)
    else:
        raise AssertionError("Expected staging revision(s) did not become accessible within the bounded check")
    print("PASS isolated staging health and expected deployed revisions")

    user_a = new_actor("a")
    user_b = new_actor("b")
    empty = expect("new learner receives a valid empty Coach response", "GET",
                   "/api/v1/me/coach/today", 200, token=user_a)
    assert empty["total_minutes"] == 0 and empty["primary_goal_id"] is None
    assert empty["active_goals"] == [] and empty["mission"] == [] and empty["readiness"] == {}
    status_code, stream = http("/api/v1/lyo2/chat/stream", method="POST", token=user_a,
                              body={"text": "What should I study?", "client_message_id": "empty-coach-" + uuid.uuid4().hex}, timeout=55)
    assert status_code == 200 and isinstance(stream, str), "Empty-goal Coach did not return SSE"
    events = [json.loads(line[6:]) for line in stream.splitlines()
              if line.startswith("data: ") and line[6:].strip() != "[DONE]"]
    assert any(event.get("type") == "answer" for event in events), "Empty-goal Coach omitted its readable answer"
    assert not any(event.get("type") == "error" for event in events), "Empty-goal Coach emitted an error"
    assert "do not have an active learning goal" in stream, "Empty-goal Coach did not invite a learning goal"
    print("PASS new learner Coach Chat SSE without fabricated readiness")
    goal = expect(
        "create evidence-scoped learning goal", "POST", GOALS, 201,
        {"goal_type": "mastery", "title": "Synthetic chemical bonding",
         "subject": "Chemistry",
         "constraints": {"daily_minutes": 15},
         "skills": [{"name": "Covalent bonds", "concept_id": "covalent-bonds"}]},
        user_a,
    )
    goal_id = goal.get("goal", {}).get("id")
    if not goal_id:
        raise AssertionError("Coach goal identity not returned")

    today = expect("load authenticated Coach mission", "GET",
                   "/api/v1/me/coach/today", 200, token=user_a)
    if not isinstance(today.get("mission"), list) or goal_id not in [g["id"] for g in today.get("active_goals", [])]:
        raise AssertionError("Coach mission did not reference the canonical goal")

    start = {"request_id": "start-" + uuid.uuid4().hex, "goal_id": goal_id,
             "origin_surface": "chat", "origin_ref": "synthetic-chat",
             "context": {"chat_session_id": "synthetic-chat"}}
    journey = expect("start durable learning journey", "POST", JOURNEYS, 201, start, user_a)
    journey_id = journey["id"]
    jp = JOURNEYS + "/" + urllib.parse.quote(journey_id, safe="")
    if journey["revision"] != 0:
        raise AssertionError("new journey must start at revision zero")

    enter = {"request_id": "enter-" + uuid.uuid4().hex,
             "expected_revision": 0, "target_surface": "classroom",
             "target_ref": "covalent-bonds",
             "context": {"concept_id": "covalent-bonds"}}
    entry = expect("save Coach -> Classroom handoff", "POST", jp + "/handoffs", 201, enter, user_a)
    if entry["revision"] != 1:
        raise AssertionError("Classroom handoff did not advance revision")

    back = {"request_id": "return-" + uuid.uuid4().hex,
            "expected_revision": 1, "target_surface": "chat",
            "target_ref": "synthetic-chat", "context": {}}
    returned = expect("save Classroom -> Chat return", "POST", jp + "/handoffs", 201, back, user_a)
    assert returned["revision"] == 2
    reopened = expect("reload durable journey", "GET", jp, 200, token=user_a)
    if reopened["revision"] != 2 or reopened["active_surface"] != "chat" or reopened["context"]["concept_id"] != "covalent-bonds":
        raise AssertionError("Reopened journey lost its context")

    replay = expect("idempotent handoff retry", "POST", jp + "/handoffs", 201, enter, user_a)
    if replay["id"] != entry["id"]:
        raise AssertionError("Retry created duplicate handoff")
    start_replay = expect("idempotent journey start replay", "POST", JOURNEYS, 201, start, user_a)
    if start_replay["id"] != journey_id:
        raise AssertionError("Retry created duplicate journey")

    stale = {"request_id": "stale-" + uuid.uuid4().hex, "expected_revision": 0,
             "target_surface": "test_prep", "context": {}}
    expect("outdated tab revision rejected", "POST", jp + "/handoffs", 409, stale, user_a)
    expect("cross-user journey read denied", "GET", jp, 404, token=user_b)
    expect("cross-user handoff denied", "POST", jp + "/handoffs", 404, stale, user_b)

    other_exam = {"request_id": "wrong-exam-" + uuid.uuid4().hex,
                  "goal_id": goal_id, "origin_surface": "test_prep",
                  "context": {"test_profile_id": "not-this-goal"}}
    expect("wrong exam profile cannot be attached", "POST", JOURNEYS, 422, other_exam, user_a)
    # The Test Prep engine must allocate independent exam identities,
    # rather than reopening the learner's previous stale test.
    prep = "/api/v1/me/study_plans"
    exam1_key = "exam-" + uuid.uuid4().hex
    exam2_key = "exam-" + uuid.uuid4().hex
    exam1 = expect("create first distinct synthetic exam", "POST",
                   prep + "/profiles/start", 201, {"request_id": exam1_key}, user_a)
    exam2 = expect("create second distinct synthetic exam", "POST",
                   prep + "/profiles/start", 201, {"request_id": exam2_key}, user_a)
    if not exam1.get("profile_id") or exam1["profile_id"] == exam2.get("profile_id"):
        raise AssertionError("Test Prep did not produce distinct exam profile IDs")
    first_replay = expect("exam creation retry does not duplicate exam", "POST",
                          prep + "/profiles/start", 201, {"request_id": exam1_key}, user_a)
    if first_replay.get("profile_id") != exam1["profile_id"]:
        raise AssertionError("Idempotent exam start reused another exam")
    for selected in (exam1["profile_id"], exam2["profile_id"]):
        state = expect("select original synthetic exam by profile ID", "GET",
            prep + "/state?profile_id=" + urllib.parse.quote(selected, safe=""),
            200, token=user_a)
        if state.get("profile", {}).get("id") != selected:
            raise AssertionError("Explicit exam selection returned another profile")
    expect("another learner cannot open first synthetic exam", "GET",
           prep + "/state?profile_id=" + urllib.parse.quote(exam1["profile_id"], safe=""),
           404, token=user_b)

    # Explicit Coach questions must be handled by the canonical Chat stream
    # without requiring an unrelated external generative-model call.
    stream_request = {"text": "What should I study today?",
                      "client_message_id": "coach-" + uuid.uuid4().hex}
    status_code, stream = http("/api/v1/lyo2/chat/stream", method="POST",
                               body=stream_request, token=user_a, timeout=55)
    if status_code != 200 or not isinstance(stream, str):
        raise AssertionError(f"Coach chat stream returned HTTP {status_code} without SSE data")
    if '"coach_mission"' not in stream or '"answer"' not in stream:
        # Synthetic staging conversation only; do not print bearer tokens.
        types = re.findall(r'"type"\s*:\s*"([^"]+)"', stream)
        event_names = re.findall(r"(?m)^event:\s*([\\w-]+)", stream)
        raise AssertionError(f"Coach Chat SSE missing event(s); types={types[:15]}, events={event_names[:15]}, prefix={stream[:550]!r}")
    print("PASS authentic Coach Chat SSE mission and answer")

    verify_deployed_revisions()
    print("PASS expected backend/client revisions remained stable through validation")
    print("PASS authenticated staging journey, Test Prep profile isolation and Coach streaming")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL staging smoke: {str(exc)[:500]}", file=sys.stderr)
        sys.exit(1)
