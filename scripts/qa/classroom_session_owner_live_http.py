#!/usr/bin/env python3
"""Two-account HTTP isolation check against LYO's isolated staging backend.

Creates two disposable test learners. Verifies both read and delete routes
require authentication and enforce ownership. Never calls AI/TTS; all
requests are limited to named staging auth and session endpoints. Delete
both synthetic accounts on every exit, and fail if cleanup cannot be proved.
Do not print tokens, session IDs, learner credentials or server responses.
"""
import json
import secrets
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

API = "https://lyojourneystagingbackend-staging.up.railway.app"
ALLOWED_EXACT = {
    "/openapi.json",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/me",
    "/auth/me",
    "/api/v1/classroom/session",
}


def request(method, path, body=None, token=None):
    parsed = urlsplit(API)
    if parsed.scheme != "https" or parsed.hostname != "lyojourneystagingbackend-staging.up.railway.app":
        raise RuntimeError("Refusing non-staging server")
    if path not in ALLOWED_EXACT and not (
        path.startswith("/api/v1/classroom/session/")
        and path[len("/api/v1/classroom/session/"):].count("/") == 0
    ):
        raise RuntimeError("Refusing non-allowlisted API request")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = Request(API + path, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=20) as res:
            raw = res.read(8_000_001)
            if len(raw) > 8_000_000:
                raise RuntimeError('Staging API response exceeded safe bound')
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as err:
        # Error bodies and headers may contain sensitive trace data.
        return err.code, {}


def student(label):
    nonce = secrets.token_hex(12)
    password = "LYO-QA-" + secrets.token_hex(20) + "aA9!"
    return {
        "email": "lyo-owner-qa-" + nonce + "@example.org",
        "username": "ownerqa" + nonce[:16],
        "password": password, "confirm_password": password,
        "first_name": label, "last_name": "SyntheticQA",
    }


def create_student(info):
    for attempt in range(3):
        status, payload = request("POST", "/api/v1/auth/register", info)
        if status in (200, 201):
            token = payload.get("access_token")
            if not token:
                code, login = request("POST", "/api/v1/auth/login", {
                    "email": info["email"], "password": info["password"],
                })
                if code != 200 or not login.get("access_token"):
                    raise RuntimeError("Account registered but cleanup token unavailable")
                token = login["access_token"]
            return token
        if status != 429 or attempt == 2:
            raise RuntimeError("Registration failed (HTTP " + str(status) + ")")
        time.sleep(65)
    raise RuntimeError("Registration retries exhausted")


def assert_status(actual, expected, check):
    valid = expected if isinstance(expected, tuple) else (expected,)
    if actual not in valid:
        raise RuntimeError(check + ": unexpected HTTP " + str(actual))


def main():
    paths = {}
    cleaned = set()
    valid = False
    try:
        code, schema = request("GET", "/openapi.json")
        assert_status(code, 200, "OpenAPI")
        if "delete" not in schema.get("paths", {}).get("/auth/me", {}):
            raise RuntimeError("Synthetic account deletion contract missing")
        route_path = "/api/v1/classroom/session/{session_id}"
        ops = schema.get("paths", {}).get(route_path, {})
        if not {"get", "delete"}.issubset(ops):
            raise RuntimeError("Session read/delete contract missing")
        print("PASS: explicit synthetic-account cleanup and session routes exist")

        first = student("First")
        second = student("Second")
        # Use separately created authenticated users and track cleanup.
        for key, info in (("A", first), ("B", second)):
            paths[key] = {"info": info, "token": None}
            paths[key]["token"] = create_student(info)
            code, me = request("GET", "/api/v1/auth/me", token=paths[key]["token"])
            assert_status(code, 200, "Account identity")
            paths[key]["id"] = str(me.get("id"))
            if not me.get("id"):
                raise RuntimeError("No stable authenticated user ID")
        if paths["A"]["id"] == paths["B"]["id"]:
            raise RuntimeError("Two test accounts collapsed to one identity")
        print("PASS: distinct authenticated synthetic identities")

        code, created = request("POST", "/api/v1/classroom/session",
            body={"preferences":{"language":"en-US"}},
            token=paths["A"]["token"])
        assert_status(code, 200, "Owner Classroom session create")
        session = created.get("session_id")
        if not isinstance(session, str) or not session:
            raise RuntimeError("Classroom returned no session identifier")
        url = "/api/v1/classroom/session/" + session

        code, details = request("GET", url, token=paths["A"]["token"])
        assert_status(code, 200, "Owner session GET")
        if details.get("session_id") != session:
            raise RuntimeError("Owner GET returned incorrect session")
        print("PASS: owner can read own Classroom session")

        for method in ("GET", "DELETE"):
            code, _ = request(method, url, token=paths["B"]["token"])
            assert_status(code, 404, "Cross-user "+method)
            code, _ = request(method, url)
            assert_status(code, (401, 403), "Anonymous "+method)
        print("PASS: foreign owner and anonymous GET/DELETE rejected")

        code, details = request("GET", url, token=paths["A"]["token"])
        assert_status(code, 200, "Other user's DELETE cannot end owner session")
        code, ended = request("DELETE", url, token=paths["A"]["token"])
        assert_status(code, 200, "Owner session DELETE")
        if ended.get("status") != "ended":
            raise RuntimeError("Owner session deletion not acknowledged")
        code, _ = request("GET", url, token=paths["A"]["token"])
        assert_status(code, 404, "Deleted session must remain inaccessible")
        print("PASS: owner can end session, foreign delete cannot, no stale session")
        valid = True
    except Exception as exc:
        print("FAIL: " + type(exc).__name__ + " (" + str(exc)[:90] + ")", file=sys.stderr)
    finally:
        for key, state in paths.items():
            token = state.get("token")
            if not token:
                print("CLEANUP BLOCKED for " + key, file=sys.stderr)
                valid = False
                continue
            status, result = request("DELETE", "/auth/me", token=token)
            if status != 200 or result.get("deleted") is not True:
                # If short-lived auth expired, retry with that test learner only.
                code, login = request("POST", "/api/v1/auth/login", {
                    "email": state["info"]["email"],
                    "password": state["info"]["password"],
                })
                if code == 200 and login.get("access_token"):
                    status, result = request("DELETE", "/auth/me", token=login["access_token"])
            if status == 200 and result.get("deleted") is True:
                cleaned.add(key)
            else:
                valid = False
                print("CLEANUP FAILED for " + key, file=sys.stderr)
        if paths and cleaned == set(paths):
            print("PASS: all synthetic staging learners permanently deleted")
    return 0 if valid and cleaned == set(paths) and len(paths) == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
