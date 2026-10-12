"""Bounded authenticated HTTP validation of a deployed multi-exam candidate.

Creates only synthetic learners. Does not bypass auth, patch providers, or
invent a score. Credentials are written only to an explicitly requested local
file, never the report or logs. Use against an isolated staging deployment.
"""
import argparse
import asyncio
from datetime import date, timedelta
import json
from pathlib import Path
import secrets
import time
import uuid

import httpx


async def validate(base_url, credentials_path=None, reuse_credentials=None):
    report = {"base_url": base_url, "status": "running", "cases": []}
    credentials = []
    started = time.monotonic()
    endpoint = "/api/v1/me/study_plans"

    def check(case, condition):
        report["cases"].append({"case": case, "passed": bool(condition)})
        if not condition:
            raise RuntimeError(f"Validation failed: {case}")

    async with httpx.AsyncClient(base_url=base_url, timeout=180) as client:
        async def request(method, path, token=None, expected=200, **kwargs):
            response = await client.request(method, path,
                headers={"Authorization": f"Bearer {token}"} if token else {}, **kwargs)
            allowed = (expected,) if isinstance(expected, int) else expected
            if response.status_code not in allowed:
                # Error responses can contain request material; keep them private.
                raise RuntimeError(f"{method} {path.split('?')[0]} returned HTTP {response.status_code}")
            return response.json() if response.content else None

        async def owner():
            if reuse_credentials:
                account = reuse_credentials.pop(0)
                result = await request("POST", "/api/v1/auth/login", json={
                    "email": account["email"], "password": account["password"],
                })
                token = result["access_token"]
                credentials.append({**account, "token": token})
                return token
            suffix = uuid.uuid4().hex[:12]
            email, password = f"testprep-{suffix}@example.com", secrets.token_urlsafe(18) + "!Aa1"
            result = await request("POST", "/api/v1/auth/register", expected=(200, 201), json={
                "email": email, "username": f"testprep-{suffix}", "password": password,
                "confirm_password": password, "first_name": "Synthetic", "last_name": "TestPrep",
            })
            if not result.get("access_token"):
                result = await request("POST", "/api/v1/auth/login", json={"email": email, "password": password})
            token = result["access_token"]
            credentials.append({"email": email, "password": password, "token": token})
            return token

        async def start(token, key):
            return await request("POST", endpoint + "/profiles/start", token, expected=201,
                                 json={"request_id": key})

        async def state(token, profile_id):
            return await request("GET", endpoint + "/state", token, params={"profile_id": profile_id})

        async def prepare(token, profile_id, subject, topic):
            message = (f"My {subject} test is on {(date.today() + timedelta(days=14)).isoformat()}. "
                       f"The test covers {topic}. I can study 25 minutes a day, five days per week. "
                       "It is multiple choice. My confidence is five out of ten in each listed topic, "
                       "and my stress level is five out of ten. "
                       "Use America/New_York as my timezone. These are all my test details.")
            for attempt in range(4):
                turn = await request("POST", endpoint + "/intake/turn", token, json={
                    "user_message": message, "test_profile_id": profile_id,
                    "request_id": str(uuid.uuid4()), "timezone": "America/New_York", "materials": [],
                })
                check(f"{subject.lower()}_intake_stays_on_selected_profile_{attempt}",
                      turn["test_profile_id"] == profile_id)
                if turn["intake_complete"]:
                    break
            check(f"{subject.lower()}_live_intake_completes", bool(turn["intake_complete"]))
            result = await request("POST", endpoint + "/plans/generate", token,
                                   params={"test_profile_id": profile_id})
            saved = await state(token, profile_id)
            check(f"{subject.lower()}_has_its_own_generated_plan",
                  saved["plan"]["id"] == result["plan_id"] and bool(saved["sessions"]))
            return saved

        try:
            first, second = await owner(), await owner()
            check("authenticated_two_distinct_synthetic_learners", first != second)
            old = await start(first, "algebra-" + uuid.uuid4().hex)
            algebra_id = old["profile_id"]
            algebra = await prepare(first, algebra_id, "Algebra", "linear equations and graphing lines")
            # Completion is deliberately unscored unless real evidence exists.
            await request("POST", endpoint + f"/sessions/{algebra['sessions'][0]['id']}/complete", first)
            before = await state(first, algebra_id)
            check("old_exam_has_recorded_completed_work", any(s["status"] == "completed" for s in before["sessions"]))

            key = "biology-" + uuid.uuid4().hex
            results = await asyncio.gather(*(start(first, key) for _ in range(6)))
            biology_id = results[0]["profile_id"]
            check("concurrent_same_key_creates_exactly_one_exam", sum(r["created"] for r in results) == 1
                  and len({r["profile_id"] for r in results}) == 1)
            check("new_exam_is_independent", biology_id != algebra_id)
            check("creation_preserves_old_plan_schedule_and_completed_work", await state(first, algebra_id) == before)
            other = await start(second, key)
            check("creation_key_is_scoped_to_owner", other["profile_id"] != biology_id)
            check("foreign_explicit_profile_is_404", bool(await request("GET", endpoint + "/state", second,
                  expected=404, params={"profile_id": algebra_id})))
            check("missing_explicit_profile_is_404", bool(await request("GET", endpoint + "/state", first,
                  expected=404, params={"profile_id": "missing-test-profile"})))
            await request("POST", endpoint + "/profiles/start", first, expected=422, json={"request_id": "short"})
            check("invalid_creation_key_is_rejected", True)
            await request("GET", endpoint + "/profiles", expected=(401, 403))
            check("anonymous_history_is_rejected", True)
            history = await request("GET", endpoint + "/profiles", second)
            own_history = await request("GET", endpoint + "/profiles", first)
            check("history_never_lists_another_learners_exams", other["profile_id"] in {p["id"] for p in history}
                  and not ({p["id"] for p in history} & {p["id"] for p in own_history}))

            biology = await prepare(first, biology_id, "Biology", "cell membranes and DNA")
            check("second_generated_plan_is_distinct", biology["plan"]["id"] != before["plan"]["id"])
            check("new_intake_and_generation_preserve_algebra", await state(first, algebra_id) == before)
            check("switching_back_restores_second_exam", await state(first, biology_id) == biology)
            distinct = await asyncio.gather(*(start(first, "distinct-" + uuid.uuid4().hex) for _ in range(2)))
            check("concurrent_distinct_keys_create_distinct_exams", all(r["created"] for r in distinct)
                  and distinct[0]["profile_id"] != distinct[1]["profile_id"])
            history = await request("GET", endpoint + "/profiles", first)
            legacy = await request("GET", endpoint + "/state", first)
            check("legacy_state_still_resumes_latest_profile", legacy["profile"]["id"] == history[0]["id"])
            for status in ("completed", "archived"):
                await request("PATCH", endpoint + "/" + before["plan"]["id"], first, json={"status": status})
                saved = await state(first, algebra_id)
                check(f"selected_{status}_history_retains_plan_and_sessions",
                      saved["plan"]["id"] == before["plan"]["id"] and saved["plan"]["status"] == status
                      and saved["sessions"] == before["sessions"])
            report.update(status="passed", profile_ids={"algebra": algebra_id, "biology": biology_id})
        except Exception as error:
            # Never include credentials, provider response text or learner input.
            report.update(status="failed", error=str(error).split("Bearer ")[0][:350])
        finally:
            if credentials_path:
                target = Path(credentials_path)
                target.write_text(json.dumps({"base_url": base_url, "accounts": credentials}))
                target.chmod(0o600)
            report["duration_seconds"] = round(time.monotonic() - started, 2)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--credentials-output")
    parser.add_argument("--reuse-credentials", help="Log in existing synthetic learners to avoid registration rate limits")
    args = parser.parse_args()
    reused = json.loads(Path(args.reuse_credentials).read_text())["accounts"] if args.reuse_credentials else None
    result = asyncio.run(validate(args.base_url.rstrip('/'), args.credentials_output, reused))
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "passed" else 1)
