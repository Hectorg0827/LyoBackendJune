#!/usr/bin/env python3
"""Staging validation kit — confirm REAL LLM output quality with live credentials.

The test suite verifies wiring keyless (every LLM call hits the graceful
fallback). This script is the missing piece: run it where the API keys live
(Railway, or locally with GEMINI_API_KEY exported) and it tells you, per
feature, whether you got a REAL model response or the fallback — and prints the
actual text so a human can judge quality.

Two modes:

  # Rich mode — boots the app in-process, seeds a learner, shows full
  # personalized output (greeting, coaching tone, challenge, hints).
  GEMINI_API_KEY=... python scripts/staging_validation.py --in-process

  # Remote mode — drives a live deployment over HTTP (validates the actual
  # Railway box). Registers a throwaway user; classifies each AI response.
  python scripts/staging_validation.py --base-url https://<your-app>.up.railway.app

Exit code 0 = all REAL responses; 1 = degraded/fallback or failures detected.
"""
import argparse
import asyncio
import os
import sys
import time
import uuid

# Phrases the resilience manager emits when ALL providers fail. If a response
# matches one of these, the AI layer degraded — the keys are not working.
FALLBACK_MARKERS = (
    "temporarily unable to process",
    "experiencing technical issues",
    "ai services unavailable",
    "retry shortly",
    "please retry in a minute",
)

GREEN, RED, YEL, RST = "\033[92m", "\033[91m", "\033[93m", "\033[0m"
real_count = 0
degraded_count = 0


def classify(text: str) -> bool:
    """True if `text` looks like a REAL model response (not a fallback)."""
    if not text:
        return False
    low = text.lower()
    return not any(m in low for m in FALLBACK_MARKERS)


def banner(title):
    print(f"\n{'='*70}\n  {title}\n{'='*70}")


def report(name, is_real, sample="", note=""):
    global real_count, degraded_count
    if is_real:
        real_count += 1
        tag = f"{GREEN}REAL{RST}"
    else:
        degraded_count += 1
        tag = f"{RED}FALLBACK/DEGRADED{RST}"
    print(f"\n[{tag}] {name}" + (f"  ({note})" if note else ""))
    if sample:
        snippet = sample if len(sample) < 600 else sample[:600] + " …"
        print("  " + snippet.replace("\n", "\n  "))


# ============================================================ AI key probe
async def probe_llm_in_process():
    """Directly ask the resilience manager — definitive 'are the keys live' check."""
    banner("AI PROVIDER PROBE (in-process)")
    from lyo_app.core.ai_resilience import ai_resilience_manager
    health = await ai_resilience_manager.get_health_status()
    configured = {n: m["configured"] for n, m in health.get("models", {}).items()}
    print("  Models configured (api_key present):")
    for n, ok in configured.items():
        print(f"    {GREEN+'✓'+RST if ok else RED+'✗'+RST} {n}")
    if not any(configured.values()):
        print(f"\n  {RED}No model has an API key configured.{RST} "
              "Set GEMINI_API_KEY (or GOOGLE_API_KEY / OPENAI_API_KEY).")

    t0 = time.time()
    resp = await ai_resilience_manager.chat_completion(
        messages=[{"role": "user", "content": "Reply with exactly: PONG"}],
        max_tokens=10, use_cache=False)
    dt = time.time() - t0
    content = (resp or {}).get("content", "")
    is_real = not resp.get("is_fallback") and classify(content)
    report("direct chat_completion", is_real,
           sample=f"model={resp.get('model')} latency={dt:.2f}s -> {content!r}",
           note="is_fallback=%s" % resp.get("is_fallback"))
    return is_real


# ============================================================ in-process rich
async def seed_learner(uid, affect, masteries):
    from lyo_app.core.database import AsyncSessionLocal
    from lyo_app.personalization.models import LearnerState, LearnerMastery, AffectState
    async with AsyncSessionLocal() as db:
        db.add(LearnerState(user_id=uid, current_affect=AffectState(affect),
                            fatigue_level=0.3, focus_level=0.7, reading_level=9,
                            preferred_pace="moderate"))
        for sid, lvl in masteries.items():
            db.add(LearnerMastery(user_id=uid, skill_id=sid, mastery_level=lvl))
        await db.commit()


def run_in_process():
    """Boot the app locally (uses whatever keys are in the environment)."""
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("SECRET_KEY", "staging-validation-secret-key-32-chars-min-xx")
    import tempfile
    os.environ.setdefault(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{os.path.join(tempfile.mkdtemp(), 'staging.db')}")

    from starlette.testclient import TestClient
    import lyo_app.enhanced_main as m
    from lyo_app.core.database import init_db
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())

    loop.run_until_complete(probe_llm_in_process())

    client = TestClient(m.app, raise_server_exceptions=False)
    email = f"stg_{uuid.uuid4().hex[:8]}@x.com"
    client.post("/auth/register", json={
        "email": email, "username": email.split("@")[0], "password": "StagePass123!",
        "confirm_password": "StagePass123!", "first_name": "Stg"})
    body = client.post("/auth/login", json={"email": email, "password": "StagePass123!"}).json()
    h = {"Authorization": f"Bearer {body['access_token']}", "X-Forwarded-For": "10.90.0.1"}
    uid = body["user"]["id"]

    # Seed a FRUSTRATED learner weak in quadratics so we can judge whether the
    # coaching directive actually softens the tone of the real model output.
    loop.run_until_complete(seed_learner(
        uid, "frustrated", {"algebra": 0.9, "quadratics": 0.15}))

    drive_http(client, h, uid, rich=True)


# ============================================================ HTTP driver
def drive_http(client, headers, uid, *, rich):
    banner("FEATURE OUTPUT QUALITY (judge the text below by hand)")

    # 1. Greeting
    g = client.get("/api/v1/chat/greeting", headers=headers)
    gj = g.json() if g.status_code == 200 else {}
    report("greeting", classify(gj.get("greeting", "")),
           sample=gj.get("greeting", f"HTTP {g.status_code}"),
           note=f"context_used={gj.get('context_used')}")

    # 2. Chat tutoring response (frustrated learner -> expect empathetic tone)
    c = client.post("/api/v1/chat", headers=headers,
                    json={"message": "I keep getting quadratic equations wrong and I'm frustrated."})
    cj = c.json() if c.status_code == 200 else {}
    resp_text = cj.get("response") or cj.get("message") or str(cj)[:300]
    report("chat tutoring response", classify(resp_text), sample=resp_text,
           note="frustrated learner — look for warmth + a worked example")

    # 3. Identity arc (deterministic — sanity, not an LLM check)
    idr = client.get("/api/v1/me/identity", headers=headers)
    if idr.status_code == 200:
        arc = idr.json().get("learning_arc", {}).get("summary", "")
        print(f"\n[{YEL}INFO{RST}] identity arc (deterministic): {arc}")

    # 4. Social: form a pod, generate a challenge (the key LLM social path)
    pod = client.post("/api/v1/collaboration/ai/study-pods?subject=Math&max_size=3",
                      headers=headers)
    gid = pod.json().get("group_id") if pod.status_code == 200 else None
    if gid:
        ch = client.post(f"/api/v1/collaboration/ai/groups/{gid}/challenge", headers=headers)
        cj = ch.json() if ch.status_code == 200 else {}
        # `degraded` is the authoritative flag from the server side.
        is_real = ch.status_code == 200 and not cj.get("degraded", True)
        report("group challenge", is_real, sample=cj.get("challenge", f"HTTP {ch.status_code}"),
               note=f"degraded={cj.get('degraded')}")

        mod = client.get(f"/api/v1/collaboration/ai/groups/{gid}/moderation", headers=headers)
        mj = mod.json() if mod.status_code == 200 else {}
        report("moderation summary", mod.status_code == 200 and not mj.get("degraded", True),
               sample=mj.get("summary", f"HTTP {mod.status_code}"),
               note=f"degraded={mj.get('degraded')}")


def run_remote(base_url):
    import httpx
    base = base_url.rstrip("/")
    banner(f"REMOTE STAGING VALIDATION -> {base}")

    # AI health probe via the public study-mode health endpoint.
    try:
        h = httpx.get(f"{base}/api/v1/study-mode/health", timeout=30)
        print(f"  study-mode health: HTTP {h.status_code} -> {str(h.json())[:300]}")
    except Exception as e:  # noqa: BLE001
        print(f"  {YEL}health probe failed: {e}{RST}")

    client = httpx.Client(base_url=base, timeout=60, follow_redirects=True)
    # thin adapter so drive_http works with httpx like a TestClient
    class _Adapter:
        def get(self, url, headers=None): return client.get(url, headers=headers)
        def post(self, url, headers=None, json=None): return client.post(url, headers=headers, json=json)
    a = _Adapter()

    email = f"stg_{uuid.uuid4().hex[:8]}@x.com"
    a.post("/auth/register", json={
        "email": email, "username": email.split("@")[0], "password": "StagePass123!",
        "confirm_password": "StagePass123!", "first_name": "Stg"})
    login = a.post("/auth/login", json={"email": email, "password": "StagePass123!"})
    if login.status_code != 200:
        print(f"{RED}login failed: HTTP {login.status_code} {login.text[:200]}{RST}")
        return
    body = login.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    uid = body.get("user", {}).get("id")
    print(f"  registered throwaway user id={uid}")
    print(f"  {YEL}note:{RST} remote mode can't seed mastery/affect; personalization "
          "depth is limited, but REAL-vs-FALLBACK classification is valid.")
    drive_http(a, headers, uid, rich=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in-process", action="store_true",
                    help="Boot the app locally and run the rich, seeded validation.")
    ap.add_argument("--base-url", help="Validate a live deployment over HTTP.")
    args = ap.parse_args()

    if not args.in_process and not args.base_url:
        ap.error("choose one: --in-process  OR  --base-url https://...")

    if args.in_process:
        run_in_process()
    else:
        run_remote(args.base_url)

    banner("SUMMARY")
    total = real_count + degraded_count
    print(f"  REAL responses:      {GREEN}{real_count}{RST} / {total}")
    print(f"  FALLBACK/DEGRADED:   {RED}{degraded_count}{RST} / {total}")
    if degraded_count:
        print(f"\n  {RED}Some AI paths degraded.{RST} Check that GEMINI_API_KEY is set "
              "in the running environment and the circuit breaker isn't open.")
        sys.exit(1)
    print(f"\n  {GREEN}All exercised AI paths returned real model output.{RST}")
    sys.exit(0)


if __name__ == "__main__":
    main()
