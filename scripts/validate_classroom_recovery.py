"""Bounded staging probes using the deployed account and real Classroom code.

This is an operator-run validation worker, never a learner endpoint or an
ordinary CI test. Recovery keeps CLASSROOM_STRICT_SCHEMA=0. Contract probes
send strict formats directly without changing the application-wide flag.
Only synthetic learners and a private temporary SQLite database are used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPORT = {"status": "pending", "recovery": [], "contracts": []}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def safe_error(error):
    text = str(error)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "JWT_SECRET_KEY", "SECRET_KEY"):
        value = os.getenv(name)
        if value:
            text = text.replace(value, "[REDACTED]")
    return text[:700]


async def recovery_probe(two_failures=False):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
    from lyo_app.ai_classroom.adaptive_teaching import AdaptiveTeacher, GuidedState, TeachingUnavailable
    from lyo_app.ai_classroom.scene_lifecycle_engine import ContextAssembler, SceneLifecycleEngine
    from lyo_app.ai_classroom.sdui_models import ActionIntent, CTAButton, Scene
    from lyo_app.classroom.models import ClassroomInteraction, ClassroomSession
    from lyo_app.core.ai_resilience import ai_resilience_manager
    from tests.adaptive_fixtures import ScriptedTeacher, action, advance_to_task, context, decline_probe

    teacher = ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context(target_duration_minutes=8)
    await runner.run(ctx, progress, action(welcome=True))
    await decline_probe(runner, progress, ctx)
    await advance_to_task(runner, progress, ctx)
    pending = GuidedState.model_validate(progress["guided_state"]).pending
    require(pending is not None, "Synthetic learner did not reach a real checkpoint")
    teacher.turn.side_effect = TeachingUnavailable("Controlled staging generation failure")
    submission = action(ActionIntent.SUBMIT_ANSWER, pending.id,
                        answer_data={"selected_option_id": "a"})
    failed = await runner.run(ctx, progress, submission)
    state = GuidedState.model_validate(progress["guided_state"])
    require(state.recovery_attempts == 1, "Initial failure was not counted")
    original_move, evidence = state.next_move, list(state.outbox)
    require(len(evidence) == 1, "Accepted answer evidence was not retained")

    def retry(scene):
        button = next(c for c in scene.components if isinstance(c, CTAButton)
                      and c.action_intent == ActionIntent.RETRY)
        return action(ActionIntent.RETRY, button.component_id)

    database = create_async_engine("sqlite+aiosqlite://")
    try:
        async with database.begin() as connection:
            await connection.run_sync(ClassroomSession.__table__.create)
            await connection.run_sync(ClassroomInteraction.__table__.create)
        async with AsyncSession(database) as db:
            persistence = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
            persistence.db = db
            require(await persistence._persist_session_progress(retry(failed), ctx, progress,
                                                               record_interaction=False), "Save failed")
        async with AsyncSession(database) as db:
            progress = await ContextAssembler(db)._load_persisted_session_progress(action(welcome=True))
        runner = AdaptiveSession(teacher)
        if two_failures:
            failed = await runner.run(ctx, progress, retry(failed))
            state = GuidedState.model_validate(progress["guided_state"])
            require(state.recovery_attempts == 2 and state.next_move == original_move,
                    "First Retry did not preserve the requested move")

        calls = []
        original_completion = ai_resilience_manager.chat_completion

        async def observed_completion(**kwargs):
            result = await original_completion(**kwargs)
            calls.append({"first_requested": kwargs["provider_order"][0],
                          "model_used": result.get("model_used"),
                          "format": kwargs.get("response_format", {}).get("type"),
                          "fallback": bool(result.get("is_fallback"))})
            return result

        teacher.turn.side_effect = AdaptiveTeacher().turn
        started = time.monotonic()
        with patch.object(ai_resilience_manager, "chat_completion", observed_completion):
            recovered = await runner.run(ctx, progress, retry(failed))
        state = GuidedState.model_validate(progress["guided_state"])
        require(calls and calls[0]["first_requested"] == "gemini-2.5-pro", "Pro was not requested first")
        require(any(c["model_used"] == "gemini-2.5-pro" and not c["fallback"] for c in calls),
                "No actual Pro response: a fallback cannot establish Pro acceptance")
        require(all(c["format"] == "json_object" for c in calls), "Strict mode leaked into recovery")
        require(state.recovery_attempts == 0, "Recovered turn did not reset the failure count")
        require(state.outbox == evidence and not state.completed, "Recovery changed learner evidence or completion")
        require(teacher.turn.await_args.args[2] == ("reteach" if two_failures else original_move),
                "Retry selected the wrong move")
        require(not any(isinstance(c, CTAButton) and c.action_intent == ActionIntent.RETRY
                        for c in recovered.components), "Recovery still shows the failure notice")
        teacher.evaluate.reset_mock()
        require(await runner.run(ctx, progress, submission) == recovered, "Duplicate answer changed the scene")
        teacher.evaluate.assert_not_awaited()
        Scene.model_validate_json(recovered.model_dump_json())
        return {"case": "second_retry_reteaches" if two_failures else "first_retry_escalates",
                "passed": True, "original_move": original_move,
                "recovered_move": "reteach" if two_failures else original_move,
                "evidence_preserved": True, "database_reload": True, "duplicate_answer_ignored": True,
                "seconds": round(time.monotonic() - started, 2), "calls": calls,
                "scene": recovered.model_dump(mode="json")}
    finally:
        await database.dispose()


def contract_examples():
    from lyo_app.ai_classroom.adaptive_teaching import (
        DiagnosticTurn, Evaluation, GuidedState, LearningPlan, ModelledTurn,
        UnitPackage, UnitTargetPackage, turn_schema,
    )
    from tests.adaptive_fixtures import ScriptedTeacher, context, evaluation, plan
    ctx, pathway, teacher = context(target_duration_minutes=8), plan(1), ScriptedTeacher()
    state = GuidedState(owner=ctx.user_id, plan=pathway)
    examples = {LearningPlan: pathway, Evaluation: evaluation()}
    for move in ("diagnose", "orient", "reteach", "answer_question", "guided", "explain", "transfer"):
        schema = turn_schema(move)
        examples[schema] = schema.model_validate(teacher._turn(ctx, state, move).model_dump())
    target = UnitTargetPackage(**{move: teacher._turn(ctx, state, move).model_dump()
                                 for move in ("guided", "faded", "independent", "explain", "transfer")})
    examples[UnitPackage] = UnitPackage(
        diagnostic=examples[DiagnosticTurn].model_dump(), orient=examples[ModelledTurn].model_dump(),
        targets=[target], interleave=teacher._turn(ctx, state, "interleave").model_dump(),
    )
    return examples


async def contract_probe(provider, schema, example):
    from jsonschema import Draft202012Validator
    from lyo_app.ai_classroom.strict_schema import strict_json_schema
    from lyo_app.core.ai_resilience import ai_resilience_manager
    enforced = strict_json_schema(schema.model_json_schema())
    Draft202012Validator.check_schema(enforced)
    reference = example.model_dump(mode="json")
    Draft202012Validator(enforced).validate(reference)
    started = time.monotonic()
    result = await ai_resilience_manager.chat_completion(
        messages=[{"role": "system", "content": "Return exactly the supplied reference JSON. This is a schema acceptance probe; do not rewrite values."},
                  {"role": "user", "content": json.dumps(reference)}],
        provider_order=[provider], response_format={"type": "json_schema", "json_schema": {
            "name": schema.__name__, "strict": True, "schema": enforced}},
        max_tokens=16000 if schema.__name__ == "UnitPackage" else 4500,
        timeout=100 if schema.__name__ == "UnitPackage" else 45,
        use_cache=False,
    )
    require(not result.get("is_fallback") and result.get("model_used") == provider,
            f"Provider did not accept/answer the contract: {str(result.get('error', 'no response'))[:500]}")
    raw = (result.get("content") or "").strip()
    payload = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    Draft202012Validator(enforced).validate(payload)
    schema.model_validate(payload)
    return {"provider": provider, "contract": schema.__name__, "passed": True,
            "seconds": round(time.monotonic() - started, 2), "tokens": result.get("tokens_used")}


async def run(output, contracts=True):
    require(os.getenv("CLASSROOM_STRICT_SCHEMA") == "0", "Recovery staging must explicitly set CLASSROOM_STRICT_SCHEMA=0")
    REPORT.update(status="running", strict_schema="0", revision=os.getenv("RAILWAY_GIT_COMMIT_SHA"))
    for two in (False, True):
        try:
            REPORT["recovery"].append(await recovery_probe(two))
        except Exception as exc:
            REPORT["recovery"].append({"case": "second_retry_reteaches" if two else "first_retry_escalates",
                                       "passed": False, "error": safe_error(exc)})
        Path(output).write_text(json.dumps(REPORT, indent=2))
        print("CLASSROOM_VALIDATION " + json.dumps({"recovery": REPORT["recovery"][-1] | {"scene": None}}), flush=True)
    if contracts:
        for provider in ("gemini-2.5-pro", "gemini-2.5-flash", "gpt-4o-mini", "gpt-4o"):
            for schema, example in contract_examples().items():
                try:
                    entry = await contract_probe(provider, schema, example)
                except Exception as exc:
                    entry = {"provider": provider, "contract": schema.__name__, "passed": False,
                             "error": safe_error(exc)}
                REPORT["contracts"].append(entry)
                Path(output).write_text(json.dumps(REPORT, indent=2))
                print("CLASSROOM_VALIDATION " + json.dumps(entry), flush=True)
    REPORT["status"] = "passed" if all(r["passed"] for r in REPORT["recovery"] + REPORT["contracts"]) else "failed"
    Path(output).write_text(json.dumps(REPORT, indent=2))
    return REPORT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="/tmp/classroom-recovery-validation.json")
    parser.add_argument("--serve", action="store_true", help="Expose only redacted probe results while the bounded worker runs")
    parser.add_argument("--recovery-only", action="store_true")
    args = parser.parse_args()
    if not args.serve:
        result = asyncio.run(run(args.output, not args.recovery_only))
        raise SystemExit(0 if result["status"] == "passed" else 1)
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    import uvicorn

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(run(args.output, not args.recovery_only))
        yield
        task.cancel()

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"worker": "classroom-recovery-validation", "status": REPORT["status"]}

    @app.get("/results")
    async def results():
        return REPORT

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
