"""Repeatable, bounded startup benchmark against ONE pinned staging backend revision.

No production requests, no learner grading/mastery assertions, no audio claims.
Sequential authenticated synthetic learners isolate model authoring latency from
content reuse. Railway deploy logs provide independent rejection-count evidence.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import statistics
import sys
import time
import uuid
from urllib.parse import urlencode

import httpx
import websockets

from continuous_teaching_live_staging_smoke import (
    BASE, WS_ENDPOINT, create_synthetic, report, require, verify_target,
)

EXPECTED_REVISION = "afe9c8a0787c857f093a0d3602663c9757afa880"
# Five matched maths starts plus independent cross-subject/bilingual probes.
CASES = [
    ("fractions", "Compare one half with one third using equal-sized pieces", "en-US"),
    ("science", "Explain evaporation and condensation using a cold glass of water", "en-US"),
    ("spanish", "Distinguir sustantivos y adjetivos en oraciones sencillas", "es-ES"),
]
SAMPLES = 12
TIMEOUT_SECONDS = 120


def utc_time() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


async def start_once(client: httpx.AsyncClient, index: int) -> float | None:
    marker = f"latency{index}"
    token, user_id = await create_synthetic(client, marker)
    session = "ct-perf-" + uuid.uuid4().hex
    case = CASES[0] if index < 5 else CASES[1] if index < 9 else CASES[2]
    subject, topic, language = case
    params = {
        "token": token,
        "session_id": session,
        "topic": topic,
        "language": language,
        "continuous_teaching": "0",  # match the previous 39.1s startup
        "resume": "0",
    }
    url = WS_ENDPOINT + "?" + urlencode(params)
    started_at = utc_time()
    clock = time.monotonic()
    try:
        async with websockets.connect(url, open_timeout=20, max_size=5_000_000) as ws:
            deadline = clock + TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                try:
                    event = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("event_type")
                if kind == "error":
                    raise RuntimeError("server returned classroom error")
                scene = event.get("scene") or {}
                if kind == "scene_start" and isinstance(scene, dict):
                    scene_id = str(scene.get("scene_id") or "")
                    require(
                        scene_id and not scene_id.startswith(
                            ("db_error_", "error_welcome_", "welcome_")
                        ),
                        "response did not contain an authoritative lesson scene",
                    )
                    require(str(event.get("user_id")) == user_id, "cross-user scene")
                    require(event.get("session_id") == session, "cross-session scene")
                    ms = round((time.monotonic() - clock) * 1000)
                    report(
                        "lesson_start_sample", status="passed", sample=index + 1,
                        session_id=session, elapsed_ms=ms,
                        case=subject, language=language,
                        started_at_utc=started_at, finished_at_utc=utc_time(),
                        authoritative_scene=True,
                    )
                    return ms
            raise TimeoutError("authoritative scene not ready within 120 seconds")
    except Exception as exc:
        report(
            "lesson_start_sample", status="failed", sample=index + 1,
            session_id=session, reason=type(exc).__name__,
            case=subject, language=language,
            started_at_utc=started_at, finished_at_utc=utc_time(),
        )
        return None


async def main() -> None:
    verify_target()
    async with httpx.AsyncClient(
        base_url=BASE, timeout=25, follow_redirects=False
    ) as client:
        response = await client.get("/health")
        require(response.status_code == 200, "staging health failed")
        health = response.json()
        require(health.get("status") in {"healthy", "ok"}, "unhealthy staging")
        require(health.get("commit_sha") == EXPECTED_REVISION,
                "refusing unexpected deployed revision")
        require(str(health.get("environment", "")).lower() != "production",
                "refusing production")
        report("benchmark_target", status="passed", sha=EXPECTED_REVISION,
               samples_requested=SAMPLES, cases=[case[0] for case in CASES],
               baseline_single_session_ms=39132)
        times = []
        for index in range(SAMPLES):
            duration = await start_once(client, index)
            if duration is not None:
                times.append(duration)
        sorted_ms = sorted(times)
        require(len(sorted_ms) >= 3, "fewer than 3 valid startup samples")
        # Nearest-rank empirical percentile. Deliberately expose N: a handful
        # of samples is a diagnostic, not a production latency SLO.
        import math
        p95_ms = sorted_ms[max(0, math.ceil(0.95 * len(sorted_ms)) - 1)]
        report(
            "benchmark_summary", status="passed", sample_count=len(sorted_ms),
            failures=SAMPLES - len(sorted_ms),
            durations_ms=sorted_ms,
            median_ms=round(statistics.median(sorted_ms)),
            p95_nearest_rank_ms=p95_ms,
            mean_ms=round(statistics.mean(sorted_ms)),
            baseline_single_session_ms=39132,
            median_delta_vs_baseline_ms=round(statistics.median(sorted_ms) - 39132),
            limitations=[
                "Baseline is one prior lesson start, not a statistical distribution",
                "Count authoring rejections from correlated Railway runtime logs",
                "Synthetic WebSocket sessions, not phone audio or user experience",
                "Provider availability/plan caching may affect results",
            ],
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        report("benchmark_result", status="failed", reason=type(exc).__name__)
        sys.exit(1)
