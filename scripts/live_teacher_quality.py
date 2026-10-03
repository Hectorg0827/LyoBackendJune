#!/usr/bin/env python3
"""Black-box teacher-quality validation against a deployed Lyo backend.

This runner deliberately uses only public client contracts:
- authenticated Lyo 2.0 Chat SSE
- server-graded Chat checks
- authenticated Classroom WebSocket
- authenticated Learning OS analytics

It never imports application code and never mutates production time. A 7-day
retention observation is therefore a second real run, not a simulated clock
jump.

Examples:
    export LYO_ACCESS_TOKEN="..."
    python scripts/live_teacher_quality.py seed
    python scripts/live_teacher_quality.py review --review-concept-id compare_fractions

Reports contain no bearer token. They are written under artifacts/teacher-quality/
unless --output is supplied.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlencode, urlparse, urlunparse

import httpx
import websockets


DEFAULT_BASE_URL = "https://api.lyoai.app"
REPORT_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_https(base_url: str, allow_http: bool = False) -> str:
    value = base_url.rstrip("/")
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("LYO_BASE_URL must be an absolute URL")
    if parsed.scheme != "https" and not allow_http:
        raise ValueError("Refusing non-HTTPS target; pass --allow-http only for local development")
    return value


def websocket_url(base_url: str, path: str, params: dict[str, Any]) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return urlunparse((scheme, parsed.netloc, path, "", query, ""))


def parse_sse_lines(lines: Iterable[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            events.append({"type": "invalid_json", "raw": payload[:500]})
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def first_dict(value: Any, predicate) -> Optional[dict[str, Any]]:
    return next((item for item in walk_dicts(value) if predicate(item)), None)


def all_dicts(value: Any, predicate) -> list[dict[str, Any]]:
    return [item for item in walk_dicts(value) if predicate(item)]


def block_type(value: dict[str, Any]) -> str:
    return str(value.get("type") or value.get("block_type") or "")


def scene_from_message(message: dict[str, Any]) -> Optional[dict[str, Any]]:
    direct = message.get("scene")
    if isinstance(direct, dict):
        return direct
    data = message.get("data")
    if isinstance(data, dict) and isinstance(data.get("scene"), dict):
        return data["scene"]
    return first_dict(message, lambda d: "scene_id" in d and isinstance(d.get("components"), list))


def visible_teacher_text(scene: dict[str, Any]) -> str:
    parts = []
    for component in scene.get("components", []):
        if not isinstance(component, dict):
            continue
        if component.get("type") in {"TeacherMessage", "ExampleBlock", "LessonBlock"}:
            for key in ("text", "content", "title", "caption"):
                value = component.get(key)
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
    return "\n".join(parts)


def component(scene: dict[str, Any], *types: str) -> Optional[dict[str, Any]]:
    wanted = set(types)
    return next(
        (
            item
            for item in scene.get("components", [])
            if isinstance(item, dict) and item.get("type") in wanted
        ),
        None,
    )


def cta(scene: dict[str, Any], intent: Optional[str] = None) -> Optional[dict[str, Any]]:
    for item in scene.get("components", []):
        if not isinstance(item, dict) or item.get("type") != "CTAButton":
            continue
        if intent is None or item.get("action_intent") == intent:
            return item
    return None


def choose_option(quiz: dict[str, Any], want_correct: bool) -> tuple[Optional[str], str]:
    """Force a scenario only when the client contract explicitly permits it.

    Guided Classroom cards sometimes expose correctness to support immediate
    local feedback. Closing checkpoints intentionally withhold it. We never
    infer a hidden key: when no declared option exists, return the first option
    and label the selection as unknown so the report cannot pretend the forced
    scenario happened.
    """
    options = [o for o in quiz.get("options", []) if isinstance(o, dict)]
    for option in options:
        if option.get("is_correct") is want_correct:
            return str(option.get("id")), "declared"
    if options and options[0].get("id") is not None:
        return str(options[0]["id"]), "unknown"
    return None, "missing"


def safe_snapshot(value: Any) -> Any:
    """Bound reports and remove obvious secret-bearing fields."""
    secret_keys = {
        "authorization", "token", "access_token", "refresh_token", "api_key",
        "password", "secret", "jwt",
    }
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            if str(key).lower() in secret_keys:
                out[key] = "[REDACTED]"
            else:
                out[key] = safe_snapshot(child)
        return out
    if isinstance(value, list):
        return [safe_snapshot(v) for v in value[:50]]
    if isinstance(value, str):
        return value[:4000]
    return value


@dataclass
class Check:
    name: str
    passed: Optional[bool]
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class Report:
    run_id: str
    phase: str
    base_url: str
    session_id: str
    topic: str
    started_at: str = field(default_factory=utc_now)
    finished_at: Optional[str] = None
    checks: list[Check] = field(default_factory=list)
    chat: dict[str, Any] = field(default_factory=dict)
    classroom: dict[str, Any] = field(default_factory=dict)
    analytics_before: Optional[dict[str, Any]] = None
    analytics_after: Optional[dict[str, Any]] = None
    notes: list[str] = field(default_factory=list)

    def check(self, name: str, passed: Optional[bool], detail: str = "") -> None:
        self.checks.append(Check(name, passed, detail))

    def to_dict(self) -> dict[str, Any]:
        return safe_snapshot(
            {
                "report_version": REPORT_VERSION,
                "run_id": self.run_id,
                "phase": self.phase,
                "base_url": self.base_url,
                "session_id": self.session_id,
                "topic": self.topic,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "checks": [c.as_dict() for c in self.checks],
                "chat": self.chat,
                "classroom": self.classroom,
                "analytics_before": self.analytics_before,
                "analytics_after": self.analytics_after,
                "notes": self.notes,
            }
        )


class LiveLyo:
    def __init__(self, base_url: str, token: str, timeout: float):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.headers = {"Authorization": f"Bearer {token}"}

    async def analytics(self, client: httpx.AsyncClient) -> Optional[dict[str, Any]]:
        response = await client.get(
            f"{self.base_url}/api/v1/learning-os/analytics/me",
            params={"days": 30},
            headers=self.headers,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        value = response.json()
        return value if isinstance(value, dict) else {"value": value}

    async def chat_seed(
        self,
        client: httpx.AsyncClient,
        report: Report,
        prompt: str,
    ) -> Optional[str]:
        payload = {
            "text": prompt,
            "session_id": report.session_id,
            "device_id": f"teacher-quality-{report.run_id[:8]}",
            "client_message_id": str(uuid.uuid4()),
            "state_summary": {},
        }
        started = time.perf_counter()
        async with client.stream(
            "POST",
            f"{self.base_url}/api/v1/lyo2/chat/stream",
            json=payload,
            headers={**self.headers, "Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            lines = [line async for line in response.aiter_lines()]
        elapsed = round(time.perf_counter() - started, 3)
        events = parse_sse_lines(lines)

        conversation = first_dict(events, lambda d: d.get("type") == "conversation")
        policy = first_dict(events, lambda d: d.get("type") == "teaching_policy")
        quiz = first_dict(
            events,
            lambda d: block_type(d) in {"QuizBlock", "quiz"} and isinstance(d.get("options") or d.get("content"), (list, dict)),
        )

        report.chat["stream_latency_seconds"] = elapsed
        report.chat["event_types"] = [str(e.get("type") or "unknown") for e in events]
        report.chat["teaching_policy"] = policy
        report.chat["conversation_id"] = conversation.get("conversation_id") if conversation else None
        report.chat["quiz_seen"] = bool(quiz)
        report.check("chat_stream_completed", bool(events), f"{len(events)} SSE events")
        report.check("chat_policy_emitted", policy is not None)
        report.check("chat_conversation_persisted", bool(report.chat["conversation_id"]))

        return report.chat["conversation_id"]

    async def classroom(
        self,
        report: Report,
        *,
        mode: str,
        review_concept_id: Optional[str],
        max_scenes: int,
        question: str,
        transfer_answer: str,
    ) -> None:
        params = {
            "session_id": report.session_id,
            "token": self.token,
            "topic": report.topic,
            "objective": f"Apply {report.topic} accurately in a new situation",
            "record_scope": "unit",
            "difficulty": "intermediate",
            "mode": mode,
            "duration_minutes": 10,
            "client_contract_version": 1,
            "review_concept_id": review_concept_id,
        }
        url = websocket_url(
            self.base_url,
            "/api/v1/classroom/ws/connect",
            params,
        )

        scenes: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        asked = False
        hint_requested = False
        forced_wrong = False
        corrected = False
        transfer_submitted = False
        reconnected = False
        resume_anchor: Optional[str] = None
        reconnect_anchor: Optional[str] = None
        post_question_seen = False
        remediation_seen = False

        async def send(ws, intent: str, comp: Optional[dict[str, Any]] = None, answer_data=None):
            payload = {
                "action_intent": intent,
                "session_id": report.session_id,
                "component_id": (comp or {}).get("component_id"),
                "answer_data": answer_data,
                "response_time_ms": 1200,
            }
            actions.append({"intent": intent, "component_id": payload["component_id"]})
            await ws.send(json.dumps(payload))

        async def receive_scene(ws) -> Optional[dict[str, Any]]:
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.monotonic()))
                message = json.loads(raw)
                if message.get("event_type") == "error":
                    report.notes.append(f"classroom error: {safe_snapshot(message)}")
                    continue
                scene = scene_from_message(message)
                if scene is not None:
                    scenes.append(safe_snapshot(scene))
                    return scene
            return None

        ssl_context = ssl.create_default_context() if url.startswith("wss://") else None

        async def connect():
            return websockets.connect(
                url,
                open_timeout=self.timeout,
                close_timeout=5,
                ssl=ssl_context,
                max_size=4 * 1024 * 1024,
            )

        ws_cm = await connect()
        async with ws_cm as ws:
            for _ in range(max_scenes):
                scene = await receive_scene(ws)
                if scene is None:
                    break

                metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
                action_name = str(metadata.get("teaching_action") or "")
                if action_name in {"REMEDIATE", "remediate", "reteach", "prerequisite"}:
                    remediation_seen = True

                text = visible_teacher_text(scene)
                if asked and question.lower().split()[0] in text.lower():
                    post_question_seen = True

                example = component(scene, "ExampleBlock", "LessonBlock")
                quiz = component(scene, "QuizCard")
                input_field = component(scene, "InputField")

                if not asked and example is not None:
                    resume_anchor = str(example.get("component_id") or scene.get("scene_id") or "")
                    await send(
                        ws,
                        "ask_question",
                        example,
                        {"message": question},
                    )
                    asked = True
                    continue

                if quiz is not None and not hint_requested:
                    await send(ws, "request_hint", quiz)
                    hint_requested = True
                    continue

                if quiz is not None and not forced_wrong:
                    option_id, certainty = choose_option(quiz, want_correct=False)
                    if option_id:
                        await send(
                            ws,
                            "submit_answer",
                            quiz,
                            {"selected_option_id": option_id},
                        )
                        forced_wrong = certainty == "declared"
                        if certainty != "declared":
                            report.notes.append(
                                "First quiz withheld its key; submitted an option but did not claim it was wrong."
                            )
                        continue

                if quiz is not None and forced_wrong and not corrected:
                    option_id, certainty = choose_option(quiz, want_correct=True)
                    if option_id and certainty == "declared":
                        await send(
                            ws,
                            "submit_answer",
                            quiz,
                            {"selected_option_id": option_id},
                        )
                        corrected = True
                        continue

                if input_field is not None and not transfer_submitted:
                    await send(
                        ws,
                        "submit_transfer",
                        input_field,
                        {"response": transfer_answer},
                    )
                    transfer_submitted = True
                    continue

                button = cta(scene, "continue") or cta(scene)
                if button is not None:
                    await send(ws, str(button.get("action_intent") or "continue"), button)
                    continue

                # A scene with no supported action is still useful evidence, but
                # the harness must not invent a client action.
                report.notes.append(
                    f"No supported action in scene {scene.get('scene_id')}; stopping first connection."
                )
                break

                # no-op

        # Explicitly reconnect once with the same learner/session identity.
        if scenes:
            reconnect_anchor = str(scenes[-1].get("scene_id") or "")
            ws_cm2 = await connect()
            async with ws_cm2 as ws2:
                scene = await receive_scene(ws2)
                reconnected = scene is not None
                if scene is not None:
                    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
                    if str(metadata.get("teaching_action") or "") in {"REMEDIATE", "remediate", "reteach", "prerequisite"}:
                        remediation_seen = True

        report.classroom = {
            "scene_count": len(scenes),
            "actions": actions,
            "teaching_actions": [
                (s.get("metadata") or {}).get("teaching_action")
                for s in scenes
                if isinstance(s.get("metadata"), dict)
            ],
            "asked_free_form_question": asked,
            "answer_scene_observed": post_question_seen,
            "resume_anchor": resume_anchor,
            "hint_requested": hint_requested,
            "forced_wrong_answer": forced_wrong,
            "remediation_observed": remediation_seen,
            "corrected_after_remediation": corrected,
            "transfer_submitted": transfer_submitted,
            "reconnected": reconnected,
            "reconnect_anchor": reconnect_anchor,
            "last_scene": scenes[-1] if scenes else None,
        }
        report.check("classroom_scene_received", bool(scenes), f"{len(scenes)} scenes")
        report.check("free_form_question_sent", asked)
        report.check(
            "free_form_question_answered",
            post_question_seen if asked else None,
            "structural live observation; review transcript for pedagogical quality",
        )
        report.check("hint_path_exercised", hint_requested)
        report.check(
            "wrong_answer_scenario_forced",
            forced_wrong if hint_requested else None,
            "only true when the live card declared a wrong option to the client",
        )
        report.check(
            "remediation_observed",
            remediation_seen if forced_wrong else None,
            "only evaluated after a confirmed wrong answer",
        )
        report.check("transfer_submitted", transfer_submitted)
        report.check("same_session_reconnected", reconnected)

    async def due_reviews(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        response = await client.get(
            f"{self.base_url}/api/v1/lyo2/chat/reviews/due",
            headers=self.headers,
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("items", []) if isinstance(body, dict) else []
        return items if isinstance(items, list) else []


async def run(args) -> int:
    token = os.getenv("LYO_ACCESS_TOKEN", "").strip()
    if not token:
        print("LYO_ACCESS_TOKEN is required for authenticated production validation.", file=sys.stderr)
        return 2

    try:
        base_url = require_https(
            os.getenv("LYO_BASE_URL", args.base_url),
            allow_http=args.allow_http,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    session_id = args.session_id or f"teacher-quality-{uuid.uuid4()}"
    report = Report(
        run_id=str(uuid.uuid4()),
        phase=args.phase,
        base_url=base_url,
        session_id=session_id,
        topic=args.topic,
    )
    lyo = LiveLyo(base_url, token, args.timeout)

    async with httpx.AsyncClient(timeout=args.timeout, follow_redirects=True) as client:
        try:
            report.analytics_before = await lyo.analytics(client)
        except Exception as exc:
            report.notes.append(f"analytics_before unavailable: {type(exc).__name__}: {exc}")

        if args.phase == "seed":
            try:
                await lyo.chat_seed(client, report, args.chat_prompt)
            except Exception as exc:
                report.check("chat_stream_completed", False, f"{type(exc).__name__}: {exc}")

            try:
                await lyo.classroom(
                    report,
                    mode="solo",
                    review_concept_id=None,
                    max_scenes=args.max_scenes,
                    question=args.question,
                    transfer_answer=args.transfer_answer,
                )
            except Exception as exc:
                report.check("classroom_scene_received", False, f"{type(exc).__name__}: {exc}")

            try:
                due = await lyo.due_reviews(client)
                report.chat["due_reviews_after_seed"] = due
            except Exception as exc:
                report.notes.append(f"due review read unavailable: {type(exc).__name__}: {exc}")

        else:
            review_concept_id = args.review_concept_id
            if not review_concept_id:
                due = await lyo.due_reviews(client)
                if due:
                    review_concept_id = str(due[0].get("skill_id") or "")
                    report.chat["selected_due_review"] = due[0]
            if not review_concept_id:
                report.check(
                    "due_review_available",
                    False,
                    "No due review exists yet. Retention must be measured on a genuinely later run.",
                )
            else:
                report.check("due_review_available", True, review_concept_id)
                try:
                    await lyo.classroom(
                        report,
                        mode="review",
                        review_concept_id=review_concept_id,
                        max_scenes=args.max_scenes,
                        question=args.question,
                        transfer_answer=args.transfer_answer,
                    )
                except Exception as exc:
                    report.check("classroom_scene_received", False, f"{type(exc).__name__}: {exc}")

        try:
            report.analytics_after = await lyo.analytics(client)
        except Exception as exc:
            report.notes.append(f"analytics_after unavailable: {type(exc).__name__}: {exc}")

    report.finished_at = utc_now()
    output = Path(args.output) if args.output else (
        Path("artifacts/teacher-quality")
        / f"{report.started_at[:10]}-{args.phase}-{report.run_id[:8]}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    passed = sum(c.passed is True for c in report.checks)
    failed = [c for c in report.checks if c.passed is False]
    pending = sum(c.passed is None for c in report.checks)
    print(f"report: {output}")
    print(f"checks: {passed} passed, {len(failed)} failed, {pending} not-applicable/pending")
    for check in failed:
        print(f"  FAIL {check.name}: {check.detail}")
    return 1 if failed else 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("seed", "review"))
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--allow-http", action="store_true")
    p.add_argument("--session-id")
    p.add_argument("--topic", default="comparing fractions")
    p.add_argument(
        "--chat-prompt",
        default=(
            "Teach me how to compare fractions such as 1/2 and 1/3. "
            "Do not just give me the answer; teach me and check whether I can apply it."
        ),
    )
    p.add_argument(
        "--question",
        default="Wait — why does a larger denominator make each equal piece smaller?",
    )
    p.add_argument(
        "--transfer-answer",
        default=(
            "If two equal ribbons are cut into 4 pieces and 8 pieces, a fourth is longer "
            "because the same whole is divided into fewer equal pieces."
        ),
    )
    p.add_argument("--review-concept-id")
    p.add_argument("--max-scenes", type=int, default=18)
    p.add_argument("--timeout", type=float, default=75.0)
    p.add_argument("--output")
    return p


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parser().parse_args())))
