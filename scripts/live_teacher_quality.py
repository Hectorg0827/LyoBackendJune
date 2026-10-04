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
REPORT_VERSION = 2


@dataclass(frozen=True)
class ScenarioPreset:
    topic: str
    objective: str
    chat_prompt: str
    question: str
    explanation_answer: str
    transfer_answer: str


@dataclass(frozen=True)
class LearnerProfile:
    ask_question: bool = False
    request_hint: bool = False
    wrong_attempts: int = 0
    attempt_correct: bool = True
    reconnect: bool = False
    partial_free_response: bool = False


SCENARIOS: dict[str, ScenarioPreset] = {
    "math_fractions": ScenarioPreset(
        topic="comparing fractions",
        objective="Compare fractions by reasoning about equal parts of the same whole",
        chat_prompt=(
            "Teach me how to compare fractions such as 1/2 and 1/3. "
            "Do not just give me the answer; teach me and check whether I can apply it."
        ),
        question="Wait — why does a larger denominator make each equal piece smaller?",
        explanation_answer=(
            "For the same whole, making more equal pieces makes each piece smaller, "
            "so the denominator changes the size of each part."
        ),
        transfer_answer=(
            "If two equal ribbons are cut into 4 pieces and 8 pieces, a fourth is longer "
            "because the same whole is divided into fewer equal pieces."
        ),
    ),
    "biology_photosynthesis": ScenarioPreset(
        topic="photosynthesis",
        objective="Explain photosynthesis inputs and outputs and predict the effect of reduced light",
        chat_prompt=(
            "Teach me the inputs and outputs of photosynthesis, then check whether I can "
            "apply the idea to a plant receiving less light."
        ),
        question="Why is light an input to the process if it is not matter like water or carbon dioxide?",
        explanation_answer=(
            "Light supplies the energy that drives the reactions converting carbon dioxide "
            "and water into stored chemical energy in glucose."
        ),
        transfer_answer=(
            "With less light, the plant generally makes glucose more slowly because less "
            "energy is available to drive photosynthesis, assuming other inputs stay similar."
        ),
    ),
    "physics_newton2": ScenarioPreset(
        topic="Newton's second law",
        objective="Apply F = ma when force or mass changes",
        chat_prompt=(
            "Teach me Newton's second law conceptually, not just the formula, and then "
            "check whether I can predict acceleration when force or mass changes."
        ),
        question="Why does the same force produce less acceleration when the object's mass is larger?",
        explanation_answer=(
            "Acceleration depends on force per unit mass, so the same force is spread across "
            "more inertia when mass is larger."
        ),
        transfer_answer=(
            "If force doubles while mass stays the same, acceleration doubles. If mass doubles "
            "with the same force, acceleration is cut in half."
        ),
    ),
    "spanish_past_tense": ScenarioPreset(
        topic="Spanish preterite versus imperfect",
        objective="Choose preterite or imperfect from narrative context",
        chat_prompt=(
            "Teach me when to use the Spanish preterite versus imperfect with a short story, "
            "then check whether I can choose the tense in a new context."
        ),
        question="Why would an ongoing background action use the imperfect while an interrupting event uses the preterite?",
        explanation_answer=(
            "The imperfect frames an ongoing or habitual background state, while the preterite "
            "presents a bounded event that occurred and moved the story forward."
        ),
        transfer_answer=(
            "In 'Yo caminaba cuando empezó a llover,' caminaba is imperfect because the walking "
            "was ongoing background action, while empezó is preterite because the rain began as a bounded event."
        ),
    ),
    "business_contribution_margin": ScenarioPreset(
        topic="contribution margin",
        objective="Apply contribution-margin reasoning when price or variable cost changes",
        chat_prompt=(
            "Teach me contribution margin using a simple product example, then check whether "
            "I can reason through a price or variable-cost change."
        ),
        question="Why is contribution margin more useful than revenue alone for judging what each sale contributes?",
        explanation_answer=(
            "Revenue ignores the variable cost required to make the sale. Contribution margin "
            "subtracts that cost and shows what remains to cover fixed costs and profit."
        ),
        transfer_answer=(
            "If price is $20 and variable cost rises from $12 to $14, contribution margin falls "
            "from $8 to $6 per unit, so each sale contributes $2 less before fixed costs."
        ),
    ),
}


LEARNER_PROFILES: dict[str, LearnerProfile] = {
    "advanced": LearnerProfile(reconnect=True),
    "beginner": LearnerProfile(request_hint=True, wrong_attempts=1, reconnect=True),
    "confident_wrong": LearnerProfile(wrong_attempts=1, reconnect=True),
    "quiet_partial": LearnerProfile(request_hint=True, partial_free_response=True, reconnect=True),
    "curious": LearnerProfile(ask_question=True, reconnect=True),
    "struggling": LearnerProfile(
        request_hint=True,
        wrong_attempts=3,
        attempt_correct=False,
        reconnect=True,
        partial_free_response=True,
    ),
    "fast_learner": LearnerProfile(),
    "interrupter": LearnerProfile(
        ask_question=True,
        request_hint=True,
        wrong_attempts=1,
        reconnect=True,
    ),
}


QUALITY_RUBRIC: tuple[tuple[str, str], ...] = (
    ("answers_learner_words", "Directly addresses the learner's actual words or misconception."),
    ("examples_progress", "Uses concrete examples that become progressively more demanding."),
    ("detour_then_resume", "Answers a free-form detour before resuming the original lesson coherently."),
    ("misconception_specific_repair", "Targets the misconception instead of repeating the same explanation."),
    ("hint_preserves_struggle", "Hints reduce difficulty without revealing the answer."),
    ("transfer_is_novel", "Transfer requires the same principle in a genuinely new context."),
    ("avoids_monologue_repetition", "Avoids unnecessary monologues, repeated questions, and empty praise."),
    ("visual_adds_information", "Any visual remediation adds instructional information rather than decoration."),
)


def quality_rubric_template() -> list[dict[str, Any]]:
    return [
        {
            "criterion": criterion,
            "description": description,
            "score": None,
            "notes": "",
            "scale": "1-5",
        }
        for criterion, description in QUALITY_RUBRIC
    ]


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


def select_due_review(
    items: Iterable[dict[str, Any]],
    requested_id: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Select only a review the server says is currently due.

    An explicit ID is a filter, never an override. This prevents a stale,
    mistyped, or early concept from being labeled as retention evidence when
    the Classroom correctly declines review mode for it.
    """
    due = [item for item in items if isinstance(item, dict)]
    requested = (requested_id or "").strip()
    if requested:
        match = next(
            (
                item
                for item in due
                if str(item.get("skill_id") or "").strip() == requested
            ),
            None,
        )
        return match, "requested_due" if match is not None else "requested_not_due"
    if due:
        return due[0], "first_due"
    return None, "none_due"


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
    scenario: str
    learner_profile: str
    topic: str
    started_at: str = field(default_factory=utc_now)
    finished_at: Optional[str] = None
    checks: list[Check] = field(default_factory=list)
    chat: dict[str, Any] = field(default_factory=dict)
    classroom: dict[str, Any] = field(default_factory=dict)
    analytics_before: Optional[dict[str, Any]] = None
    analytics_after: Optional[dict[str, Any]] = None
    analytics_delta: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    quality_rubric: list[dict[str, Any]] = field(default_factory=quality_rubric_template)

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
                "scenario": self.scenario,
                "learner_profile": self.learner_profile,
                "topic": self.topic,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "checks": [c.as_dict() for c in self.checks],
                "chat": self.chat,
                "classroom": self.classroom,
                "analytics_before": self.analytics_before,
                "analytics_after": self.analytics_after,
                "analytics_delta": self.analytics_delta,
                "notes": self.notes,
                "quality_rubric": self.quality_rubric,
            }
        )


def analytics_delta(
    before: Optional[dict[str, Any]],
    after: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Small, explicit delta over counters relevant to one live run."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return {}

    def number(root: dict[str, Any], *path: str) -> float:
        value: Any = root
        for key in path:
            if not isinstance(value, dict):
                return 0.0
            value = value.get(key)
        return float(value) if isinstance(value, (int, float)) else 0.0

    metrics = {
        "evidence_attempts": ("evidence_attempts",),
        "identified_sessions": ("sessions", "identified_sessions"),
        "successful_sessions": ("sessions", "successful_sessions"),
        "model_calls": ("model_usage", "calls"),
        "model_tokens": ("model_usage", "tokens"),
        "linked_model_calls": ("model_usage", "linked_calls"),
        "linked_model_tokens": ("model_usage", "linked_tokens"),
        "transfer_attempts": ("transfer", "attempts"),
        "transfer_successes": ("transfer", "successes"),
        "remediation_followups": ("remediation", "eligible_followups"),
        "remediation_repairs": ("remediation", "repaired"),
    }
    return {
        label: number(after, *path) - number(before, *path)
        for label, path in metrics.items()
    }


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
        lines: list[str] = []
        stream_transport_error: Optional[str] = None
        async with client.stream(
            "POST",
            f"{self.base_url}/api/v1/lyo2/chat/stream",
            json=payload,
            headers={**self.headers, "Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            try:
                async for line in response.aiter_lines():
                    lines.append(line)
            except httpx.RemoteProtocolError as exc:
                # Production proxies can terminate a chunked SSE response after
                # the final useful event without a clean HTTP body terminator.
                # Preserve the events already delivered so the report can judge
                # Chat -> policy -> persistence instead of throwing that evidence away.
                stream_transport_error = f"{type(exc).__name__}: {exc}"
        elapsed = round(time.perf_counter() - started, 3)
        events = parse_sse_lines(lines)

        conversation = first_dict(
            events,
            lambda d: bool(d.get("conversation_id")),
        )
        policy = first_dict(events, lambda d: d.get("type") == "teaching_policy")
        quiz = first_dict(
            events,
            lambda d: (
                block_type(d) in {"QuizBlock", "quiz"}
                and isinstance(d.get("content"), dict)
                and isinstance(d.get("content", {}).get("options"), list)
            ),
        )

        conversation_id = str(conversation.get("conversation_id")) if conversation else None
        report.chat["stream_latency_seconds"] = elapsed
        report.chat["stream_transport_error"] = stream_transport_error
        report.chat["event_types"] = [str(e.get("type") or "unknown") for e in events]
        report.chat["teaching_policy"] = policy
        report.chat["conversation_id"] = conversation_id
        report.chat["quiz_seen"] = bool(quiz)
        report.check(
            "chat_stream_completed",
            bool(events) and stream_transport_error is None,
            (
                f"{len(events)} SSE events"
                if stream_transport_error is None
                else f"{len(events)} SSE events recovered before {stream_transport_error}"
            ),
        )
        if stream_transport_error is not None:
            report.check(
                "chat_stream_evidence_recovered",
                bool(events),
                "Partial SSE transport failure did not erase already-delivered teaching evidence.",
            )
        report.check("chat_policy_emitted", policy is not None)
        report.check("chat_conversation_persisted", bool(conversation_id))

        if quiz is None or conversation_id is None:
            report.check(
                "chat_smart_block_graded",
                False,
                "No persisted conversation + quiz Smart Block pair was emitted.",
            )
            return conversation_id

        # The answer key must not be present in the learner-visible stream.
        content = quiz.get("content") if isinstance(quiz.get("content"), dict) else {}
        report.check(
            "chat_answer_key_hidden",
            "correct_index" not in content,
            "Learner-visible Smart Blocks must not expose correct_index.",
        )

        block_id = quiz.get("id") or quiz.get("block_id")
        if not block_id:
            report.check("chat_smart_block_graded", False, "Quiz block has no id.")
            return conversation_id

        grade_started = time.perf_counter()
        grade = await client.post(
            f"{self.base_url}/api/v1/lyo2/chat/check",
            headers=self.headers,
            json={
                "conversation_id": conversation_id,
                "block_id": str(block_id),
                "selected_index": 0,
                "time_taken_ms": 1800,
                "hint_used": False,
            },
        )
        report.chat["check_latency_seconds"] = round(time.perf_counter() - grade_started, 3)
        report.chat["check_status"] = grade.status_code
        if grade.status_code != 200:
            report.check(
                "chat_smart_block_graded",
                False,
                f"status {grade.status_code}: {grade.text[:300]}",
            )
            return conversation_id

        verdict = grade.json()
        report.chat["check_verdict"] = verdict
        report.check(
            "chat_smart_block_graded",
            isinstance(verdict, dict) and isinstance(verdict.get("correct"), bool),
            "Server returned an explicit correctness verdict.",
        )
        return conversation_id

    async def classroom(
        self,
        report: Report,
        *,
        mode: str,
        review_concept_id: Optional[str],
        max_scenes: int,
        question: str,
        explanation_answer: str,
        transfer_answer: str,
        objective: str,
        learner_profile: LearnerProfile,
    ) -> None:
        params = {
            "session_id": report.session_id,
            "token": self.token,
            "topic": report.topic,
            "objective": objective,
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
        resumed_same_example = False
        original_example_text = ""
        remediation_seen = False
        remediation_visual_seen = False
        declared_wrong_available = False
        wrong_attempts = 0
        correct_submitted = False
        unknown_quiz_submitted = False
        free_response_types: list[str] = []

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
                    remediation_visual_seen = remediation_visual_seen or any(
                        isinstance(item, dict)
                        and (
                            item.get("block_type") == "teaching_visual"
                            or (
                                item.get("type") == "LessonBlock"
                                and item.get("block_type") == "teaching_visual"
                            )
                        )
                        for item in scene.get("components", [])
                    )

                text = visible_teacher_text(scene)
                if asked and text:
                    # The first authored teacher scene after ASK_QUESTION is the
                    # live answer to the detour. Pedagogical quality is reviewed
                    # from the transcript; this assertion is only structural.
                    post_question_seen = True
                    if original_example_text and text == original_example_text:
                        resumed_same_example = True

                example = component(scene, "ExampleBlock", "LessonBlock")
                quiz = component(scene, "QuizCard")
                input_field = component(scene, "InputField")

                if learner_profile.ask_question and not asked and example is not None:
                    resume_anchor = str(example.get("component_id") or scene.get("scene_id") or "")
                    original_example_text = text
                    await send(
                        ws,
                        "ask_question",
                        example,
                        {"message": question},
                    )
                    asked = True
                    continue

                if quiz is not None and learner_profile.request_hint and not hint_requested:
                    await send(ws, "request_hint", quiz)
                    hint_requested = True
                    continue

                if quiz is not None and wrong_attempts < learner_profile.wrong_attempts:
                    option_id, certainty = choose_option(quiz, want_correct=False)
                    if option_id and certainty == "declared":
                        declared_wrong_available = True
                        await send(
                            ws,
                            "submit_answer",
                            quiz,
                            {"selected_option_id": option_id},
                        )
                        wrong_attempts += 1
                        forced_wrong = True
                        continue
                    report.notes.append(
                        "Quiz withheld its key; the requested wrong-answer learner behavior "
                        "was not claimed or forced."
                    )

                if quiz is not None and learner_profile.attempt_correct and not correct_submitted:
                    option_id, certainty = choose_option(quiz, want_correct=True)
                    if option_id and certainty == "declared":
                        await send(
                            ws,
                            "submit_answer",
                            quiz,
                            {"selected_option_id": option_id},
                        )
                        correct_submitted = True
                        corrected = wrong_attempts > 0
                        continue
                    if option_id and not unknown_quiz_submitted:
                        await send(
                            ws,
                            "submit_answer",
                            quiz,
                            {"selected_option_id": option_id},
                        )
                        unknown_quiz_submitted = True
                        report.notes.append(
                            "Quiz withheld its key; submitted one learner-visible option but "
                            "did not label it correct or incorrect."
                        )
                        continue

                if input_field is not None:
                    evidence_type = str(input_field.get("evidence_type") or "transfer")
                    free_response_types.append(evidence_type)
                    response_text = (
                        explanation_answer if evidence_type == "explanation" else transfer_answer
                    )
                    if learner_profile.partial_free_response:
                        response_text = " ".join(response_text.split()[:7])
                    await send(
                        ws,
                        str(input_field.get("action_intent") or "submit_transfer"),
                        input_field,
                        {"response": response_text},
                    )
                    if evidence_type == "transfer":
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

        # Explicitly reconnect with the same learner/session identity only for
        # profiles designed to exercise continuity.
        if scenes and learner_profile.reconnect:
            reconnect_anchor = str(scenes[-1].get("scene_id") or "")
            ws_cm2 = await connect()
            async with ws_cm2 as ws2:
                scene = await receive_scene(ws2)
                reconnected = scene is not None
                if scene is not None:
                    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
                    if str(metadata.get("teaching_action") or "") in {"REMEDIATE", "remediate", "reteach", "prerequisite"}:
                        remediation_seen = True
                        remediation_visual_seen = remediation_visual_seen or any(
                            isinstance(item, dict)
                            and item.get("block_type") == "teaching_visual"
                            for item in scene.get("components", [])
                        )

        transcript = [
            {
                "scene_id": s.get("scene_id"),
                "scene_type": s.get("scene_type"),
                "teaching_action": (
                    (s.get("metadata") or {}).get("teaching_action")
                    if isinstance(s.get("metadata"), dict)
                    else None
                ),
                "target_evidence_type": (
                    (s.get("metadata") or {}).get("target_evidence_type")
                    if isinstance(s.get("metadata"), dict)
                    else None
                ),
                "component_types": [
                    item.get("type")
                    for item in s.get("components", [])
                    if isinstance(item, dict)
                ],
                "teacher_text": visible_teacher_text(s),
            }
            for s in scenes
        ]
        report.classroom = {
            "scene_count": len(scenes),
            "actions": actions,
            "transcript": transcript,
            "teaching_actions": [
                (s.get("metadata") or {}).get("teaching_action")
                for s in scenes
                if isinstance(s.get("metadata"), dict)
            ],
            "asked_free_form_question": asked,
            "answer_scene_observed": post_question_seen,
            "same_example_resumed": resumed_same_example,
            "resume_anchor": resume_anchor,
            "hint_requested": hint_requested,
            "forced_wrong_answer": forced_wrong,
            "remediation_observed": remediation_seen,
            "remediation_visual_observed": remediation_visual_seen,
            "corrected_after_remediation": corrected,
            "declared_wrong_available": declared_wrong_available,
            "wrong_attempts_forced": wrong_attempts,
            "correct_answer_submitted": correct_submitted,
            "free_response_evidence_types": free_response_types,
            "transfer_submitted": transfer_submitted,
            "reconnected": reconnected,
            "reconnect_anchor": reconnect_anchor,
            "last_scene": scenes[-1] if scenes else None,
        }
        report.check("classroom_scene_received", bool(scenes), f"{len(scenes)} scenes")
        report.check(
            "free_form_question_sent",
            asked if learner_profile.ask_question else None,
            "profile does not request a detour" if not learner_profile.ask_question else "",
        )
        report.check(
            "free_form_question_answered",
            post_question_seen if asked else None,
            "structural live observation; review transcript for pedagogical quality",
        )
        report.check(
            "interrupted_example_resumed",
            resumed_same_example if asked and original_example_text else None,
            "same teacher text reappeared after the detour; deterministic tests cover state identity",
        )
        report.check(
            "hint_path_exercised",
            hint_requested if learner_profile.request_hint else None,
            "profile does not request a hint" if not learner_profile.request_hint else "",
        )
        report.check(
            "wrong_answer_scenario_forced",
            (
                wrong_attempts >= learner_profile.wrong_attempts
                if learner_profile.wrong_attempts and declared_wrong_available
                else None
            ),
            "only evaluated when the live card declares an incorrect option",
        )
        report.check(
            "remediation_observed",
            remediation_seen if forced_wrong else None,
            "only evaluated after a confirmed wrong answer",
        )
        report.check(
            "transfer_submitted",
            transfer_submitted if "transfer" in free_response_types else None,
            "no live transfer InputField was reached" if "transfer" not in free_response_types else "",
        )
        report.check(
            "same_session_reconnected",
            reconnected if learner_profile.reconnect else None,
            "profile does not request reconnect" if not learner_profile.reconnect else "",
        )

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

    scenario = SCENARIOS[args.scenario]
    learner_profile = LEARNER_PROFILES[args.profile]
    topic = args.topic or scenario.topic
    chat_prompt = args.chat_prompt or scenario.chat_prompt
    question = args.question or scenario.question
    explanation_answer = args.explanation_answer or scenario.explanation_answer
    transfer_answer = args.transfer_answer or scenario.transfer_answer
    objective = args.objective or scenario.objective

    session_id = args.session_id or f"teacher-quality-{uuid.uuid4()}"
    report = Report(
        run_id=str(uuid.uuid4()),
        phase=args.phase,
        base_url=base_url,
        session_id=session_id,
        scenario=args.scenario,
        learner_profile=args.profile,
        topic=topic,
    )
    lyo = LiveLyo(base_url, token, args.timeout)

    async with httpx.AsyncClient(timeout=args.timeout, follow_redirects=True) as client:
        try:
            report.analytics_before = await lyo.analytics(client)
        except Exception as exc:
            report.notes.append(f"analytics_before unavailable: {type(exc).__name__}: {exc}")

        if args.phase == "seed":
            try:
                await lyo.chat_seed(client, report, chat_prompt)
            except Exception as exc:
                report.check("chat_stream_completed", False, f"{type(exc).__name__}: {exc}")

            try:
                await lyo.classroom(
                    report,
                    mode="solo",
                    review_concept_id=None,
                    max_scenes=args.max_scenes,
                    question=question,
                    explanation_answer=explanation_answer,
                    transfer_answer=transfer_answer,
                    objective=objective,
                    learner_profile=learner_profile,
                )
            except Exception as exc:
                report.check("classroom_scene_received", False, f"{type(exc).__name__}: {exc}")

            try:
                due = await lyo.due_reviews(client)
                report.chat["due_reviews_after_seed"] = due
            except Exception as exc:
                report.notes.append(f"due review read unavailable: {type(exc).__name__}: {exc}")

        else:
            due = await lyo.due_reviews(client)
            selected, selection_reason = select_due_review(
                due, args.review_concept_id
            )
            report.chat["due_review_selection"] = selection_reason
            if selected is not None:
                report.chat["selected_due_review"] = selected

            review_concept_id = (
                str(selected.get("skill_id") or "").strip()
                if selected is not None
                else ""
            )
            if not review_concept_id:
                requested = (args.review_concept_id or "").strip()
                detail = (
                    f"Requested concept {requested!r} is not currently due."
                    if requested
                    else (
                        "No due review exists yet. Retention must be measured "
                        "on a genuinely later run."
                    )
                )
                report.check("due_review_available", False, detail)
            else:
                report.check("due_review_available", True, review_concept_id)
                try:
                    await lyo.classroom(
                        report,
                        mode="review",
                        review_concept_id=review_concept_id,
                        max_scenes=args.max_scenes,
                        question=question,
                        explanation_answer=explanation_answer,
                        transfer_answer=transfer_answer,
                        objective=objective,
                        learner_profile=learner_profile,
                    )
                except Exception as exc:
                    report.check("classroom_scene_received", False, f"{type(exc).__name__}: {exc}")

        try:
            report.analytics_after = await lyo.analytics(client)
        except Exception as exc:
            report.notes.append(f"analytics_after unavailable: {type(exc).__name__}: {exc}")

    report.analytics_delta = analytics_delta(report.analytics_before, report.analytics_after)
    if args.phase == "seed" and report.analytics_delta:
        report.check(
            "chat_or_classroom_evidence_reached_record",
            report.analytics_delta.get("evidence_attempts", 0) > 0,
            f"evidence delta={report.analytics_delta.get('evidence_attempts', 0)}",
        )

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
    p.add_argument(
        "--scenario",
        choices=tuple(SCENARIOS),
        default="math_fractions",
        help="Coherent subject fixture; explicit text flags below override its fields.",
    )
    p.add_argument(
        "--profile",
        choices=tuple(LEARNER_PROFILES),
        default="interrupter",
        help="Scripted learner behavior to exercise against the live teacher.",
    )
    p.add_argument("--topic")
    p.add_argument("--objective")
    p.add_argument("--chat-prompt")
    p.add_argument("--question")
    p.add_argument("--explanation-answer")
    p.add_argument("--transfer-answer")
    p.add_argument("--review-concept-id")
    p.add_argument("--max-scenes", type=int, default=32)
    p.add_argument("--timeout", type=float, default=75.0)
    p.add_argument("--output")
    return p


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parser().parse_args())))
