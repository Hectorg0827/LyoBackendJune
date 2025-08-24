"""Dataset preparation utilities for tutor fine-tuning.

Reads raw conversational tutoring data (JSONL) and produces a cleaned JSONL
with flattened prompt/response records suitable for supervised fine-tuning.

Input JSONL record schema (examples):
{
  "task_type": "socratic_hint",
  "student_level": "beginner",
  "domain": "python-loops",
  "turns": [
    {"role":"student","content":"Why does my loop..."},
    {"role":"tutor","hint_level":1,"strategy":"clarify_goal","content":"What sequence..."}
  ],
  "learning_objective": "Understand even numbers",
  "misconception_tag": "off_by_one_addition"
}

Output JSONL record:
{
  "text": "<|system|>Role: Adaptive tutor...<|student|>...<|tutor|>...<|endofdialog|>",
  "meta": {...}
}
"""
from __future__ import annotations
import json, argparse, sys
from pathlib import Path
from typing import List, Dict, Any

SYSTEM_PREAMBLE = (
    "<|system|>Role: Adaptive expert tutor. Use Socratic questioning, scaffolding, and reflection. "
    "Output clear, jargon-light explanations and minimal next hints when appropriate.</|system|>"
)


def flatten_turns(turns: List[Dict[str, Any]]) -> str:
    parts = []
    for t in turns:
        role = t.get("role")
        content = t.get("content", "").strip()
        if not content:
            continue
        if role == "tutor" and t.get("hint_level") is not None:
            parts.append(f"<|tutor|><|hint:{t['hint_level']}|>{content}")
        else:
            parts.append(f"<|{role}|>{content}")
    parts.append("<|endofdialog|>")
    return "\n".join(parts)


def transform_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    turns = rec.get("turns", [])
    flattened = flatten_turns(turns)
    text = SYSTEM_PREAMBLE + "\n" + flattened
    meta = {
        "task_type": rec.get("task_type"),
        "student_level": rec.get("student_level"),
        "domain": rec.get("domain"),
        "misconception_tag": rec.get("misconception_tag"),
    }
    return {"text": text, "meta": meta}


def process(in_path: Path, out_path: Path):
    with in_path.open() as fin, out_path.open("w") as fout:
        for line in fin:
            if not line.strip():
                continue
            rec = json.loads(line)
            out = transform_record(rec)
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")


def cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    process(Path(args.input), Path(args.output))

if __name__ == "__main__":
    cli()
