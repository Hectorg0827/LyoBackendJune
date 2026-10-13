"""Real JWT/HTTP/PostgreSQL Discover verification in an isolated staging DB.

Never overrides authentication, calls an AI provider, or mutates serving data.
The optional production audit uses a read-only database transaction and GETs.
"""
import asyncio
import base64
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB_NAME = "discover_filters_20261013"
LIVE = "https://api.lyoai.app"
KNOWN_SHA = "e1cb18e4803215667a262c131fcf0a38014151d13063520c2151bec9c1864d25"


def guard():
    if os.getenv("DISCOVER_FILTER_VALIDATION_ENABLED") != "true":
        raise RuntimeError("Explicit Discover staging validation flag required")
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    url = urlsplit(dsn)
    if url.hostname != "classroomstagingdb.railway.internal" or url.path != "/" + DB_NAME:
        raise RuntimeError("Validation must use its independent staging database")
    return dsn


async def prepare():
    guard()
    dsn = os.environ["DISCOVER_VALIDATION_ADMIN_URL"]
    if urlsplit(dsn).hostname != "classroomstagingdb.railway.internal":
        raise RuntimeError("Database provisioning must target existing staging Postgres")
    connection = await asyncpg.connect(dsn, timeout=30)
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", DB_NAME)
        if not exists:
            await connection.execute(f'CREATE DATABASE "{DB_NAME}"')
        print("DISCOVER_VALIDATION_DATABASE_READY=" + DB_NAME, flush=True)
    finally:
        await connection.close()


async def verify(base_url="http://127.0.0.1:8080"):
    dsn = guard()
    report = {"status": "running", "tested_commit": os.getenv("RAILWAY_GIT_COMMIT_SHA"),
              "database": DB_NAME, "auth_overridden": False, "cases": [], "media": {}}
    started = time.monotonic()
    def check(name, condition, **evidence):
        report["cases"].append({"case": name, "passed": bool(condition), **evidence})

    async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
        async def call(path, token=None, method="GET", expected=200, **kwargs):
            response = await client.request(method, path,
                headers={"Authorization": "Bearer " + token} if token else {}, **kwargs)
            allowed = (expected,) if isinstance(expected, int) else expected
            if response.status_code not in allowed:
                raise RuntimeError(f"{method} {path} returned HTTP {response.status_code}")
            return response.json()

        try:
            for attempt in range(120):
                try:
                    health = await call("/health")
                    if health.get("services", {}).get("database") == "healthy":
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Candidate database readiness timed out")
            check("real_candidate_boot_and_database_health", True, commit=health.get("commit_sha"))

            # /health proves connectivity before background schema setup finishes.
            for attempt in range(120):
                connection = await asyncpg.connect(dsn, timeout=15)
                try:
                    ready = await connection.fetchval("""SELECT to_regclass('users') IS NOT NULL
                        AND to_regclass('clips') IS NOT NULL AND to_regclass('clip_saves') IS NOT NULL
                        AND to_regclass('refresh_tokens') IS NOT NULL""")
                finally:
                    await connection.close()
                if ready:
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Candidate schema readiness timed out")
            check("actual_auth_and_clip_tables_ready", True)

            # Uses the real registration/login endpoints and their issued JWTs.
            tokens, owners = [], []
            for label in ("a", "b"):
                email = f"discover-validation-{label}@example.com"
                password = os.environ["DISCOVER_VALIDATION_PASSWORD"]
                signup = await client.post("/auth/register", json={
                    "email": email, "username": f"discover-validation-{label}",
                    "password": password, "confirm_password": password,
                    "first_name": "Synthetic", "last_name": "Discover",
                })
                if signup.status_code in (200, 201):
                    result = signup.json()
                elif signup.status_code in (400, 409):
                    result = await call("/auth/login", method="POST", json={"email": email, "password": password})
                else:
                    raise RuntimeError(f"Synthetic registration returned HTTP {signup.status_code}")
                if not result.get("access_token"):
                    result = await call("/auth/login", method="POST", json={"email": email, "password": password})
                token = result["access_token"]
                payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
                tokens.append(token)
                owners.append(int(payload.get("user_id") or payload["sub"]))
            check("two_distinct_real_authenticated_accounts", owners[0] != owners[1])

            # Reuse the previously verified storage object; never upload serving media.
            from lyo_app.routers.clip_media_storage import _provider, _s3_client
            provider, bucket = _provider()
            cloud = _s3_client(provider)
            inventory = await asyncio.to_thread(cloud.list_objects_v2, Bucket=bucket, Prefix="media/clips/", MaxKeys=100)
            matches = [x for x in inventory.get("Contents", []) if x["Size"] == 663882 and x["Key"].endswith(".mp4")]
            if not matches:
                raise RuntimeError("Recorded durable MP4 fixture not found; media verification remains blocked")
            fixture_path = "/api/v1/media/file/clips/" + matches[0]["Key"].split("/")[-1]
            candidate_video = await client.get(fixture_path)
            async with httpx.AsyncClient(timeout=60, follow_redirects=False) as live_client:
                live_video = await live_client.get(LIVE + fixture_path)
                expected_bytes = live_video.content
                check("serving_mp4_fixture_200_and_recorded_hash", live_video.status_code == 200
                      and hashlib.sha256(expected_bytes).hexdigest() == KNOWN_SHA)
                check("candidate_mp4_exactly_matches_serving_fixture", candidate_video.status_code == 200
                      and candidate_video.content == expected_bytes and len(expected_bytes) == 663882)
                for header, start, end in [("bytes=0-1023", 0, 1023), ("bytes=4096-8191", 4096, 8191),
                                           ("bytes=-1024", len(expected_bytes)-1024, len(expected_bytes)-1),
                                           ("bytes=660000-", 660000, len(expected_bytes)-1)]:
                    for scope, transport, target in [("candidate", client, fixture_path), ("serving", live_client, LIVE+fixture_path)]:
                        response = await transport.get(target, headers={"Range": header})
                        check(f"{scope}_range_{header}", response.status_code == 206
                              and response.content == expected_bytes[start:end+1]
                              and response.headers.get("content-range") == f"bytes {start}-{end}/{len(expected_bytes)}")
                for scope, transport, target in [("candidate", client, fixture_path), ("serving", live_client, LIVE+fixture_path)]:
                    response = await transport.get(target, headers={"Range": "bytes=9999999-"})
                    check(scope+"_beyond_eof_416", response.status_code == 416
                          and response.headers.get("content-range") == f"bytes */{len(expected_bytes)}")
                report["media"] = {"fixture_url": LIVE+fixture_path, "bytes": len(expected_bytes),
                                   "sha256": hashlib.sha256(expected_bytes).hexdigest()}
                poster_inventory = await asyncio.to_thread(cloud.list_objects_v2, Bucket=bucket,
                                                            Prefix="media/clip_thumbnails/", MaxKeys=20)
                posters = poster_inventory.get("Contents", [])
                if posters:
                    poster_path = "/api/v1/media/file/clip_thumbnails/" + posters[0]["Key"].split("/")[-1]
                    first, second = await client.get(poster_path), await live_client.get(LIVE+poster_path)
                    check("candidate_and_serving_poster_bytes_match", first.status_code == second.status_code == 200
                          and first.content == second.content and len(first.content) > 0)
                    report["media"]["poster_url"] = LIVE+poster_path

            # SQL creates fixture data only; tested queries remain actual HTTP routes.
            fixtures = []
            for i in range(30):
                fixtures.append({"owner": owners[0], "title": "target-beyond-first-page" if i == 0 else f"Math clip {i:02}",
                                 "description": "description-needle" if i == 3 else "math lesson",
                                 "subject": ["Math", "math", " MATH "][i % 3],
                                 "topic": "topic-needle" if i == 4 else "fractions", "public": True,
                                 "views": i % 4, "likes": i % 3, "level": "beginner"})
            for title, subject in [("Literal 100%_Math / x+y & café", "Science"), ("Literal 100abMath", "science"),
                                   ("title-needle", "Biology"), ("ordinary subject text", "Subject-Needle"),
                                   ("null label", None), ("blank label", ""), ("spaces label", " "),
                                   ("placeholder general", "General"), ("placeholder unknown", "Unknown")]:
                fixtures.append({"owner": owners[1], "title": title, "description": "",
                                 "subject": subject, "topic": "optics", "public": True,
                                 "views": 50, "likes": 4, "level": "advanced"})
            fixtures += [{"owner": owners[0], "title": "private-secret-a", "description": "",
                          "subject": "Math", "topic": "private", "public": False, "views": 999,
                          "likes": 999, "level": "beginner"},
                         {"owner": owners[1], "title": "private-secret-b", "description": "",
                          "subject": "PrivateOnly", "topic": "private", "public": False, "views": 999,
                          "likes": 999, "level": "beginner"},
                         {"owner": owners[1], "title": "visibility-transition", "description": "",
                          "subject": "Math", "topic": "private", "public": True, "views": 999,
                          "likes": 999, "level": "beginner"}]
            connection = await asyncpg.connect(dsn, timeout=30)
            try:
                async with connection.transaction():
                    await connection.execute("DELETE FROM clip_saves WHERE clip_id IN (SELECT id FROM clips WHERE user_id = ANY($1::int[]))", owners)
                    await connection.execute("DELETE FROM clips WHERE user_id = ANY($1::int[])", owners)
                    for i, item in enumerate(fixtures):
                        item["id"] = str(await connection.fetchval("""INSERT INTO clips
                          (user_id,title,description,video_url,subject,topic,level,tags,key_points,is_public,
                           view_count,like_count,share_count,comment_count,created_at,updated_at,duration_seconds,enable_course_generation)
                          VALUES ($1,$2,$3,$4,$5,$6,$7,'[]','[]',$8,$9,$10,0,0,$11,$11,8,false) RETURNING id""",
                          item["owner"], item["title"], item["description"], LIVE+fixture_path, item["subject"],
                          item["topic"], item["level"], item["public"], item["views"], item["likes"],
                          datetime(2026, 10, 1) + timedelta(minutes=i//2)))
                    # Retained saves deliberately include another creator's private clip.
                    for item in fixtures:
                        await connection.execute("INSERT INTO clip_saves(user_id,clip_id,created_at) VALUES($1,$2,$3)",
                                                 owners[0], int(item["id"]), datetime(2026, 10, 1))
            finally:
                await connection.close()
            report["fixture_counts"] = {"clips": len(fixtures), "public": sum(x["public"] for x in fixtures)}
            token = tokens[0]
            for path in ["/api/v1/clips/discover/filters", "/api/v1/clips/discover", "/api/v1/clips/saved"]:
                result = await client.get(path)
                check("anonymous_rejected_"+path.rsplit("/",1)[1], result.status_code in (401,403), http_status=result.status_code)
                result = await client.get(path, headers={"Authorization":"Bearer invalid-token"})
                check("invalid_token_rejected_"+path.rsplit("/",1)[1], result.status_code in (401,403), http_status=result.status_code)

            filters = await call("/api/v1/clips/discover/filters", token)
            counts = {x["name"].strip().lower():x["count"] for x in filters["subjects"]}
            check("subject_counts_and_case_collapsing", counts == {"math":31,"science":2,"biology":1,"subject-needle":1}, counts=counts)
            for subject, count in counts.items():
                response = await call("/api/v1/clips/discover", token, params={"subject":subject})
                check("subject_matches_advertised_count_"+subject, response["total"]==count)

            baseline = await call("/api/v1/clips/discover", token)
            check("target_is_outside_original_first_twenty", fixtures[0]["id"] not in {x["id"] for x in baseline["clips"]})
            for q, expected_id in [("target-beyond-first-page",fixtures[0]["id"]),
                                   ("description-needle",fixtures[3]["id"]), ("topic-needle",fixtures[4]["id"]),
                                   ("title-needle",fixtures[32]["id"]), ("subject-needle",fixtures[33]["id"]),
                                   ("100%_Math",fixtures[30]["id"]), ("x+y & café",fixtures[30]["id"]),
                                   ("/",fixtures[30]["id"]), (" CAFÉ ",fixtures[30]["id"])]:
                response = await call("/api/v1/clips/discover", token, params={"q":q})
                check("literal_search_"+q, response["total"]==1 and [x["id"] for x in response["clips"]]==[expected_id])
            blank = await call("/api/v1/clips/discover", token, params={"q":"   "})
            check("blank_search_preserves_total", blank["total"]==baseline["total"])
            combination = await call("/api/v1/clips/discover", token,
                                     params={"q":"target-beyond-first-page","subject":" mAtH ","sort":"latest","level":"beginner"})
            check("search_subject_sort_level_combine", combination["total"]==1 and combination["clips"][0]["id"]==fixtures[0]["id"])
            for params in [{"sort":"following"},{"q":"x"*121},{"subject":"x"*101},{"page":0},{"per_page":101}]:
                response = await client.get("/api/v1/clips/discover", headers={"Authorization":"Bearer "+token},params=params)
                check("invalid_parameter_"+next(iter(params)), response.status_code==422, http_status=response.status_code)

            public = [x for x in fixtures if x["public"]]
            for sort in ["for_you","latest","popular"]:
                order = sorted(public, key=lambda x: (x["views"]+2*x["likes"],int(x["id"])) if sort=="for_you"
                               else (x["likes"],x["views"],int(x["id"])) if sort=="popular"
                               else (fixtures.index(x)//2,int(x["id"])), reverse=True)
                pages=[]
                for page in [1,2]:
                    value=await call("/api/v1/clips/discover",token,params={"sort":sort,"page":page})
                    pages+=value["clips"]
                    check(f"{sort}_page_{page}_total",value["total"]==len(public))
                ids=[x["id"] for x in pages]
                check(sort+"_pagination_exact_ids_and_tiebreakers",ids==[x["id"] for x in order],returned=len(ids),unique=len(set(ids)))
            for route in ["discover","saved"]:
                pages=[]
                for page in [1,2]:
                    value=await call("/api/v1/clips/"+route,token,params={"subject":" mAtH ","page":page})
                    pages+=value["clips"]
                expected={x["id"] for x in fixtures if x["subject"] and x["subject"].strip().lower()=="math"
                          and (x["public"] or (route=="saved" and x["owner"]==owners[0]))}
                ids=[x["id"] for x in pages]
                check(route+"_filtered_pagination_no_duplicates",set(ids)==expected and len(ids)==len(expected),returned=len(ids),unique=len(set(ids)))
            saved=await call("/api/v1/clips/saved",token,params={"per_page":100})
            expected={x["id"] for x in fixtures if x["public"] or x["owner"]==owners[0]}
            check("saved_privacy_and_total",saved["total"]==len(expected) and {x["id"] for x in saved["clips"]}==expected)
            other=await call("/api/v1/clips/saved",tokens[1],params={"per_page":100})
            check("saved_is_scoped_to_account",other["total"]==0 and not other["clips"])
            own_private=await call("/api/v1/clips/saved",token,params={"q":"private-secret-a"})
            foreign_private=await call("/api/v1/clips/saved",token,params={"q":"private-secret-b"})
            check("saved_search_includes_own_private",own_private["total"]==1)
            check("saved_search_excludes_foreign_private",foreign_private["total"]==0)
            transition=fixtures[-1]
            await call("/api/v1/clips/"+transition["id"],tokens[1],method="PUT",json={"isPublic":False})
            after=await call("/api/v1/clips/saved",token,params={"q":"visibility-transition"})
            check("saved_former_public_now_private_is_hidden",after["total"]==0 and not after["clips"])

            audit_dsn=os.getenv("DISCOVER_LIVE_AUDIT_DATABASE_URL")
            if audit_dsn:
                connection=await asyncpg.connect(audit_dsn.replace("postgresql+asyncpg://","postgresql://",1),timeout=30)
                try:
                    async with connection.transaction(readonly=True):
                        legacy=await connection.fetch("SELECT id,video_url FROM clips WHERE id IN (1,2) ORDER BY id")
                finally:
                    await connection.close()
                legacy_results=[]
                async with httpx.AsyncClient(timeout=30,follow_redirects=False) as live_client:
                    for item in legacy:
                        path=urlsplit(item["video_url"]).path
                        if re.fullmatch(r"/api/v1/media/file/clips/[a-f0-9]{32}\.(mp4|mov|webm)",path):
                            response=await live_client.get(LIVE+path,headers={"Range":"bytes=0-1023"})
                            legacy_results.append({"clip_id":item["id"],"http_status":response.status_code})
                        else:
                            legacy_results.append({"clip_id":item["id"],"status":"outside_canonical_media_path"})
                report["legacy_media_read_only_audit"]=legacy_results
            report["status"]="passed" if all(x["passed"] for x in report["cases"]) else "failed"
        except Exception as error:
            check("verification_completed_without_runtime_error", False)
            report.update(status="failed",error=type(error).__name__+": "+str(error).split("Bearer")[0][:250])
        report["duration_seconds"]=round(time.monotonic()-started,2)
        report["passed"]=sum(x["passed"] for x in report["cases"])
        report["failed"]=len(report["cases"])-report["passed"]
        Path("/tmp/discover-verification-result.json").write_text(json.dumps(report,indent=2))
        print("DISCOVER_VERIFICATION_RESULT="+json.dumps(report,separators=(",",":")),flush=True)
    return report


async def serve():
    guard()
    port=os.getenv("PORT","8080")
    process=await asyncio.create_subprocess_exec(sys.executable,"-m","uvicorn","lyo_app.enhanced_main:app",
                                                "--host","0.0.0.0","--port",port)
    report=await verify("http://127.0.0.1:"+port)
    if report["status"]!="passed":
        process.terminate()
        await process.wait()
        raise SystemExit(2)
    await process.wait()
    raise SystemExit(process.returncode)


if __name__=="__main__":
    asyncio.run(prepare() if sys.argv[1]=="prepare" else serve())
