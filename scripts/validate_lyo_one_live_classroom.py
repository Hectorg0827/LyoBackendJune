#!/usr/bin/env python3
"""Manual, isolated, provider-backed Classroom quality gate.

Creates an ephemeral synthetic learner and runs the *real* deployed black-box
teaching harness. No production account, DB, URL or bearer token is used.
Requires operator readiness confirmation. If a model provider is unavailable
the gate FAILS; a green /health or mocked teaching turn never counts as proof.
"""
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

STAGING_API = "https://lyojourneystagingbackend-staging.up.railway.app"
EXPECTED_HOST = "lyojourneystagingbackend-staging.up.railway.app"
SCENARIOS = {"math_fractions", "biology_photosynthesis", "physics_newton2",
             "spanish_past_tense", "business_contribution_margin"}
PROFILES = {"interrupter", "beginner", "advanced", "confident_wrong",
            "quiet_partial", "curious", "struggling", "fast_learner"}


def require_safe_target(base_url=STAGING_API):
    parsed = urllib.parse.urlparse(base_url)
    if (parsed.scheme != "https" or parsed.hostname != EXPECTED_HOST
            or parsed.path not in ("", "/") or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("Refusing to use any host other than isolated Lyo One staging")
    if os.getenv("LYO_ONE_PROVIDER_STAGING_READY") != "yes":
        raise ValueError("Provider-backed staging must be explicitly confirmed ready")


def verify_candidate():
    require_safe_target(STAGING_API)
    expected = os.getenv("LYO_ONE_EXPECTED_BACKEND_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ValueError("LYO_ONE_EXPECTED_BACKEND_SHA must identify the full deployed candidate")
    req = urllib.request.Request(STAGING_API + "/health", headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=35) as response:
        health = json.load(response)
    actual = health.get("commit_sha")
    if health.get("environment") != "staging" or actual != expected:
        raise RuntimeError(f"Isolated staging candidate mismatch: expected {expected}, received {actual}")
    models = health.get("services", {}).get("ai", {}).get("models", {})
    configured = sorted(name for name, model in models.items()
                        if name.startswith("gemini-") and model.get("configured"))
    if not configured:
        raise RuntimeError("Isolated staging has no configured Gemini provider; enter its separate GEMINI_API_KEY before running real teaching")
    return {"commit_sha": actual, "configured_gemini_models": configured}


def request(path, payload):
    req = urllib.request.Request(
        STAGING_API + path, data=json.dumps(payload).encode(),
        method="POST", headers={"Content-Type": "application/json",
                                "User-Agent": "LyoOne-TeacherQuality-Synthetic/1"},
    )
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.status, json.load(response)


def create_synthetic_access_token():
    suffix = uuid.uuid4().hex
    email = f"lyo-one-teacher-{suffix[:14]}@example.com"
    password = "Staging1!" + secrets.token_urlsafe(24)
    status, user = request("/api/v1/auth/register", {
        "email": email, "password": password, "full_name": "Synthetic Classroom QA",
    })
    if status not in (200, 201) or not user.get("user_id"):
        raise RuntimeError("Synthetic staging learner registration failed")
    status, session = request("/api/v1/auth/login", {
        "email": email, "password": password,
    })
    token = session.get("access_token")
    if status != 200 or not isinstance(token, str) or len(token) < 30:
        raise RuntimeError("Synthetic staging learner authentication failed")
    return token


def main():
    require_safe_target()
    before = verify_candidate()
    scenario = os.getenv("LYO_ONE_CLASSROOM_SCENARIO", "math_fractions")
    profile = os.getenv("LYO_ONE_CLASSROOM_PROFILE", "struggling")
    if scenario not in SCENARIOS or profile not in PROFILES:
        raise ValueError("Unsupported fixture; keep to vetted teaching scenarios")
    token = create_synthetic_access_token()
    env = os.environ.copy()
    env["LYO_ACCESS_TOKEN"] = token
    env["LYO_BASE_URL"] = STAGING_API
    output = Path("artifacts/lyo-one-classroom") / f"{scenario}-{profile}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "scripts/live_teacher_quality.py", "seed",
        "--base-url", STAGING_API, "--scenario", scenario, "--profile", profile,
        "--max-scenes", "14", "--timeout", "75",
        "--output", str(output),
    ]
    completed = subprocess.run(command, env=env, timeout=780, check=False)
    if completed.returncode:
        raise RuntimeError(f"Real Classroom teaching validation failed, exit {completed.returncode}; inspect redacted report")
    data = json.loads(output.read_text())
    checks = data.get("checks", [])
    if not checks or any(c.get("passed") is False for c in checks):
        raise RuntimeError("Missing or failed teaching quality checks")
    required = {"classroom_scene_received", "classroom_authored_instruction_delivered", "classroom_recovery_loop_absent", "chat_or_classroom_evidence_reached_record"}
    # Prevent an empty or swallowed provider-error run being marked green.
    successes = {c.get("name") for c in checks if c.get("passed") is True}
    if not required <= successes:
        raise RuntimeError(f"Missing provider-backed teaching checks: {sorted(required - successes)}")
    after = verify_candidate()
    data["deployment_validation"] = {"before": before, "after": after}
    output.write_text(json.dumps(data, indent=2))
    print("PASS actual provider-backed Classroom scenes and persisted learning evidence")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, urllib.error.HTTPError, subprocess.TimeoutExpired) as exc:
        # Do not print a bearer token or the synthetic learner's password.
        print(f"FAIL isolated Classroom provider gate: {str(exc)[:360]}", file=sys.stderr)
        sys.exit(1)
