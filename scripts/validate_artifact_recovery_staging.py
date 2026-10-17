#!/usr/bin/env python3
"""Opt-in artifact acceptance against isolated staging, never production.

Run in a trusted staging runtime with that backend's isolated Firestore access.
Credentials remain in environment variables; reports contain only synthetic data.
Fault-injection and mutation-provider suppression are covered separately by unit
tests. This runner verifies real HTTP/SSE, durable artifact reads and chat history.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
import uuid

import httpx


def require_target(url: str, expected_sha: str) -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith(".up.railway.app")
            or parsed.username or parsed.password or parsed.port
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Use an isolated HTTPS Railway service origin")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("A full expected backend commit SHA is required")
    return url.rstrip("/")


def verify_health(health: dict, expected_sha: str) -> None:
    if health.get("environment") != "staging":
        raise ValueError("Backend must identify itself as staging")
    if health.get("commit_sha") != expected_sha:
        raise ValueError("Staging revision does not match the candidate")
    services = health.get("services") or {}
    if services.get("database") != "healthy":
        raise ValueError("Staging database is unavailable")
    if services.get("firebase") != "enabled":
        raise ValueError("Isolated Firebase artifact storage is not enabled")


def decode_sse(raw: str) -> list[dict]:
    events = []
    frames = raw.replace("\r\n", "\n").split("\n\n")
    if frames[-1].strip():
        raise ValueError("Truncated SSE frame")
    for frame in frames:
        values = [line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:")]
        if not values:
            continue
        data = "\n".join(values)
        if data == "[DONE]":
            events.append({"type": "DONE"})
        else:
            event = json.loads(data)
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise ValueError("Malformed SSE event")
            events.append(event)
    return events


def completed_answer(events: list[dict], *, expect_artifact: bool) -> dict:
    if not events or events[-1].get("type") != "DONE":
        raise AssertionError("SSE did not finish through DONE")
    if sum(e.get("type") == "DONE" for e in events) != 1:
        raise AssertionError("Unexpected duplicate SSE terminator")
    if any(e.get("type") in {"error", "voice_incomplete"}
           or e.get("generation_status") == "incomplete" for e in events):
        raise AssertionError("Error or incomplete generation cannot pass")
    answers = [e for e in events if e.get("type") == "answer"]
    if len(answers) != 1 or answers[0].get("generation_status") != "completed":
        raise AssertionError("One explicitly completed answer is required")
    if not str((answers[0].get("block") or {}).get("content", {}).get("text") or "").strip():
        raise AssertionError("Completed answer is empty")
    artifacts = [e for e in events if e.get("type") == "artifact"]
    if len(artifacts) != (1 if expect_artifact else 0):
        raise AssertionError("Unexpected artifact count")
    return answers[0]


async def get_json(client, base, path, token=""):
    response = await client.get(base + path, headers={"Authorization": f"Bearer {token}"} if token else {})
    response.raise_for_status()
    return response.json()


async def verify_candidate(client, base, expected_sha, evidence=None):
    health = await get_json(client, base, "/health")
    snapshot = {"commit_sha": health.get("commit_sha"), "environment": health.get("environment"),
                "firebase": (health.get("services") or {}).get("firebase")}
    if evidence is not None:
        evidence.update(snapshot)
    verify_health(health, expected_sha)
    return snapshot


async def turn(client, base, token, text, *, active=None, intent="MODIFY_ARTIFACT"):
    payload = {"text": text, "forced_intent": intent, "client_message_id": str(uuid.uuid4()),
               "state_summary": {}, "active_artifact": active}
    chunks = []
    headers = {"Accept": "text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with client.stream("POST", base + "/api/v1/lyo2/chat/stream", json=payload,
                             headers=headers) as response:
        response.raise_for_status()
        async for chunk in response.aiter_text():
            chunks.append(chunk)
    return decode_sse("".join(chunks))


async def verify_history(client, base, token, events, answer):
    conversation = next(e["conversation_id"] for e in events if e["type"] == "conversation")
    history = await get_json(client, base, f"/api/v1/chat/conversations/{conversation}", token)
    # Every turn in this runner starts a fresh conversation. The public history
    # schema exposes the saved row ID, not its internal client-message key.
    matches = [m for m in history["messages"] if m.get("role") == "assistant"]
    if len(matches) != 1 or matches[0]["content"] != answer["block"]["content"]["text"]:
        raise AssertionError("Completed assistant answer was not durably persisted exactly once")
    if matches[0].get("generation_status") != "completed":
        raise AssertionError("Saved assistant answer is incomplete")


def reference(artifact):
    return {"artifact_id": artifact["artifact_id"], "artifact_type": artifact["type"],
            "artifact_version": artifact["version"]}


async def exercise(client, base, expected_sha, report):
    # Do not import cloud SDKs, authenticate learners, or seed fixtures until
    # the public revision and storage preflight has passed.
    if os.getenv("LYO_ARTIFACT_STAGING_READY") != "yes" or os.getenv("ENVIRONMENT") != "staging":
        raise ValueError("Explicit staging-ready opt-in and ENVIRONMENT=staging are required")
    tokens = [os.environ[f"LYO_ARTIFACT_STAGING_TOKEN_{suffix}"] for suffix in ("A", "B")]
    project = os.environ["LYO_ARTIFACT_STAGING_FIREBASE_PROJECT"]
    if not re.search(r"(?:^|-)(staging|test|sandbox)(?:-|$)", project):
        raise ValueError("Use a dedicated Firebase project named for staging, test, or sandbox")
    identities = [await get_json(client, base, "/api/v1/auth/me", token) for token in tokens]
    user_a, user_b = (str(identity["id"]) for identity in identities)
    if user_a == user_b or "0" in {user_a, user_b}:
        raise ValueError("Two distinct authenticated staging learners are required")

    from lyo_app.ai.schemas.lyo2 import ArtifactType, FlashcardDeck
    from lyo_app.services.artifact_service import ArtifactService

    storage = ArtifactService()
    storage._require_storage()
    if storage.fb.db.project != project:
        raise ValueError("Local artifact storage is not the approved isolated Firebase project")
    marker = "Artifact QA " + uuid.uuid4().hex
    content = {"title": marker, "cards": [{"front": "What captures light?", "back": "Chlorophyll"}]}
    fixture_ids = set()
    fixtures = []
    try:
        for owner in (user_a, user_b, ""):
            artifact = await storage.create_artifact(owner, ArtifactType.FLASHCARDS, content)
            fixture_ids.add(artifact["artifact_id"])
            fixtures.append(artifact)
        owned, foreign, unowned = fixtures
        baseline = {a["artifact_id"]: await storage.get_artifact(a["artifact_id"]) for a in fixtures}
        missing = {"artifact_id": str(uuid.uuid4()), "artifact_type": "FLASHCARDS", "artifact_version": 1}
        for name, active in (("stale", missing), ("foreign", reference(foreign)),
                             ("unowned", reference(unowned)), ("no_selection", None)):
            events = await turn(client, base, tokens[0], "Add a flashcard to the selected saved deck.", active=active)
            answer = completed_answer(events, expect_artifact=False)
            text = answer["block"]["content"]["text"]
            if "reopen" not in text.lower():
                raise AssertionError("Unavailable target did not offer reopen recovery")
            if active and "so I haven't changed it" not in text:
                raise AssertionError("The unavailable mutation recovery path was not exercised")
            visible = json.dumps(events)
            if marker in visible:
                raise AssertionError("Unavailable saved content leaked in SSE")
            if re.search(r"I've updated|I have updated|successfully (saved|updated)|your deck is ready", visible, re.I):
                raise AssertionError("Rejected update emitted a success confirmation")
            for artifact_id, before in baseline.items():
                if await storage.get_artifact(artifact_id) != before:
                    raise AssertionError("A rejected update changed a saved artifact")
            if await storage.get_artifact(missing["artifact_id"]) is not None:
                raise AssertionError("A stale target was unexpectedly created")
            await verify_history(client, base, tokens[0], events, answer)
            report["checks"].append({"name": name, "passed": True})

        anonymous = await client.post(base + "/api/v1/lyo2/chat/stream", json={
            "text": "Add a card to this saved deck.", "forced_intent": "MODIFY_ARTIFACT",
            "active_artifact": reference(owned), "state_summary": {},
        })
        if anonymous.status_code not in {401, 403}:
            anonymous.raise_for_status()
            anonymous_events = decode_sse(anonymous.text)
            anonymous_answer = completed_answer(anonymous_events, expect_artifact=False)
            if "reopen" not in anonymous_answer["block"]["content"]["text"].lower() or marker in anonymous.text:
                raise AssertionError("Unauthenticated mutation did not fail closed")
        if await storage.get_artifact(owned["artifact_id"]) != owned:
            raise AssertionError("Unauthenticated mutation changed saved content")
        report["checks"].append({"name": "unauthenticated_update", "passed": True})

        events = await turn(client, base, tokens[0], "Add one card about oxygen to this deck; keep its title.",
                            active=reference(owned))
        answer = completed_answer(events, expect_artifact=True)
        block = next(e["block"] for e in events if e["type"] == "artifact")
        updated = await storage.get_artifact(owned["artifact_id"])
        if (not updated or updated["user_id"] != user_a or updated["version"] != 2
                or block["version_id"] != owned["artifact_id"] + "_v2"):
            raise AssertionError("Owned update did not persist the expected owner and version")
        deck = FlashcardDeck.model_validate(updated["content"])
        if len(deck.cards) != 2 or await storage.get_artifact(owned["artifact_id"], version=1) != owned:
            raise AssertionError("Owned update lost its original version or requested card")
        if FlashcardDeck.model_validate(block["content"]).model_dump() != deck.model_dump():
            raise AssertionError("Streamed update differs from the durable deck")
        await verify_history(client, base, tokens[0], events, answer)
        report["checks"].append({"name": "owned_update_and_reload", "passed": True})

        events = await turn(client, base, tokens[0],
                            f"Create three photosynthesis flashcards titled '{marker}'.", intent="FLASHCARDS")
        answer = completed_answer(events, expect_artifact=True)
        block = next(e["block"] for e in events if e["type"] == "artifact")
        artifact_id, version = block["version_id"].rsplit("_v", 1)
        created = await storage.get_artifact(artifact_id)
        if (not created or version != "1" or created["user_id"] != user_a
                or marker not in created["content"].get("title", "") or artifact_id in fixture_ids):
            raise AssertionError("New deck was not durably saved as a distinct owned fixture")
        fixture_ids.add(artifact_id)
        if len(FlashcardDeck.model_validate(created["content"]).cards) != 3:
            raise AssertionError("New deck omitted requested cards")
        if FlashcardDeck.model_validate(block["content"]).model_dump() != FlashcardDeck.model_validate(created["content"]).model_dump():
            raise AssertionError("Streamed new deck differs from the durable deck")
        await verify_history(client, base, tokens[0], events, answer)
        report["checks"].append({"name": "create_and_reload", "passed": True})
    finally:
        # Only records created by this run are eligible for cleanup. Never
        # remove account history or perform collection-wide deletions.
        for artifact_id in fixture_ids:
            def remove_fixture():
                for doc in storage.fb.db.collection(storage.COLLECTION).where("artifact_id", "==", artifact_id).stream():
                    doc.reference.delete()
            await asyncio.to_thread(remove_fixture)
        report["after"] = {}
        await verify_candidate(client, base, expected_sha, report["after"])


async def run(args):
    report = {"expected_sha": args.expected_sha, "status": "blocked", "checks": [],
              "scope": "Real artifact storage, authenticated HTTP/SSE and assistant history; no fault injection or device certification"}
    try:
        base = require_target(args.url, args.expected_sha)
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=False) as client:
            report["before"] = {}
            await verify_candidate(client, base, args.expected_sha, report["before"])
            if args.preflight_only:
                report["status"] = "preflight_passed"
            else:
                await exercise(client, base, args.expected_sha, report)
                report["status"] = "passed"
    except Exception as exc:
        # Exception messages from HTTP/cloud SDKs may contain tokens or URLs.
        report["error_type"] = type(exc).__name__
        if type(exc) in {ValueError, AssertionError, KeyError}:
            report["reason"] = str(exc)[:300]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] in {"passed", "preflight_passed"} else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("artifacts/artifact-recovery-staging.json"))
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
