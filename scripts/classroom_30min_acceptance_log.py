#!/usr/bin/env python3
"""Minimal, redacted journal for a manual 30-minute staging classroom QA run.

This is an observation log, not an automated browser test. It deliberately
rejects PASS when the clock or mandatory observations are missing.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time


REQUIRED = (
    "lesson_started",
    "first_audio_en",
    "modeled_example",
    "guided_correct",
    "guided_wrong",
    "help_preserved",
    "partial_answer",
    "fresh_independent",
    "navigation",
    "reconnect",
)


def journal(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"Journal not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def summarize(rows: list[dict]) -> dict:
    starts = [row for row in rows if row.get("type") == "start"]
    if len(starts) != 1:
        raise ValueError("Journal must contain exactly one start row")
    start = starts[0]
    ends = [row for row in rows if row.get("type") == "finish"]
    end_at = ends[-1]["epoch"] if ends else time.time()
    elapsed = max(0.0, end_at - start["epoch"])
    observed = {
        row.get("kind") for row in rows
        if row.get("type") == "event" and row.get("status") == "pass"
    }
    missing = [item for item in REQUIRED if item not in observed]
    failures = [row for row in rows if row.get("type") == "event" and row.get("status") == "fail"]
    finished = bool(ends)
    return {
        "elapsed_seconds": round(elapsed, 1),
        "thirty_minutes_observed": finished and elapsed >= 1800,
        "missing_required_checks": missing,
        "explicit_failures": len(failures),
        "finished": finished,
        "automated_gate": (
            "PASS" if finished and elapsed >= 1800 and not missing and not failures
            else "INCOMPLETE"
        ),
        "human_listening_review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("start", "event", "finish", "report"):
        p = sub.add_parser(command)
        p.add_argument("--output", required=True, type=Path)
        if command == "start":
            p.add_argument("--topic", required=True)
            p.add_argument("--tester", default="staging-qa")
        if command == "event":
            p.add_argument("--kind", required=True)
            p.add_argument("--status", choices=("pass", "fail", "blocked", "not_tested"), required=True)
            p.add_argument("--latency-ms", type=float)
            p.add_argument("--evidence", default="")
    args = parser.parse_args()
    now = time.time()
    stamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
    try:
        if args.command == "start":
            if args.output.exists():
                raise ValueError("Journal already exists; use a fresh filename")
            journal(args.output, {"type": "start", "epoch": now, "at": stamp,
                                  "topic": args.topic, "tester": args.tester})
        elif args.command == "event":
            rows = read_rows(args.output)
            if any(row.get("type") == "finish" for row in rows):
                raise ValueError("Cannot add events to a finished journal")
            journal(args.output, {"type": "event", "epoch": now, "at": stamp,
                                  "kind": args.kind, "status": args.status,
                                  "latency_ms": args.latency_ms, "evidence": args.evidence})
        elif args.command == "finish":
            rows = read_rows(args.output)
            if any(row.get("type") == "finish" for row in rows):
                raise ValueError("Journal already finished")
            journal(args.output, {"type": "finish", "epoch": now, "at": stamp})
        print(json.dumps(summarize(read_rows(args.output)), indent=2))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
