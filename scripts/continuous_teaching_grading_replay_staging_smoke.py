"""Live graded Classroom checkpoint/replay verification on the isolated LYO staging host.

Exercises server-issued grading, stale-submission replay, reconnect and saved
scene identity using a synthetic authenticated learner. Never targets production.
No direct database visibility: this tests the externally observable contract.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid

import httpx
import websockets

from continuous_teaching_live_staging_smoke import (
    BASE, create_synthetic, report, require, socket_url, verify_target,
)

EXPECTED_REVISION = "16b44150da69457e2ab738175aafc10361f349e6"
GRADE_VERDICTS = {"correct", "incorrect", "partial"}
MAX_STEPS = 9
SCENE_TIMEOUT = 150


async def scene_cycle(ws, *, name: str, timeout: float = SCENE_TIMEOUT):
    deadline = time.monotonic() + timeout
    start = None
    expected_scene = None
    feedback = []
    while time.monotonic() < deadline:
        message = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
        try:
            payload = json.loads(message)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        event = payload.get("event_type")
        if event == "error":
            data = payload.get("data") or {}
            raise RuntimeError("classroom_socket_error:" + str(data.get("error", "unknown"))[:70])
        if event == "answer_feedback":
            feedback.append(payload.get("data") or {})
        elif event == "scene_start" and payload.get("scene"):
            start = payload["scene"]
            expected_scene = str(start.get("scene_id") or "")
        elif event == "scene_complete" and start:
            if str((payload.get("data") or {}).get("scene_id")) == expected_scene:
                require(bool(expected_scene), "scene identity missing")
                return start, feedback
    raise RuntimeError("timed out waiting for " + name)


def components(scene):
    return scene.get("components") or []


def task_from(scene):
    for comp in components(scene):
        if comp.get("type") in ("QuizCard", "InputField"):
            return comp
    return None


def continue_from(scene):
    return next(
        (component for component in components(scene)
         if component.get("type") == "CTAButton"
         and component.get("action_intent") == "continue"), None
    )


def action(session: str, intent: str, component_id: str, answer_data=None):
    return {
        "event_type": "user_action",
        "session_id": session,
        "action_intent": intent,
        "component_id": component_id,
        "answer_data": answer_data or {},
        "response_time_ms": 3600,
    }


def submission(session: str, component: dict):
    cid = component.get("component_id")
    require(bool(cid), "checkpoint component ID missing")
    if component.get("type") == "QuizCard":
        options = component.get("options") or []
        require(len(options) >= 2, "QuizCard missing options")
        # Diagnostic answer keys must be concealed from clients.
        # Avoid abstention if one is present; do not invent a correct answer.
        usable = [o for o in options
                  if not any(s in str(o.get("label", "")).lower()
                             for s in ("not sure", "don't know", "no sé", "no se"))]
        selected = (usable or options)[0]
        require(bool(selected.get("id")), "quiz answer option ID missing")
        return action(session, "submit_answer", cid,
                      {"selected_option_id": selected["id"], "is_correct": True})
    require(component.get("type") == "InputField", "invalid response component")
    # A synthetic explanation, not a claim of correctness. The LLM grader must
    # judge it against the ACTUAL question; uncertainty/incorrect is acceptable.
    response = ("For equal-size wholes, one half is larger than one third. "
                "With fewer equal pieces each piece is bigger.")
    return action(session, "submit_transfer", cid,
                  {"response": response, "is_correct": True})


def is_diagnostic(scene):
    metadata = scene.get("metadata") or {}
    return metadata.get("target_evidence_type") == "recognition"


def evidence_target(scene):
    return str((scene.get("metadata") or {}).get("target_evidence_type") or "unknown")


def feedback_for(feedbacks: list, component_id: str):
    return [f for f in feedbacks if f.get("component_id") == component_id]


async def main():
    verify_target()
    async with httpx.AsyncClient(base_url=BASE, timeout=25, follow_redirects=False) as http:
        response = await http.get("/health")
        require(response.status_code == 200, "staging health not 200")
        health = response.json()
        require(health.get("commit_sha") == EXPECTED_REVISION,
                "refusing to test a different deployment revision")
        require(str(health.get("environment", "")).lower() != "production",
                "refusing production environment")
        report("staging_revision", status="passed", sha_confirmed=True)
        token, user_id = await create_synthetic(http, "grade")
        session = "ct-grade-" + uuid.uuid4().hex

        url = socket_url(token, session, topic="Comparing fractions and equal-sized pieces",
                         resume=False)
        async with websockets.connect(url, open_timeout=25, max_size=5_000_000) as ws:
            scene, _ = await scene_cycle(ws, name="initial scene")
            report("initial_teacher_scene", status="passed",
                   component_types=[x.get("type") for x in components(scene)],
                   evidence_type=evidence_target(scene))
            seen_non_diagnostic = False
            for index in range(MAX_STEPS):
                task = task_from(scene)
                if task and not is_diagnostic(scene):
                    seen_non_diagnostic = True
                    break
                if task and is_diagnostic(scene):
                    # The opening probe is a graded server-recognition check,
                    # but never mastery evidence. Advance to real practice.
                    require(all(opt.get("is_correct") is None
                                for opt in task.get("options", [])),
                            "diagnostic answer key leaked to client")
                    await ws.send(json.dumps(submission(session, task)))
                    new_scene, fb = await scene_cycle(ws, name="post-diagnostic scene")
                    matching = feedback_for(fb, task["component_id"])
                    require(len(matching) == 1
                            and matching[0].get("verdict") in GRADE_VERDICTS,
                            "diagnostic missing one server verdict")
                    require(new_scene.get("scene_id") != scene.get("scene_id"),
                            "diagnostic did not advance")
                    report("diagnostic_server_verdict", status="passed",
                           verdict=matching[0]["verdict"], step=index + 1,
                           answer_key_hidden=True)
                    scene = new_scene
                    continue

                button = continue_from(scene)
                require(button is not None, "no actionable graded question or Continue CTA")
                await ws.send(json.dumps(action(session, "continue", button["component_id"])))
                new_scene, _ = await scene_cycle(ws, name="next teaching step")
                require(new_scene.get("scene_id") != scene.get("scene_id"),
                        "Continue did not transition to a new scene")
                scene = new_scene
                report("teaching_transition", status="passed", step=index + 1,
                       evidence_type=evidence_target(scene),
                       component_types=[x.get("type") for x in components(scene)])

            require(seen_non_diagnostic, "failed to reach live practice checkpoint")
            component = task_from(scene)
            require(component is not None, "no graded checkpoint")
            answer = submission(session, component)
            checkpoint_id = component["component_id"]
            previous_id = scene.get("scene_id")
            report("practice_checkpoint_reached", status="passed",
                   answer_type=component["type"], evidence_type=evidence_target(scene))
            await ws.send(json.dumps(answer))
            committed, feedback = await scene_cycle(ws, name="server graded response")
            graded = feedback_for(feedback, checkpoint_id)
            require(len(graded) == 1, "expected exactly one server feedback for accepted answer")
            verdict = str(graded[0].get("verdict") or "")
            require(verdict in GRADE_VERDICTS,
                    "teacher did not supply a definitive graded verdict")
            require(committed.get("scene_id") and committed.get("scene_id") != previous_id,
                    "graded answer did not advance to a new committed scene")
            final_id = str(committed["scene_id"])
            report("practice_answer_server_graded", status="passed", verdict=verdict,
                   feedback_count=len(graded), new_scene=True)

            # Exact stale action must be idempotent in the same live session.
            await ws.send(json.dumps(answer))
            duplicated, replay_feedback = await scene_cycle(ws, name="duplicate replay")
            require(str(duplicated.get("scene_id")) == final_id,
                    "duplicate submission advanced teaching to another scene")
            require(not feedback_for(replay_feedback, checkpoint_id),
                    "duplicate answer emitted additional grading feedback")
            report("duplicate_answer_idempotent", status="passed",
                   same_scene=True, extra_grade_feedback=False)

        # Separate WebSocket connection, same JWT owner and durable session.
        resume_url = socket_url(token, session, topic="Comparing fractions and equal-sized pieces",
                                resume=True)
        async with websockets.connect(resume_url, open_timeout=25, max_size=5_000_000) as ws:
            restored, _ = await scene_cycle(ws, name="saved graded scene on reconnect")
            require(str(restored.get("scene_id")) == final_id,
                    "reconnect did not restore the saved post-grade scene")
            report("post_grade_scene_restored", status="passed", same_scene=True)
            await ws.send(json.dumps(answer))
            still_same, extra = await scene_cycle(ws, name="replayed answer after reconnect")
            require(str(still_same.get("scene_id")) == final_id,
                    "replayed answer after reconnect advanced again")
            require(not feedback_for(extra, checkpoint_id),
                    "replayed answer after reconnect caused a second grade")
            report("post_reconnect_duplicate_idempotent", status="passed",
                   same_scene=True, extra_grade_feedback=False)

        report("result", status="passed", limitations=[
            "database event counts not directly inspected",
            "no forced backend restart in this run",
            "no physical Android audio or microphone verified",
        ])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        # No credentials, user email or raw exception text is ever emitted.
        report("result", status="failed", reason=type(exc).__name__)
        sys.exit(1)
